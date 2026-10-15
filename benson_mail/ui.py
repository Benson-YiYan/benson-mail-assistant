import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .core import Service, IMAPMailbox, save_json
from . import platform_windows as platform
from .report_index import report_entry, matches

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
        notebook=ttk.Notebook(frame); notebook.pack(fill='both',expand=True)
        settings_shell=ttk.Frame(notebook); reports_page=ttk.Frame(notebook,padding=10)
        settings_canvas=tk.Canvas(settings_shell,highlightthickness=0)
        settings_scroll=ttk.Scrollbar(settings_shell,orient='vertical',command=settings_canvas.yview)
        settings_scroll.pack(side='right',fill='y'); settings_canvas.pack(side='left',fill='both',expand=True)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_page=ttk.Frame(settings_canvas,padding=10)
        settings_window=settings_canvas.create_window((0,0),window=settings_page,anchor='nw')
        settings_page.bind('<Configure>',lambda _:settings_canvas.configure(scrollregion=settings_canvas.bbox('all')))
        settings_canvas.bind('<Configure>',lambda event:settings_canvas.itemconfigure(settings_window,width=event.width))
        notebook.add(reports_page,text='邮件报告'); notebook.add(settings_shell,text='邮箱与设置')
        form=ttk.Frame(settings_page); form.pack(fill='x')
        self.account=tk.StringVar(value=self.config.get('account','')); self.password=tk.StringVar(); self.output=tk.StringVar(value=self.config.get('output_dir','')); self.command=self.config.get('codex_command',[])
        for row,(label,var) in enumerate([('163 邮箱地址',self.account),('POP3/IMAP/SMTP 授权码',self.password),('报告保存文件夹',self.output)]):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=6)
            ttk.Entry(form,textvariable=var,show='●' if row==1 else '').grid(row=row,column=1,sticky='ew',padx=10)
        form.columnconfigure(1,weight=1)
        ttk.Button(form,text='浏览……',command=self.choose_folder).grid(row=2,column=2)
        ttk.Button(form,text='选择 Codex 程序',command=self.choose_codex).grid(row=3,column=1,sticky='w',pady=6)
        self.codex_label=tk.StringVar(value='Codex：'+('已配置' if self.command else '等待自动查找'))
        ttk.Label(settings_page,textvariable=self.codex_label).pack(anchor='w')
        self.auto=tk.BooleanVar(value=self.config.get('autostart',False)); ttk.Checkbutton(settings_page,text='登录 Windows 后自动启动',variable=self.auto,command=self.save_settings).pack(anchor='w',pady=8)
        ttk.Label(settings_page,text='在163邮箱设置中启用 IMAP 并生成授权码；不要填写邮箱登录密码。\n授权码由 Windows 当前用户加密保存，留空保留已保存的授权码。',wraplength=650).pack(anchor='w',pady=6)
        ttk.Button(settings_page,text='保存邮箱设置',command=self.save_settings).pack(anchor='w')
        ttk.Label(settings_page,text='来信及可读取的附件内容将交给您已登录的 Codex 服务分析。\n不会自动回复；不会把邮件标记为已读。',wraplength=650).pack(anchor='w',pady=6)
        interval_row=ttk.Frame(frame); interval_row.pack(fill='x',pady=6)
        self.interval=tk.StringVar(value=str(self.config.get('interval',60)))
        ttk.Label(interval_row,text='自定义检查间隔').pack(side='left')
        ttk.Entry(interval_row,textvariable=self.interval,width=8).pack(side='left',padx=6)
        ttk.Label(interval_row,text='秒').pack(side='left')
        ttk.Button(interval_row,text='应用间隔',command=self.apply_interval).pack(side='left',padx=6)
        controls=ttk.Frame(frame); controls.pack(fill='x',pady=8)
        self.toggle=ttk.Button(controls,text='开始监听',command=self.toggle_service); self.toggle.pack(side='left')
        ttk.Button(controls,text='测试连接',command=self.test_connections).pack(side='left',padx=8)
        self.check_button=ttk.Button(controls,text='立即检查',command=self.check_now); self.check_button.pack(side='left',padx=8)
        ttk.Button(controls,text='打开邮件文件夹',command=self.open_folder).pack(side='left')
        ttk.Button(controls,text='退出程序',command=self.exit).pack(side='right')
        # Pack the resizable report area last so it cannot push controls off-screen.
        notebook.pack_forget(); notebook.pack(fill='both',expand=True,pady=(8,0))
        self.search=tk.StringVar(); self.sender_filter=tk.StringVar(); self.start_day=tk.StringVar(); self.end_day=tk.StringVar(); self.attachment_filter=tk.StringVar(value='全部')
        search_row=ttk.Frame(reports_page); search_row.pack(fill='x')
        ttk.Label(search_row,text='搜索').pack(side='left')
        ttk.Entry(search_row,textvariable=self.search).pack(side='left',fill='x',expand=True,padx=6)
        ttk.Label(reports_page,text='搜索正文、发送者、附件名及主题（本机已保存邮件）').pack(anchor='w',pady=4)
        filters=ttk.Frame(reports_page); filters.pack(fill='x',pady=5)
        ttk.Label(filters,text='发件人').pack(side='left'); ttk.Entry(filters,textvariable=self.sender_filter,width=18).pack(side='left',padx=6)
        ttk.Label(filters,text='附件').pack(side='left'); ttk.Combobox(filters,textvariable=self.attachment_filter,values=['全部','有附件','无附件'],state='readonly',width=9).pack(side='left',padx=6)
        days=ttk.Frame(reports_page); days.pack(fill='x',pady=5)
        ttk.Label(days,text='收到日期').pack(side='left')
        ttk.Entry(days,textvariable=self.start_day,width=12).pack(side='left',padx=6)
        ttk.Label(days,text='至').pack(side='left'); ttk.Entry(days,textvariable=self.end_day,width=12).pack(side='left',padx=6)
        ttk.Label(days,text='YYYY-MM-DD，留空不限').pack(side='left')
        ttk.Button(days,text='重置',command=self.reset_filters).pack(side='right')
        self.reports=ttk.Treeview(reports_page,columns=('subject','sender','time'),show='headings',height=5)
        for name,label,width in [('subject','邮件主题',280),('sender','发件人',160),('time','收到时间（北京）',155)]:
            self.reports.heading(name,text=label); self.reports.column(name,width=width,minwidth=60)
        self.reports.pack(fill='both',expand=True); self.reports.bind('<Double-1>',self.open_report); self.report_paths=[]
        for var in (self.search,self.sender_filter,self.start_day,self.end_day,self.attachment_filter): var.trace_add('write',lambda *_:self.refresh_reports())
        root.protocol('WM_DELETE_WINDOW',self.on_close); root.after(100,self.drain)
        if not self_test:
            if not self.output.get(): self.output.set(str(platform.documents_dir()/'邮件'))
            if self.account.get() and (self.directory/'secret.bin').exists():
                try: self.secret=platform.load_secret(self.directory/'secret.bin',self.account.get())
                except OSError: self.detail.set('授权码无法解密，请重新填写。')
            self.create_tray(); threading.Thread(target=self.find_codex,daemon=True).start(); self.refresh_reports()
            if not self.account.get() or not self.secret: root.after(250,self.show_onboarding)
    def show_onboarding(self):
        dialog=tk.Toplevel(self.root); dialog.title('首次使用 · 连接163邮箱'); dialog.transient(self.root); dialog.grab_set()
        panel=ttk.Frame(dialog,padding=24); panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='欢迎使用邮件小秘书',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w',pady=6)
        ttk.Label(panel,text='邮箱地址').pack(anchor='w'); ttk.Entry(panel,textvariable=self.account,width=42).pack(fill='x',pady=6)
        ttk.Label(panel,text='POP3/IMAP/SMTP 授权码').pack(anchor='w'); ttk.Entry(panel,textvariable=self.password,show='●').pack(fill='x',pady=6)
        ttk.Label(panel,text='在163邮箱设置中开启IMAP并生成授权码。\n这里填授权码，不是邮箱登录密码。',wraplength=400).pack(anchor='w',pady=8)
        def save():
            if self.save_settings() and self.secret: dialog.destroy(); self.detail.set('邮箱已保存，请测试连接并开始监听。')
        ttk.Button(panel,text='保存邮箱设置',command=save).pack(anchor='w')
    def apply_interval(self):
        try:
            seconds=int(self.interval.get())
            if not 10<=seconds<=86400: raise ValueError()
        except ValueError:
            messagebox.showerror('间隔无效','请输入10到86400之间的整数秒数。',parent=self.root); return
        if not self.save_settings(): return
        if self.service: self.service.set_interval(seconds)
        self.detail.set(f'已保存：每{seconds}秒检查；无新邮件不调用AI。')
    def check_now(self):
        if not self.service or not self.service.thread or not self.service.thread.is_alive():
            self.detail.set('请先开始监听，再点击立即检查。'); return
        self.check_button.configure(state='disabled',text='检查中…'); self.detail.set('已请求检查，正在连接邮箱…'); self.service.request_check()
    def reset_filters(self):
        for var in (self.search,self.sender_filter,self.start_day,self.end_day): var.set('')
        self.attachment_filter.set('全部')
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
        account=self.account.get().strip().lower()
        import re
        if not re.fullmatch(r'[a-z0-9._%+\-]+@163\.com',account):
            messagebox.showerror('邮箱地址无效','请输入完整的163邮箱地址，例如 name@163.com。',parent=self.root); return False
        active=bool(self.service and self.service.thread and self.service.thread.is_alive())
        if active and account!=self.config.get('account'):
            messagebox.showinfo('请先暂停','请暂停监听，等当前邮件处理完成后再更换邮箱。',parent=self.root); return False
        if not self.password.get() and (not self.secret or account!=self.config.get('account')):
            messagebox.showerror('缺少授权码','请填写 POP3/IMAP/SMTP 授权码。',parent=self.root); return False
        try:
            seconds=int(self.interval.get())
            if not 10<=seconds<=86400: raise ValueError('interval')
            if self.password.get(): platform.save_secret(self.directory/'secret.bin',account,self.password.get()); self.secret=self.password.get(); self.password.set('')
            elif account!=self.config.get('account'):
                self.secret=''
            platform.set_autostart(self.auto.get())
            self.config={'account':account,'host':'imap.163.com','output_dir':self.output.get(),'codex_command':self.command,'autostart':self.auto.get(),'interval':seconds,'enabled':bool(self.service and not self.service.cancel.is_set())}
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
            if event.get('status') in ('正在检查','正在分析'): self.check_button.configure(state='disabled',text='检查中…')
            if event.get('check_done') or event.get('status')=='已暂停': self.check_button.configure(state='normal',text='立即检查')
            if 'detail' in event: self.detail.set(event['detail'])
            if event.get('status')=='已暂停':
                self.toggle.configure(text='开始监听',state='normal'); self.config['enabled']=False
                if not self.self_test: save_json(self.directory/'config.json',self.config)
            if 'notification' in event: self.notify(event['notification'])
            if 'report' in event: self.refresh_reports()
        if not self.exiting: self.root.after(100,self.drain)
    def refresh_reports(self):
        paths=sorted(Path(self.output.get()).glob('*/*.txt'),key=lambda p:p.stat().st_mtime,reverse=True) if self.output.get() else []
        selected=self.reports.selection()
        self.reports.delete(*self.reports.get_children())
        self.report_paths=[]
        for path in paths:
            entry=report_entry(path)
            if not matches(entry,self.search.get(),self.sender_filter.get(),self.start_day.get(),self.end_day.get(),self.attachment_filter.get()): continue
            self.report_paths.append(path)
            self.reports.insert('', 'end',iid=str(path),values=(entry['title'],entry['sender'],entry['time']))
        if selected and self.reports.exists(selected[0]): self.reports.selection_set(selected[0])
    def open_folder(self):
        try: path=Path(self.output.get()); path.mkdir(parents=True,exist_ok=True); os.startfile(path)
        except Exception: messagebox.showerror('无法打开','请重新选择有写入权限的文件夹。',parent=self.root)
    def open_report(self,event=None):
        selected=self.reports.selection()
        if selected: os.startfile(selected[0])
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
