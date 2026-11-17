"""Build-only phonetic UI language. Never transform mailbox data or AI output.

The checked-in lexicon keeps package generation deterministic and dependency-free.
English words are rendered as playful Chinese sounds, separated by middle dots.
Code spans, URLs, addresses, placeholders and error identifiers stay byte-for-byte.
"""
import json
from pathlib import Path
import re

LEXICON = Path(__file__).with_name("chinglish-words.json")
WORDS = json.loads(LEXICON.read_text(encoding="utf-8")) if LEXICON.exists() else {}
LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", (
    "诶", "比", "西", "迪", "伊", "艾弗", "吉", "艾尺", "艾", "杰", "凯", "艾尔",
    "艾姆", "恩", "欧", "皮", "丘", "阿尔", "艾斯", "提", "优", "维", "达布流",
    "艾克斯", "歪", "贼德")))
PROTECTED = re.compile(
    r"```[\s\S]*?```|`[^`\n]+`|https?://[^\s<>)]+|"
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\{\d+\}|%(?:\d+\$)?[sdf]|\[[A-Z][A-Z0-9_:-]+\]|"
    r"\byyyyMMddHHmm\b|\bYYYY-MM-DD\b|\bHH:mm\b|"
    r"(?<!\w)(?:[A-Za-z]:\\[^\s]+|/[A-Za-z0-9_./-]+)|"
    r"\b[A-Za-z0-9_./-]+\.(?:json|md|txt|exe|app|dmg|ps1|py|bat|command|pdf|log|csv)\b",
    0)
TOKEN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")


def word(value):
    return WORDS.get(value.lower(), "".join(LETTERS[c] for c in value.lower() if c in LETTERS))


def _plain(text):
    # Replace only English words, never Chinese mail subjects or arbitrary data.
    result = TOKEN.sub(lambda match: word(match.group()), text)
    # A middle dot replaces the English word boundary, not sentence punctuation.
    result = re.sub(r"(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff&])", "·", result)
    result = re.sub(r"(?<=&) +(?=[\u3400-\u9fff])", "·", result)
    return result


def transliterate(text):
    parts = []
    end = 0
    for match in PROTECTED.finditer(text):
        parts.extend((_plain(text[end:match.start()]), match.group()))
        end = match.end()
    parts.append(_plain(text[end:]))
    return "".join(parts)


def catalog(english):
    exact = {source: transliterate(target) for source, target in english["exact"].items()}
    # Backend errors/statuses can already arrive in English. Only known app-owned
    # whole strings are mapped; free-form subjects and report contents are excluded.
    for target in english["exact"].values():
        exact.setdefault(target, transliterate(target))
    # Benson's chosen navigation spellings are the canonical names of this pack.
    exact["邮件报告"] = "喵·瑞泼特斯"
    exact["邮箱与检查"] = "喵博克斯·&·切克斯"
    exact["邮件小秘书"] = "伊喵·阿西斯腾特"
    templates = [
        {"pattern": row["pattern"], "en": transliterate(row["en"])}
        for row in english["templates"]]
    # A worker can return an already localized English status. Build anchored
    # counterparts for those app-owned templates, keeping captures untouched.
    english_templates = [row["en"] for row in english["templates"]]
    english_templates.extend(value for value in english["exact"].values() if "%s" in value)
    for text in english_templates:
        if "%s" in text:
            counter = iter(range(text.count("%s")))
            text = re.sub(r"%s", lambda _: "{" + str(next(counter)) + "}", text)
        slots = re.split(r"(\{\d+\})", text)
        if len(slots) == 1:
            continue
        pattern = "^" + "".join("(.*?)" if re.fullmatch(r"\{\d+\}", part) else re.escape(part) for part in slots) + "$"
        counter = iter(range((len(slots) - 1) // 2))
        numbered = re.sub(r"\{\d+\}", lambda _: "{" + str(next(counter)) + "}", text)
        templates.append({"pattern": pattern, "en": transliterate(numbered)})
    # Multiple source strings can have the same English translation.
    templates = list({row["pattern"]: row for row in templates}.values())
    return {"exact": exact, "templates": templates}
