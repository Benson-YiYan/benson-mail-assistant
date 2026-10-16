"""GUI entrypoint. --self-test never loads real account settings."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import traceback

def self_test(result_path,screenshot):
    result={'ok':False,'checks':[]}; app=None
    try:
        from benson_mail import platform_windows as platform
        from benson_mail.ui import Application
        from benson_mail.core import Service, APIAnalyzer, ANALYSIS_PROMPT
        from benson_mail.ai_api import tls_context
        import ssl
        import certifi
        context = tls_context()
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        assert Path(certifi.where()).is_file()
        assert Path(certifi.where()).stat().st_size > 100000
        result['checks'].append('bundled CA roots and native TLS context with hostname and certificate verification enabled')
        import tkinter as tk
        from PIL import ImageGrab
        from email.message import EmailMessage
        from datetime import datetime,timezone
        with tempfile.TemporaryDirectory(prefix='BensonMail-test-') as temporary:
            directory=Path(temporary); account='synthetic@example.invalid'; secret='SYNTHETIC-NOT-A-CREDENTIAL'
            platform.save_secret(directory/'secret.bin',account,secret)
            assert platform.load_secret(directory/'secret.bin',account)==secret
            result['checks'].append('current-user DPAPI round trip')
            assert platform.documents_dir().is_absolute(); result['checks'].append('Windows Documents known folder')
            name='BensonMail-SelfTest'
            try:
                platform.set_autostart(True,name); assert platform.has_autostart(name)
                platform.set_autostart(False,name); assert not platform.has_autostart(name)
            finally: platform.set_autostart(False,name)
            result['checks'].append('startup register and cleanup')
            m=EmailMessage(); m['Subject']='模拟来信：合同检查'; m['From']='demo@example.invalid'; m.set_content('请周五检查附件并回复。')
            class FakeMailbox:
                messages={}
                def snapshot(self): return 'synthetic',[*self.messages]
                def fetch(self,uid): return m.as_bytes(),datetime(2026,10,14,1,2,tzinfo=timezone.utc)
            box=FakeMailbox(); calls=[]
            def analyze(message,stop):
                calls.append(message)
                return '1 新邮件提醒\n模拟来信\n2 发件人\ndemo@example.invalid\n3 中文摘要\n请检查合同。\n4 具体待办及截止时间\n周五检查，具体日期待确认。\n5 附件实际内容\n无附件。\n6 建议回复\n收到，我将检查后回复。'
            config={'account':account,'output_dir':str(directory/'中文报告'),'codex_command':[]}
            events=[]; service=Service(config,secret,directory/'state',events.append,mailbox=box,analyzer=analyze)
            service.check_once(); service.check_once(); assert not calls
            box.messages[1]=True; service.check_once(); service.check_once(); assert len(calls)==1
            files=list((directory/'中文报告').glob('*/*.txt')); assert len(files)==1; assert all(section in files[0].read_text(encoding='utf-8') for section in ('新邮件提醒','发件人','中文摘要','具体待办','附件实际内容','建议回复'))
            result['checks'].append('synthetic baseline, empty check, six sections, Unicode export, deduplication')
            root=tk.Tk(); app=Application(root,directory/'ui',config,self_test=True)
            app.create_tray()
            import time
            deadline=time.monotonic()+10
            while not app.tray_ready.is_set() and time.monotonic()<deadline:
                root.update(); time.sleep(.05)
            assert app.tray is not None and app.tray_ready.is_set(), 'Windows tray failed to start'
            assert app.tray.visible, 'Windows tray icon is not visible'
            for event in events: app.events.put(event)
            app.drain(); root.update()
            app.refresh_reports(); root.update()
            rows=app.reports.get_children()
            assert len(rows)==1
            assert app.reports.item(rows[0],'values')[0]=='模拟来信：合同检查'
            assert app.reports.item(rows[0],'values')[2]=='2026-10-14 09:02'
            app.search.set('不存在的测试词'); root.update(); assert not app.reports.get_children()
            app.reset_filters(); root.update(); assert len(app.reports.get_children())==1
            app.interval.set('25'); app.apply_interval(); root.update()
            assert '每25秒' in app.detail.get()
            app.show_onboarding(); root.update()
            dialogs=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel)]
            assert len(dialogs)==1 and dialogs[0].winfo_viewable()
            dialogs[0].destroy()
            result['checks'].append('separate original subject/time, local search/reset, editable interval and first-run account dialog')
            from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
            import threading
            api_requests=[]
            class APIHandler(BaseHTTPRequestHandler):
                def log_message(self,*_): pass
                def do_POST(self):
                    api_requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                    self.send_response(200); self.end_headers()
                    self.wfile.write(json.dumps({'choices':[{'message':{'content':'1 提醒\n2 发件人\n3 摘要\n4 待办\n5 附件\n6 回复'}}]}).encode())
            api_server=ThreadingHTTPServer(('127.0.0.1',0),APIHandler)
            api_thread=threading.Thread(target=api_server.serve_forever,daemon=True); api_thread.start()
            try:
                app.ai_provider.set('api'); app.api_base.set('http://127.0.0.1:%d/v1'%api_server.server_port)
                app.api_model.set('synthetic-model'); app.api_key.set('SYNTHETIC-API-KEY')
                assert app.save_ai_settings(),app.ai_detail.get()
                assert app.api_key.get()==''
                assert 'SYNTHETIC-API-KEY' not in (app.directory/'config.json').read_text()
                assert 'SYNTHETIC-API-KEY' not in app.api_key_path(app.api_base.get()+'/chat/completions').read_bytes().decode(errors='ignore')
                assert '6 回复' in APIAnalyzer(app.config,app.api_secret)({'subject':'synthetic'},threading.Event())
                assert api_requests[0]['messages'][0]['content']==ANALYSIS_PROMPT+json.dumps({'subject':'synthetic'},ensure_ascii=False)
                assert app.command==[], 'API self-test must not require Codex'
            finally:
                api_server.shutdown(); api_server.server_close(); api_thread.join()
            result['checks'].append('API settings DPAPI encryption, no plaintext key, packaged HTTP call and original prompt without Codex')
            assert len(app.notified)==2, 'New and completed notifications must both dispatch'
            app.tray.remove_notification()
            result['checks'].append('real Windows pystray startup, visibility, notify/remove APIs and queue dispatch')
            app.events.put({'status':'运行中','detail':'模拟新来信已整理，真实邮件与授权码未用于测试。'}); app.drain(); root.update()
            assert app.status.get()=='运行中'; app.events.put({'status':'已暂停'}); app.drain(); root.update(); assert app.toggle.cget('text')=='开始监听'
            app.on_close(); root.update(); assert root.state()=='withdrawn'; app.restore(); root.update()
            if screenshot:
                root.update(); x=root.winfo_rootx(); y=root.winfo_rooty(); width=root.winfo_width(); height=root.winfo_height()
                left,top,right,bottom=platform.work_area()
                assert x>=left and y>=top and x+width<=right and y+height<=bottom, 'Window does not fit desktop work area'
                for control in (app.toggle,app.check_button):
                    assert control.winfo_rooty()+control.winfo_height()<=y+height, 'Action button clipped below window'
                    assert control.winfo_rootx()+control.winfo_width()<=x+width, 'Action button clipped at window edge'
                assert app.report_container.winfo_height()>=height*.9, 'Reports must occupy full window height'
                assert app.report_container.winfo_rootx()>x+width*.3, 'Reports must be in the right pane'
                assert app.reports.winfo_height()>=height*.55, 'Report list is too short'
                Path(screenshot).parent.mkdir(parents=True,exist_ok=True); ImageGrab.grab(bbox=(x,y,x+width,y+height)).save(screenshot)
                app.notebook.select(1); root.update()
                assert app.ai_save_button.winfo_rooty()+app.ai_save_button.winfo_height()<=y+height, 'AI save button clipped'
                assert app.ai_test_button.winfo_rooty()+app.ai_test_button.winfo_height()<=y+height, 'AI test button clipped'
                assert app.api_key_entry.winfo_rooty()+app.api_key_entry.winfo_height()<=app.ai_canvas.winfo_rooty()+app.ai_canvas.winfo_height(), 'API key input clipped below settings viewport'
                # The first report must actually be visible, not hidden by a sibling frame.
                first_row=app.reports.bbox(app.reports.get_children()[0])
                assert first_row, 'First report row has no visible bounding box'
                row_x=app.reports.winfo_rootx()+first_row[0]+10
                row_y=app.reports.winfo_rooty()+first_row[1]+first_row[3]//2
                assert root.winfo_containing(row_x,row_y)==app.reports, 'Report table covered by another widget'
                time_cell=app.reports.bbox(app.reports.get_children()[0],'time')
                assert time_cell[0]+time_cell[2]<=app.reports.winfo_width(), 'Receipt time column clipped'
                ImageGrab.grab(bbox=(x,y,x+width,y+height)).save(str(Path(screenshot).with_name(Path(screenshot).stem+'-settings.png')))
            app.exit(); app=None; result['checks'].append('actual Tk window, full-height right report pane, visible actions, close/restore/exit, screenshot')
            result['ok']=True
    except Exception:
        result['error']=traceback.format_exc()
    finally:
        if app is not None:
            if app.tray: app.tray.stop()
            try: app.root.destroy()
            except Exception: pass
    Path(result_path).parent.mkdir(parents=True,exist_ok=True)
    Path(result_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1

def main():
    if '--bridge' in sys.argv:
        parser=argparse.ArgumentParser()
        parser.add_argument('--bridge',action='store_true')
        parser.add_argument('--launcher')
        parser.add_argument('--fixture')
        args=parser.parse_args()
        from benson_mail.bridge import run
        run(args.launcher,args.fixture)
        return 0
    from benson_mail.app_icon import set_process_identity
    set_process_identity(Path(sys.executable).name.startswith('Uninstall-BensonMail-'))
    if Path(sys.executable).name.startswith('Uninstall-BensonMail-'):
        from benson_mail.uninstall import cli as uninstall
        return uninstall()
    parser=argparse.ArgumentParser(); parser.add_argument('--self-test'); parser.add_argument('--screenshot'); parser.add_argument('--background',action='store_true'); args=parser.parse_args()
    if args.self_test: return self_test(args.self_test,args.screenshot)
    import tkinter as tk
    from tkinter import messagebox
    from benson_mail import platform_windows as platform
    from benson_mail.ui import Application
    root=tk.Tk(); root.withdraw()
    if sys.platform!='win32': messagebox.showerror('需要 Windows','正式运行支持 Windows 10/11 x64。',parent=root); root.destroy(); return 1
    instance=platform.SingleInstance()
    if instance.already_running:
        messagebox.showinfo('已经运行','邮件小秘书已经运行，请在右下角托盘点击蓝色信封打开。',parent=root); root.destroy(); instance.close(); return 0
    try:
        app=Application(root,platform.app_dir()); root.deiconify()
        if args.background and app.tray: root.withdraw()
        if app.config.get('enabled'): root.after(500,app.toggle_service)
        root.mainloop()
    finally: instance.close()
    return 0

if __name__=='__main__': sys.exit(main())
