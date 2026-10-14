import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .core import Service, IMAPMailbox, save_json
from . import platform_windows as platform

class Application:
    def __init__(self,root,directory,config=None,self_test=False):
        self.root=root; self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True); self.self_test=self_test
        self.config=config or (json.loads((self.directory/'config.json').read_text(encoding='utf-8')) if (self.directory/'config.json').exists() else {})
        self.events=queue.Queue(); self.service=None; self.tray=None; self.exiting=False; self.secret=''; self.notified=set(); self.tray_ready=threading.Event()
        root.title('Benson 邮件小秘书')
        if os.name=='nt': left,top,right,bottom=platform.work_area()
        else: left,top,right,bottom=0,0,root.winfo_screenwidth(),root.winfo_screenheight()
        width=min(780,max(400,right-left-40)); height=min(630,max(400,bottom-top-80))
        root.geometry(f'{width}x{height}+{left+20}+{top+20}'); root.minsize(min(700,width),min(560,height))
        style=ttk.Style(root); style.theme_use('clam'); style.configure('TLabel',font=('Microsoft YaHei UI',10)); style.configure('TButton',font=('Microsoft YaHei UI',10),padding=7)
        frame=ttk.Frame(root,padding=22); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='邮件小秘书',font=('Microsoft YaHei UI',22,'bold')).pack(anchor='w')
        ttk.Label(frame,text='新来信自动整理成中文报告，您决定如何回复。').pack(anchor='w',pady=(5,12))
        self.status=tk.StringVar(value='已暂停'); self.detail=tk.StringVar(value='填写邮箱与授权码，然后测试连接。')
        ttk.Label(frame,textvariable=self.status,font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w'); ttk.Label(frame,textvariable=self.detail,wraplength=710).pack(anchor='w',pady=8)
        form=ttk.Frame(frame); form.pack(fill='x')
        self.account=tk.StringVar(value=self.config.get('account','')); self.password=tk.StringVar(); self.output=tk.StringVar(value=self.config.get('output_dir','')); self.command=self.config.get('codex_command',[])
        for row,(label,var) in enumerate([('163 邮箱',self.account),('客户端授权码',self.password),('报告保存文件夹',self.output)]):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=6)
            ttk.Entry(form,textvariable=var,show='●' if row==1 else '').grid(row=row,column=1,sticky='ew',padx=10)
        form.columnconfigure(1,weight=1)
        ttk.Button(form,text='选择文件夹',command=self.choose_folder).grid(row=2,column=2)
        ttk.Button(form,text='选择 Codex 程序',command=self.choose_codex).grid(row=3,column=1,sticky='w',pady=6)
        self.codex_label=tk.StringVar(value='Codex：'+('已配置' if self.command else '等待自动查找'))
        ttk.Label(frame,textvariable=self.codex_label).pack(anchor='w')
        self.auto=tk.BooleanVar(value=self.config.get('autostart',False)); ttk.Checkbutton(frame,text='登录 Windows 后自动启动',variable=self.auto,command=self.save_settings).pack(anchor='w',pady=8)
        ttk.Label(frame,text='开始前请知悉：来信及可读取的附件内容将交给您已登录的 Codex 服务分析。\n不会自动回复；不会把邮件标记为已读。',wraplength=710).pack(anchor='w',pady=6)
        controls=ttk.Frame(frame); controls.pack(fill='x',pady=8)
        self.toggle=ttk.Button(controls,text='开始监听',command=self.toggle_service); self.toggle.pack(side='left')
        ttk.Button(controls,text='测试连接',command=self.test_connections).pack(side='left',padx=8)
        ttk.Button(controls,text='打开邮件文件夹',command=self.open_folder).pack(side='left')
        ttk.Button(controls,text='退出程序',command=self.exit).pack(side='right')
        ttk.Label(frame,text='最近报告（双击打开）').pack(anchor='w',pady=(10,3))
        self.reports=tk.Listbox(frame,height=5,font=('Microsoft YaHei UI',10)); self.reports.pack(fill='both',expand=True); self.reports.bind('<Double-1>',self.open_report); self.report_paths=[]
        root.protocol('WM_DELETE_WINDOW',self.on_close); root.after(100,self.drain)
        if not self_test:
            if not self.output.get(): self.output.set(str(platform.documents_dir()/'邮件'))
            if self.account.get() and (self.directory/'secret.bin').exists():
                try: self.secret=platform.load_secret(self.directory/'secret.bin',self.account.get())
                except OSError: self.detail.set('授权码无法解密，请重新填写。')
            self.create_tray(); threading.Thread(target=self.find_codex,daemon=True).start(); self.refresh_reports()
    def find_codex(self):
        command=self.command if platform.verify_codex(self.command) else platform.discover_codex()
        self.events.put({'command':command})
    def choose_folder(self):
        chosen=filedialog.askdirectory(parent=self.root)
        if chosen: self.output.set(chosen)
    def choose_codex(self):
        chosen=filedialog.askopenfilename(parent=self.root,title='选择 Codex 命令行程序（通常在 resources 文件夹）',filetypes=[('Codex 程序','*.exe *.cmd'),('所有文件','*')])
        if chosen:
            command=platform.resolve_cli(chosen)
            def check(): self.events.put({'command':command if platform.verify_codex(command) else [],'detail':'若未找到：先安装并登录 Codex；选择 resources 下的命令行 codex.exe。桌面主程序不适用。'})
            threading.Thread(target=check,daemon=True).start()
    def save_settings(self):
        if self.self_test: return True
        account=self.account.get().strip()
        if not account: return False
        try:
            if self.password.get(): platform.save_secret(self.directory/'secret.bin',account,self.password.get()); self.secret=self.password.get(); self.password.set('')
            elif account!=self.config.get('account'):
                self.secret=''
            platform.set_autostart(self.auto.get())
            self.config={'account':account,'host':'imap.163.com','output_dir':self.output.get(),'codex_command':self.command,'autostart':self.auto.get(),'enabled':bool(self.service and not self.service.cancel.is_set())}
            save_json(self.directory/'config.json',self.config); return True
        except Exception: messagebox.showerror('未保存','设置保存失败，请检查文件夹权限或重新填写授权码。',parent=self.root); return False
    def toggle_service(self):
        if self.service and self.service.thread and self.service.thread.is_alive(): self.service.stop(); self.toggle.configure(state='disabled'); return
        if not self.save_settings(): return
        if not self.secret or not self.command or not self.output.get(): messagebox.showinfo('还差一步','请填写授权码、选择保存文件夹，并测试 Codex 连接。',parent=self.root); return
        self.service=Service(self.config,self.secret,self.directory/'state',self.events.put); self.service.start(); self.toggle.configure(text='暂停监听'); self.config['enabled']=True; save_json(self.directory/'config.json',self.config)
    def test_connections(self):
        if not self.save_settings(): return
        self.detail.set('正在分别检查邮箱和 Codex，请稍候…')
        config=dict(self.config); secret=self.secret; command=list(self.command)
        def work():
            try:
                mailbox=IMAPMailbox(config,secret); mailbox.snapshot(); mailbox.close(); email_ok=True
            except Exception: email_ok=False
            codex_ok=platform.verify_codex(command)
            if codex_ok:
                try:
                    import subprocess
                    result=subprocess.run(command+['login','status'],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)); codex_ok=result.returncode==0
                except Exception: codex_ok=False
            self.events.put({'status':'连接检查完成','detail':('邮箱：正常。' if email_ok else '邮箱：失败，请检查 163 设置中 IMAP 是否开启、授权码是否正确。')+(' Codex：已登录。' if codex_ok else ' Codex：请打开桌面应用登录；重新选择命令行程序后重试。')})
        threading.Thread(target=work,daemon=True).start()
    def drain(self):
        while True:
            try: event=self.events.get_nowait()
            except queue.Empty: break
            if event.get('action')=='restore': self.restore()
            elif event.get('action')=='toggle': self.toggle_service()
            elif event.get('action')=='exit': self.exit()
            if 'command' in event: self.command=event['command'] or []; self.codex_label.set('Codex：'+('已找到命令行程序' if self.command else '未找到，请点击选择 Codex 程序'))
            if 'status' in event: self.status.set(event['status'])
            if 'detail' in event: self.detail.set(event['detail'])
            if event.get('status')=='已暂停':
                self.toggle.configure(text='开始监听',state='normal'); self.config['enabled']=False
                if not self.self_test: save_json(self.directory/'config.json',self.config)
            if 'notification' in event: self.notify(event['notification'])
            if 'report' in event: self.refresh_reports()
        if not self.exiting: self.root.after(100,self.drain)
    def refresh_reports(self):
        self.report_paths=sorted(Path(self.output.get()).glob('*/*.txt'),key=lambda p:p.stat().st_mtime,reverse=True)[:30] if self.output.get() else []
        self.reports.delete(0,'end')
        for path in self.report_paths: self.reports.insert('end',path.name)
    def open_folder(self):
        try: path=Path(self.output.get()); path.mkdir(parents=True,exist_ok=True); os.startfile(path)
        except Exception: messagebox.showerror('无法打开','请重新选择有写入权限的文件夹。',parent=self.root)
    def open_report(self,event=None):
        selected=self.reports.curselection()
        if selected: os.startfile(self.report_paths[selected[0]])
    def create_tray(self):
        try:
            import pystray
            from PIL import Image,ImageDraw
            image=Image.new('RGB',(64,64),'#2058a5'); draw=ImageDraw.Draw(image); draw.rectangle((12,20,52,45),outline='white',width=3); draw.line((12,20,32,35,52,20),fill='white',width=3)
            def action(name): return lambda icon,item:self.events.put({'action':name})
            self.tray=pystray.Icon('BensonMail',image,'邮件小秘书',pystray.Menu(pystray.MenuItem('打开窗口',action('restore'),default=True),pystray.MenuItem('开始／暂停',action('toggle')),pystray.MenuItem('退出',action('exit'))))
            def setup(icon):
                icon.visible=True
                self.tray_ready.set()
            self.tray.run_detached(setup)
        except Exception: self.tray=None
    def notify(self,notice):
        if notice['id'] in self.notified: return
        self.notified.add(notice['id'])
        if self.tray and self.tray_ready.is_set():
            try: self.tray.notify(notice['message'][:240],notice['title'])
            except Exception:
                if getattr(self,'self_test',False): raise
                self.detail.set('报告照常保存；系统通知不可用，请查看最近报告。')
    def restore(self): self.root.deiconify(); self.root.lift(); self.root.focus_force()
    def on_close(self):
        if self.tray: self.root.withdraw()
        elif self.self_test: self.root.withdraw()
        else: self.exit()
    def exit(self):
        if self.exiting: return
        self.exiting=True; self.toggle.configure(state='disabled'); self.detail.set('正在停止，请稍候…')
        if self.service: self.service.stop()
        self.await_exit()
    def await_exit(self):
        if self.service and self.service.thread and self.service.thread.is_alive(): self.root.after(100,self.await_exit); return
        if self.tray: self.tray.stop()
        self.root.destroy()
