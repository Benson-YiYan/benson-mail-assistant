"""Fail-closed checks for sending Gmail content to a configured AI service."""


def require_gmail_ai_consent(config, *sources):
    profiles = config.get('mailboxes') or []
    if not profiles and config.get('mailbox'):
        profiles = [{'connection': config['mailbox']}]
    records = []

    def collect(value):
        if isinstance(value, dict):
            if any(key in value for key in ('mailbox_key', 'mailbox_account', 'account')):
                records.append(value)
            for key in ('original_mail', 'sources', 'selected_emails'):
                collect(value.get(key))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for source in sources:
        collect(source)
    targets = []
    for record in records:
        account = str(record.get('mailbox_account') or record.get('account') or '').strip().casefold()
        key = str(record.get('mailbox_key') or '')
        target = next((item for item in profiles
                       if (key and str(item.get('id') or item.get('mailbox_key') or '') == key)
                       or str(item.get('connection', item).get('account', '')).strip().casefold() == account), None)
        if target:
            connection = target.get('connection', target)
            if connection.get('mail_provider') == 'gmail':
                targets.append(connection)
        elif account.endswith('@gmail.com'):
            raise PermissionError(_denied(config))
    if not records:
        targets = [item.get('connection', item) for item in profiles
                   if item.get('connection', item).get('mail_provider') == 'gmail']
    if any(item.get('gmail_ai_consent') is not True for item in targets):
        raise PermissionError(_denied(config))


def _denied(config):
    messages = {
        'zh': '此 Gmail 账号尚未同意将邮件内容发送给所选 AI。请在该账号的邮箱设置中开启同意。',
        'en': 'This Gmail account has not consented to sending message content to the selected AI. Enable consent in this account’s mailbox settings.',
        'es': 'Esta cuenta de Gmail no ha aceptado enviar el contenido de sus mensajes a la IA elegida. Activa el consentimiento en la configuración de esta cuenta.',
        'chinglish': '兹斯·吉梅尔·阿考恩特·哈兹·诺特·孔森提德·图·森德·梅瑟吉·康腾特·图·泽·瑟莱克提德·诶艾. 恩艾博尔·孔森特·因·兹斯·阿考恩特兹·喵博克斯·塞听斯.',
    }
    return messages.get(config.get('ui_language', 'zh'), messages['zh'])
