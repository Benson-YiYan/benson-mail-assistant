"""Offline proxy tunnels: remote DNS, verified TLS, read-only IMAP and fail closed."""
import socket
import ssl
import threading
import unittest
from unittest.mock import patch
import trustme
from benson_mail import mailbox_config as mail


class ProxyTests(unittest.TestCase):
    def test_validation_and_identity_preserve_existing_progress(self):
        base = {'account': 'a@example.com', 'host': 'imap.example.com'}
        configured = {**base, 'proxy_mode':'socks5', 'proxy_host':'127.0.0.1', 'proxy_port':10808}
        self.assertEqual(mail.mailbox_id(base), mail.mailbox_id(configured))
        self.assertEqual(mail.state_identity(base), mail.state_identity(configured))
        for host in ('http://localhost', 'user:secret@localhost', 'localhost/path', 'evil\r\nInjected: yes'):
            with self.assertRaises(ValueError): mail.normalize({**configured, 'proxy_host':host})
        with self.assertRaises(ValueError): mail.normalize({**configured, 'proxy_port':0})
        self.assertEqual(mail.normalize(base)['proxy_mode'], 'direct')

    def test_system_proxy_selection_no_bypass_and_no_secret_leak(self):
        value = mail.normalize({'account':'a@example.com','proxy_mode':'system'})
        with patch.object(mail.urllib.request, 'getproxies', return_value={'https':'http://localhost:10808', 'no':'*'}):
            self.assertEqual(mail.resolve_proxy(value), ('http','localhost',10808))
        with patch.object(mail.urllib.request, 'getproxies', return_value={'socks':'http://localhost:10808'}):
            self.assertEqual(mail.resolve_proxy(value), ('socks5','localhost',10808))
        for proxies in ({}, {'https':'http://user:PRIVATE@localhost:10808'}, {'https':'https://localhost:10808'}):
            with patch.object(mail.urllib.request, 'getproxies', return_value=proxies), self.assertRaises(mail.ProxyConnectionError) as caught:
                mail.resolve_proxy(value)
            self.assertNotIn('PRIVATE', str(caught.exception))

    def test_failed_proxy_does_not_resolve_or_connect_mail_destination(self):
        config = {'account':'a@example.com','host':'never-resolve.example.invalid','proxy_mode':'socks5','proxy_host':'127.0.0.1','proxy_port':9,'ui_language':'en'}
        with patch.object(mail.socket, 'create_connection', side_effect=TimeoutError('DO_NOT_LEAK')) as create:
            with self.assertRaises(mail.MailConnectionError) as caught: mail.connect(config,'SECRET')
        create.assert_called_once_with(('127.0.0.1',9), unittest.mock.ANY)
        self.assertIn('127.0.0.1:9',str(caught.exception))
        self.assertIn('No direct fallback',str(caught.exception))
        self.assertNotIn('DO_NOT_LEAK',str(caught.exception))

    def tunnel(self, kind, security='ssl', trusted=True):
        ca = trustme.CA(); cert = ca.issue_cert('imap.test.invalid')
        server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); cert.configure_cert(server_tls)
        client_tls = ssl.create_default_context()
        if trusted: ca.configure_trust(client_tls)
        listener = socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen(); listener.settimeout(5)
        commands, errors, destinations = [], [], []
        def exact(sock,n):
            result=b''
            while len(result)<n:
                data=sock.recv(n-len(result))
                if not data: raise EOFError()
                result+=data
            return result
        def worker():
            tls_handshake = False
            try:
                sock,_=listener.accept(); sock.settimeout(5)
                with sock:
                    if kind=='http':
                        header=b''
                        while not header.endswith(b'\r\n\r\n'): header+=exact(sock,1)
                        destinations.append(header.split(b'\r\n')[0])
                        sock.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                    else:
                        self.assertEqual(exact(sock,3),b'\x05\x01\x00'); sock.sendall(b'\x05\x00')
                        self.assertEqual(exact(sock,4),b'\x05\x01\x00\x03')
                        destinations.append(exact(sock,exact(sock,1)[0])+exact(sock,2))
                        sock.sendall(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
                    if security=='ssl':
                        tls_handshake = True
                        sock=server_tls.wrap_socket(sock,server_side=True)
                        tls_handshake = False
                    sock.sendall(b'* OK fixture ready\r\n')
                    while True:
                        line=b''
                        while not line.endswith(b'\r\n'): line+=exact(sock,1)
                        commands.append(line)
                        tag,op,*_=line.rstrip().split(b' '); op=op.upper()
                        if op==b'CAPABILITY': sock.sendall(b'* CAPABILITY IMAP4rev1 STARTTLS\r\n'+tag+b' OK done\r\n')
                        elif op==b'STARTTLS':
                            sock.sendall(tag+b' OK begin TLS\r\n')
                            tls_handshake = True
                            sock=server_tls.wrap_socket(sock,server_side=True)
                            tls_handshake = False
                        elif op==b'LOGIN': sock.sendall(tag+b' OK authenticated\r\n')
                        elif op==b'EXAMINE': sock.sendall(b'* 0 EXISTS\r\n'+tag+b' OK opened\r\n')
                        elif op==b'LOGOUT': sock.sendall(b'* BYE done\r\n'+tag+b' OK logout\r\n'); break
                        else: raise AssertionError(op)
                    sock.close()
            except (ssl.SSLError, ConnectionResetError):
                # Windows can report WSAECONNRESET instead of a TLS alert when
                # the client rejects this deliberately untrusted certificate.
                if trusted or not tls_handshake: errors.append('unexpected TLS failure or reset')
            except Exception as error: errors.append(repr(error))
        thread=threading.Thread(target=worker,daemon=True); thread.start()
        config={'account':'a@example.com','host':'imap.test.invalid','security':security,'proxy_mode':kind,'proxy_host':'127.0.0.1','proxy_port':listener.getsockname()[1]}
        try:
            if trusted:
                client=mail.connect(config,'SYNTHETIC',client_tls); client.logout()
            else:
                with self.assertRaisesRegex(mail.MailConnectionError,'证书'): mail.connect(config,'SYNTHETIC',client_tls)
            thread.join(6); self.assertFalse(thread.is_alive()); self.assertEqual(errors,[])
            self.assertTrue(destinations)
            self.assertIn(b'imap.test.invalid',destinations[0])
            if trusted:
                self.assertTrue(any(b' EXAMINE ' in c for c in commands))
                self.assertFalse(any(b' SELECT ' in c for c in commands))
                if security=='starttls':
                    self.assertLess(next(i for i,c in enumerate(commands) if b' STARTTLS' in c),next(i for i,c in enumerate(commands) if b' LOGIN ' in c))
            else: self.assertFalse(any(b' LOGIN ' in c for c in commands))
        finally: listener.close()

    def test_http_and_socks_verified_tls_readonly_remote_dns(self):
        for kind in ('http','socks5'):
            with self.subTest(kind=kind): self.tunnel(kind)

    def test_starttls_before_credentials_and_untrusted_certificate_rejected(self):
        self.tunnel('socks5','starttls')
        self.tunnel('http',trusted=False)

    def test_per_account_proxy_survives_save_select_restart_without_secret_reentry(self):
        import tempfile
        from pathlib import Path
        from benson_mail.bridge import Controller
        with tempfile.TemporaryDirectory() as temporary, \
             patch('benson_mail.bridge.platform.save_secret', side_effect=lambda p, *_: p.write_bytes(b'encrypted')), \
             patch('benson_mail.bridge.platform.load_secret', return_value='SYNTHETIC'), \
             patch('benson_mail.bridge.platform.set_autostart'):
            controller=Controller(Path(temporary),lambda _:None)
            base={'account':'one@example.invalid','host':'imap.example.invalid','secret':'SYNTHETIC','output_dir':temporary}
            controller.command('save_mail',{**base,'proxy_mode':'http','proxy_host':'localhost','proxy_port':10809})
            identifier=mail.mailbox_id(base)
            controller.command('save_mail',{**base,'secret':'','proxy_mode':'socks5','proxy_host':'127.0.0.1','proxy_port':10808})
            controller.command('select_mail',{'id':''})
            controller.command('save_mail',{**base,'account':'two@example.invalid','proxy_mode':'direct'})
            controller=Controller(Path(temporary),lambda _:None)
            controller.command('select_mail',{'id':identifier})
            self.assertEqual(controller.config['proxy_mode'],'socks5')
            self.assertEqual(controller.config['proxy_port'],10808)
            other=next(p for p in controller.profiles() if p['account']=='two@example.invalid')
            self.assertEqual(other['proxy_mode'],'direct')

    def test_handshake_errors_sanitize_untrusted_proxy_response(self):
        for reply in (b'HTTP/1.1 407 PRIVATE\r\n\r\n', b'PRIVATE\r\n\r\n'):
            left,right=socket.socketpair()
            with left,right:
                right.sendall(reply)
                with patch.object(mail.socket,'create_connection',return_value=left), self.assertRaises(mail.ProxyConnectionError) as caught:
                    mail.proxy_socket(('http','localhost',1234),'imap.test.invalid',993,.3)
                self.assertNotIn('PRIVATE',str(caught.exception))
        left,right=socket.socketpair()
        with left,right, patch.object(mail.socket,'create_connection',return_value=left):
            with self.assertRaisesRegex(mail.ProxyConnectionError,'timed out'):
                mail.proxy_socket(('socks5','localhost',1234),'imap.test.invalid',993,.05)


if __name__=='__main__': unittest.main()
