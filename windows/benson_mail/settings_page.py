"""Whole-page settings plans: validate first, then commit with local rollback.

UI drafts are not persisted by validation. Secrets never appear in returned plans.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

from . import platform_windows as platform
from .ai_api import identity
from .mailbox_config import normalize, mailbox_id
from .notification_policy import normalize_preferences
from .assistant_tools import validate_usage_rates, _rate_binding


def _interval(value):
    if isinstance(value, bool): raise ValueError('检查间隔应为10至86400秒。')
    try:
        seconds = int(value)
    except (TypeError, ValueError): raise ValueError('检查间隔应为10至86400秒。') from None
    if str(seconds) != str(value).strip() or not 10 <= seconds <= 86400:
        raise ValueError('检查间隔应为10至86400秒。')
    return seconds


def _output_directory(config,data,plan):
    output=data.get('output_dir','')
    if not isinstance(output,str) or not output.strip(): raise ValueError('请选择报告保存文件夹。')
    directory=Path(output.strip()).expanduser()
    if directory.exists() and not directory.is_dir(): raise ValueError('请选择报告保存文件夹。')
    parent=directory
    while not parent.exists() and parent!=parent.parent:parent=parent.parent
    if not parent.is_dir() or not os.access(parent,os.W_OK):raise ValueError('Report folder is not writable.')
    plan['output']=directory
    config['output_dir']=str(directory)


def _mailbox_list(controller,config,profiles,data,plan,fields):
    drafts=data['mailboxes']
    if not isinstance(drafts,list) or len(drafts)>100: raise ValueError('Invalid mailbox list.')
    existing={mailbox_id(profile):profile for profile in profiles}
    saved=[];aliases={};seen=set();origins=set()
    for draft in drafts:
        if not isinstance(draft,dict):raise ValueError('Invalid mailbox list.')
        original_id=draft.get('original_id') or draft.get('id') or ''
        if original_id and original_id not in existing:raise ValueError('Mailbox draft refers to a missing original.')
        if original_id and original_id in origins:raise ValueError('Invalid mailbox list.')
        if original_id:origins.add(original_id)
        old=existing.get(original_id,{})
        merged={**old,**{key:value for key,value in draft.items() if key in fields}}
        # An implicit login follows a changed email address; an explicit custom login is preserved.
        if 'account' in draft and 'username' not in draft and old.get('username')==old.get('account'):
            merged.pop('username',None)
        connection=normalize(merged);identifier=mailbox_id(connection)
        if identifier in seen:raise ValueError('这个邮箱连接已存在，请从已添加邮箱中选择。')
        seen.add(identifier)
        enabled=draft.get('monitor_enabled',old.get('monitor_enabled',True))
        if not isinstance(enabled,bool):raise ValueError('Mailbox enabled must be a boolean.')
        secret=draft.get('secret','')
        if not isinstance(secret,str):raise ValueError('Invalid mailbox credential.')
        changed=not old or identifier!=original_id
        item={**connection,'monitor_enabled':enabled}
        if secret:
            binding='mailbox:'+identifier;relative='mail-secrets/'+identifier+'.bin'
            plan['secrets'].append((controller.root/relative,binding,secret))
            item.update(secret_binding=binding,mail_secret_file=relative)
        elif changed:
            raise ValueError('新邮箱或连接设置变更后，请重新填写密码、授权码或 OAuth2 访问令牌。')
        else:
            for key in ('secret_binding','mail_secret_file'):
                if key in old:item[key]=old[key]
            # Unchanged disabled accounts can remain without credentials; enabling needs a usable secret.
            if enabled and not controller.fixture and not controller.mailbox_secret(old):
                raise ValueError('Mailbox credentials are unavailable.')
        saved.append(item)
        aliases[identifier]=identifier
        if original_id:aliases[original_id]=identifier
        client_id=draft.get('client_id')
        if client_id is not None:
            if not isinstance(client_id,str) or not client_id or len(client_id)>100 or client_id in aliases:raise ValueError('Invalid mailbox draft identifier.')
            aliases[client_id]=identifier
    selected=data.get('selected_mailbox_id') or data.get('selected_id') or ''
    if not isinstance(selected,str):raise ValueError('Selected mailbox is missing from the draft list.')
    if selected:
        if selected not in aliases:raise ValueError('Selected mailbox is missing from the draft list.')
        selected=aliases[selected]
    elif config.get('account') and mailbox_id(config) in aliases:
        selected=aliases[mailbox_id(config)]
    else:selected=mailbox_id(saved[0]) if saved else ''
    config['mailboxes']=saved
    for key in fields:config.pop(key,None)
    if selected:
        chosen=next(profile for profile in saved if mailbox_id(profile)==selected)
        config.update({key:chosen[key] for key in fields if key in chosen})
    plan['selected_mailbox_id']=selected


def _validate(controller, page, data):
    from .bridge import MAIL_FIELDS
    if page not in ('mail', 'ai', 'general'): raise ValueError('Unknown settings page.')
    if not isinstance(data, dict): raise ValueError('Invalid settings values.')
    config = copy.deepcopy(controller.config)
    plan = {'page': page, 'config': config, 'secrets': [], 'output': None, 'policy': None, 'rates': None, 'autostart': None}
    if page == 'mail':
        controller.paused()
        profiles = config.get('mailboxes')
        if profiles is None:
            profiles = [{**{k:config[k] for k in MAIL_FIELDS if k in config}, 'monitor_enabled':True}] if config.get('account') else []
        previous_id = mailbox_id(config) if config.get('account') else None
        if 'mailboxes' in data:
            _mailbox_list(controller,config,profiles,data,plan,MAIL_FIELDS)
        else:
            # Compatibility for the one-mailbox setup wizard and old Save Mail button.
            connection = normalize(data)
            new_id = mailbox_id(connection)
            if any(mailbox_id(profile) == new_id and new_id != previous_id for profile in profiles):
                raise ValueError('这个邮箱连接已存在，请从已添加邮箱中选择。')
            secret = data.get('secret', '')
            if not isinstance(secret, str): raise ValueError('Invalid mailbox credential.')
            changed = previous_id != new_id
            if not secret and (changed or not controller.secret()):
                raise ValueError('新邮箱或连接设置变更后，请重新填写密码、授权码或 OAuth2 访问令牌。')
            if secret:
                binding = 'mailbox:' + new_id
                relative = 'mail-secrets/' + new_id + '.bin'
                plan['secrets'].append((controller.root / relative, binding, secret))
                config.update(secret_binding=binding, mail_secret_file=relative)
            config.update(connection)
            enabled = next((profile.get('monitor_enabled',True) for profile in profiles if mailbox_id(profile)==previous_id), True)
            config['mailboxes'] = [profile for profile in profiles if mailbox_id(profile)!=previous_id] + [{**{k:config[k] for k in MAIL_FIELDS if k in config}, 'monitor_enabled':enabled}]
        if 'output_dir' in data:
            _output_directory(config,data,plan)
        elif 'mailboxes' not in data:
            raise ValueError('请选择报告保存文件夹。')
        if 'autostart' in data:
            autostart=data['autostart']
            if not isinstance(autostart,bool):raise ValueError('Autostart must be a boolean.')
            config['autostart']=autostart;plan['autostart']=autostart
        if 'seconds' in data or 'interval' in data: config['interval'] = _interval(data.get('seconds',data.get('interval')))
        if 'mail_policy' in data:
            from .mail_policy import validate_policy
            plan['policy'] = validate_policy(data['mail_policy'])
            config['mail_policy'] = plan['policy']
    elif page == 'ai':
        controller.paused()
        provider = data.get('ai_provider')
        if provider not in ('api','codex','deepseek_harness'): raise ValueError('请选择分析方式。')
        base = data.get('api_base','').strip(); model = data.get('api_model','').strip()
        key = data.get('key','').strip()
        harness = data.get('harness_path','').strip()
        if provider == 'api':
            binding = identity(base)
            if not model: raise ValueError('请填写模型名。')
            path = controller.key_path(base)
            if key: plan['secrets'].append((path,binding,key))
            elif not path.exists() or not platform.load_secret(path,binding): raise ValueError('请填写此基础地址的 API Key。')
        if provider == 'deepseek_harness':
            from .deepseek_harness_ai import discover
            discover(harness)
        if provider == 'codex' and 'codex_path' in data:
            cli_path=data.get('codex_path','')
            if not isinstance(cli_path,str):raise ValueError('Invalid Codex launcher path.')
            cli_path=cli_path.strip()
            command=platform.resolve_cli(cli_path) if cli_path else config.get('codex_command') or platform.discover_codex()
            if not platform.verify_codex(command):raise ValueError('未找到可用的 Codex 命令行程序，请选择 resources 下的 codex.exe。')
            config['codex_command']=command
        config.update(ai_provider=provider, api_base=base, api_model=model, harness_path=harness)
        if 'rates' in data:
            rate = validate_usage_rates(data['rates']);rate['model']=model
            plan['rates'] = (_rate_binding(model,base),rate)
    else:
        if 'output_dir' in data: _output_directory(config,data,plan)
        preferences = normalize_preferences({
            'notifications_enabled':data.get('notifications_enabled',config.get('notifications_enabled',True)),
            'quiet_hours':data.get('quiet_hours',config.get('quiet_hours',{}))})
        config.update({key:preferences[key] for key in ('notifications_enabled','quiet_hours')})
        if 'autostart' in data:
            if not isinstance(data['autostart'],bool): raise ValueError('Autostart must be a boolean.')
            config['autostart']=data['autostart'];plan['autostart']=data['autostart']
        if 'ui_language' in data:
            if data['ui_language'] not in ('zh','en','es'): raise ValueError('Invalid interface language')
            config['ui_language']=data['ui_language']
    return plan


def _commit(controller, page, data):
    # No directory, credential, policy, registry or file mutation happens before this returns.
    plan = validate(controller,page,data)
    root = controller.root
    original_config = copy.deepcopy(controller.config)
    backups = {}
    created_dirs = []
    registry_attempted = False
    def remember(path):
        path=Path(path)
        if path not in backups: backups[path] = path.read_bytes() if path.exists() else None
    def create_parents(path):
        missing=[];current=Path(path)
        while not current.exists() and current!=current.parent:
            missing.append(current);current=current.parent
        for folder in reversed(missing):
            folder.mkdir();created_dirs.append(folder)
    remember(controller.path)
    for path,_,_ in plan['secrets']: remember(path)
    if plan['policy'] is not None: remember(root/'blocked_mail'/'state.json')
    if plan['rates'] is not None: remember(root/'usage-rates.json')
    try:
        if plan['output'] is not None: create_parents(plan['output'])
        for path,binding,secret in plan['secrets']:
            create_parents(path.parent)
            platform.save_secret(path,binding,secret)
        if plan['policy'] is not None:
            from .mail_policy import policy_save
            policy_save(root,plan['policy'])
        if plan['rates'] is not None:
            from .assistant_tools import _chat
            path=root/'usage-rates.json'
            saved=json.loads(path.read_text()) if path.exists() else {'rates':{}}
            binding,rate=plan['rates'];saved.setdefault('rates',{})[binding]=rate
            _chat()._atomic(path,json.dumps(saved))
        if plan['autostart'] is not None and not controller.fixture:
            registry_attempted=True
            platform.set_autostart(plan['autostart'],launcher=controller.launcher)
        controller.config=plan['config']
        controller.persist()
    except Exception:
        controller.config=original_config
        for path,old in backups.items():
            if old is None: path.unlink(missing_ok=True)
            else:
                from .assistant_tools import _chat
                path.parent.mkdir(parents=True,exist_ok=True)
                # Preserve encrypted bytes exactly; use binary staging for secret stores.
                temporary=path.with_name('.'+path.name+'.rollback')
                temporary.write_bytes(old);os.replace(temporary,path)
        if registry_attempted:
            try: platform.set_autostart(bool(original_config.get('autostart')),launcher=controller.launcher)
            except Exception: pass
        for folder in reversed(created_dirs):
            try: folder.rmdir()
            except OSError: pass
        raise
    # Only expose the new live settings after the entire page has committed.
    for service in controller.all_services():
        for key in ('interval','notifications_enabled','quiet_hours','ui_language','mail_policy','output_dir'):
            if key in controller.config: service.config[key]=copy.deepcopy(controller.config[key])
        if hasattr(service.analyzer,'config') and 'ui_language' in controller.config:
            service.analyzer.config['ui_language']=controller.config['ui_language']
        if page=='mail' and ('seconds' in data or 'interval' in data): service.set_interval(controller.config['interval'])
    result={'saved':True,'page':page}
    if 'selected_mailbox_id' in plan:result['selected_mailbox_id']=plan['selected_mailbox_id']
    return result


_SETTINGS_ERRORS = {
    'Invalid Codex launcher path.': ('Codex 启动器路径无效。', 'La ruta del iniciador de Codex no es válida.'),
    'Invalid mailbox list.': ('邮箱列表无效，请重新填写。', 'La lista de buzones no es válida.'),
    'Mailbox draft refers to a missing original.': ('草稿引用的原邮箱已不存在，请重新打开设置。', 'El buzón original del borrador ya no existe. Vuelve a abrir Configuración.'),
    'Mailbox enabled must be a boolean.': ('邮箱监听选项必须为开或关。', 'La opción de escucha del buzón debe estar activada o desactivada.'),
    'Invalid mailbox draft identifier.': ('邮箱草稿标识无效。', 'El identificador del borrador de buzón no es válido.'),
    'Selected mailbox is missing from the draft list.': ('所选邮箱不在草稿列表中，请重新选择。', 'El buzón seleccionado no figura en la lista del borrador. Selecciónalo de nuevo.'),
    'Unknown settings page.': ('未知设置页面。', 'Página de configuración desconocida.'),
    'Invalid settings values.': ('设置内容无效，请重新填写。', 'Los valores de configuración no son válidos.'),
    'Invalid mailbox credential.': ('邮箱凭据无效，请重新填写。', 'Las credenciales del buzón no son válidas.'),
    'Report folder is not writable.': ('报告保存文件夹无法写入，请选择其他位置。', 'No se puede escribir en la carpeta de informes. Elige otra ubicación.'),
    'Autostart must be a boolean.': ('开机启动选项必须为开或关。', 'La opción de inicio automático debe estar activada o desactivada.'),
    'Invalid interface language': ('界面语言无效。', 'El idioma de la interfaz no es válido.'),
    'Time must use HH:mm (00:00–23:59)': ('时间请填写为 HH:mm（00:00–23:59）。', 'La hora debe tener el formato HH:mm (00:00–23:59).'),
    'notifications_enabled must be a boolean': ('系统通知选项必须为开或关。', 'La opción de notificaciones debe estar activada o desactivada.'),
    'quiet_hours.enabled must be a boolean': ('免打扰选项必须为开或关。', 'La opción No molestar debe estar activada o desactivada.'),
}


def _call(controller, function, page, data):
    from .runtime_i18n import using_language
    from .assistant_tools import _ERROR_TEXT
    language=controller.config.get('ui_language','zh')
    try:
        with using_language(language): return function(controller,page,data)
    except (ValueError,RuntimeError) as error:
        translated=_SETTINGS_ERRORS.get(str(error)) or _ERROR_TEXT.get(str(error))
        if translated and language in ('zh','es'):
            raise type(error)(translated[0 if language=='zh' else 1]) from None
        raise


def validate(controller, page, data):
    return _call(controller,_validate,page,data)


def commit(controller, page, data):
    return _call(controller,_commit,page,data)
