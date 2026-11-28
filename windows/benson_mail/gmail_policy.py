"""Fail-closed consent checks before Gmail message content is sent to AI."""


def _profiles(config):
    profiles = config.get('mailboxes')
    if isinstance(profiles, list):
        return profiles
    return [config]


def _source_records(values):
    for value in values:
        if not isinstance(value, dict):
            continue
        if any(key in value for key in ('mailbox_key', 'mailbox_account', 'account')):
            yield value
        for key in ('original_mail', 'sources', 'selected_emails'):
            nested = value.get(key)
            if isinstance(nested, dict):
                yield from _source_records((nested,))
            elif isinstance(nested, list):
                yield from _source_records(nested)


def _denied(config):
    language = config.get('ui_language', 'zh')
    messages = {
        'zh': '此 Gmail 账号尚未允许将邮件正文和可读取的附件文字发送给 AI。请在邮箱设置中开启授权；关闭后会停止后续发送。',
        'en': 'This Gmail account has not consented to sending message bodies and readable attachment text to AI. Enable consent in mailbox settings; turning it off stops future transfers.',
        'es': 'Esta cuenta de Gmail no ha autorizado enviar a la IA el cuerpo de los mensajes ni el texto legible de los adjuntos. Activa el consentimiento en la configuración del correo; al desactivarlo se detienen los envíos posteriores.',
        'chinglish': '泽·吉梅尔·阿康特·哈兹·诺特·孔森提德·图·森丁·梅瑟吉·博迪兹·安德·瑞德布尔·阿塔奇门特·特克斯特·图·诶艾. 恩艾博尔·孔森特·因·喵博克斯·塞听斯; 图宁·伊特·奥弗·斯托普斯·弗优彻·传斯弗尔斯.',
    }
    return messages.get(language, messages['zh'])


def require_gmail_ai_consent(config, *sources):
    """Raise before any AI call when a source Gmail mailbox lacks explicit opt-in."""
    try:
        from .mailbox_config import mailbox_id
    except ImportError:
        mailbox_id = None
    profiles = _profiles(config)
    gmail = [profile for profile in profiles if profile.get('mail_provider') == 'gmail']
    if not gmail:
        return

    records = list(_source_records(sources))
    denied = []
    if not records:
        denied = [profile for profile in gmail if profile.get('gmail_ai_consent') is not True]
    else:
        for record in records:
            target = None
            key = record.get('mailbox_key')
            if key and mailbox_id:
                target = next((profile for profile in profiles if mailbox_id(profile) == key), None)
            account = str(record.get('mailbox_account') or record.get('account') or '').strip().casefold()
            if target is None and account:
                target = next((profile for profile in profiles
                               if str(profile.get('account', '')).strip().casefold() == account), None)
            if target is not None and target.get('mail_provider') == 'gmail':
                if target.get('gmail_ai_consent') is not True:
                    denied.append(target)
            elif target is None:
                # Legacy reports without a reliable mailbox identity must never
                # bypass an unconsented Gmail account in a multi-mail setup.
                denied.extend(profile for profile in gmail if profile.get('gmail_ai_consent') is not True)
    if denied:
        raise PermissionError(_denied(config))
