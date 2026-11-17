"""Maintainer-only lexicon refresh: install cmudict in a project build venv first.

Normal builds use the checked-in JSON and do not need this development dependency.
The resulting Chinese sounds are a playful approximation, not an IPA reference.
"""
import json
from pathlib import Path
import re

import cmudict

ROOT = Path(__file__).resolve().parents[1]
VOWELS = dict(zip("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split(),
                  "阿 诶 阿 奥 奥 艾 诶 尔 诶 伊 伊 欧 欧 乌 乌".split()))
CONSONANTS = dict(zip("B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH".split(),
                      "布 吃 德 泽 弗 格 哈 吉 克 尔 姆 恩 恩 普 尔 斯 什 特 思 维 乌 伊 兹 日".split()))
COMBINED = {
    "B": "巴 贝 巴 波 鲍 拜 贝 伯 贝 比 比 博 博 布 布",
    "P": "帕 派 帕 泼 鲍 拍 佩 珀 佩 皮 皮 波 波 普 普",
    "M": "马 麦 玛 莫 毛 麦 梅 默 梅 米 米 莫 莫 姆 姆",
    "F": "法 法 弗 佛 福 法 费 弗 费 菲 菲 佛 佛 富 富",
    "V": "瓦 维 沃 沃 沃 外 维 弗 维 维 维 沃 沃 弗 弗",
    "D": "达 戴 德 多 道 戴 德 德 戴 迪 迪 多 多 杜 杜",
    "T": "塔 泰 特 托 陶 泰 特 特 泰 提 提 托 托 图 图",
    "N": "纳 奈 纳 诺 瑙 奈 内 纳 内 尼 尼 诺 诺 努 努",
    "L": "拉 莱 勒 洛 劳 莱 勒 勒 雷 利 利 洛 洛 卢 卢",
    "K": "卡 凯 克 科 考 凯 克 克 凯 基 基 科 科 库 库",
    "G": "嘎 盖 格 果 高 盖 格 格 盖 吉 吉 果 果 古 古",
    "HH": "哈 海 哈 霍 豪 海 赫 赫 黑 希 希 霍 霍 胡 胡",
    "R": "拉 莱 瑞 若 饶 瑞 瑞 尔 瑞 瑞 瑞 若 若 鲁 鲁",
    "S": "萨 塞 瑟 索 萨 赛 塞 瑟 塞 西 西 索 索 苏 苏",
    "Z": "扎 泽 泽 佐 早 宰 泽 泽 泽 兹 兹 佐 佐 祖 祖",
    "SH": "沙 谢 舍 肖 少 晒 谢 舍 谢 希 希 肖 肖 舒 舒",
    "CH": "查 柴 彻 乔 超 柴 切 彻 切 奇 奇 乔 乔 楚 楚",
    "JH": "加 杰 杰 乔 焦 宅 杰 杰 杰 吉 吉 乔 乔 朱 朱",
    "TH": "萨 塞 瑟 索 萨 赛 塞 瑟 塞 西 西 索 索 苏 苏",
    "DH": "扎 泽 泽 佐 早 宰 泽 泽 泽 兹 兹 佐 佐 祖 祖",
    "W": "瓦 外 沃 沃 沃 歪 韦 沃 韦 威 威 沃 沃 乌 乌",
    "Y": "亚 耶 亚 哟 尧 耶 耶 耶 耶 伊 伊 哟 哟 优 优",
}
COMBINED = {key: dict(zip(VOWELS, row.split())) for key, row in COMBINED.items()}
OVERRIDES = {
    "mail": "喵", "reports": "瑞泼特斯", "report": "瑞泼特", "mailbox": "喵博克斯",
    "mailboxes": "喵博克西斯", "checks": "切克斯", "check": "切克", "ai": "诶·艾",
    "service": "瑟维斯", "general": "杰讷勒尔", "settings": "塞听斯", "save": "塞夫",
    "cancel": "坎搜", "summarize": "萨玛瑞兹", "email": "伊喵", "assistant": "阿西斯腾特",
    "the": "泽", "a": "诶", "an": "安", "and": "安德", "or": "奥尔", "of": "奥夫",
    "to": "图", "in": "因", "on": "昂", "for": "佛", "with": "威兹", "without": "威兹奥特",
    "is": "伊兹", "are": "阿尔", "be": "比", "it": "伊特", "this": "兹斯", "that": "泽特",
    "you": "优", "your": "尤尔", "not": "诺特", "no": "诺", "yes": "耶斯",
    "will": "威尔", "can": "坎", "cannot": "坎诺特", "only": "昂利", "all": "奥尔",
    "from": "弗若姆", "after": "阿弗特", "before": "比佛", "please": "普利兹",
    "open": "欧喷", "close": "克漏兹", "send": "森德", "reply": "瑞普莱",
    "replies": "瑞普莱兹", "original": "奥瑞吉讷尔", "folder": "佛尔德",
    "folders": "佛尔德斯", "select": "瑟莱克特", "selected": "瑟莱克提德",
    "download": "当漏德", "update": "阿普戴特", "language": "兰贵吉",
    "english": "英格力士", "spanish": "斯班尼士", "chinese": "拆尼斯",
    "chinglish": "英格力士", "codex": "科戴克斯", "deepseek": "迪普西克",
    "harness": "哈尼斯", "github": "吉特哈布", "windows": "温斗斯", "mac": "麦克",
    "macos": "麦克欧艾斯", "token": "托肯", "tokens": "托肯斯", "markdown": "马克当",
    "smtp": "艾斯艾姆提皮", "imap": "艾麦普", "pop": "泡普", "api": "诶皮艾",
    "oauth": "欧奥思", "tls": "提艾尔艾斯", "ssl": "艾斯艾斯艾尔",
    "ui": "优艾", "cpu": "西皮优", "mb": "艾姆比", "gb": "吉比",
}


def phonetic(phones):
    phones = [re.sub(r"\d", "", phone) for phone in phones]
    result = []
    i = 0
    while i < len(phones):
        phone = phones[i]
        if i + 1 < len(phones) and phone in COMBINED and phones[i + 1] in VOWELS:
            result.append(COMBINED[phone][phones[i + 1]])
            i += 2
        else:
            result.append(VOWELS.get(phone, CONSONANTS.get(phone, "")))
            i += 1
    return "".join(result)


def main():
    pronunciations = cmudict.dict()
    words = set()
    for folder in ("macos/Resources", "windows/native"):
        data = json.loads((ROOT / folder / "ui-en.json").read_text(encoding="utf-8"))
        text = "\n".join(data["exact"].values()) + "\n" + "\n".join(row["en"] for row in data["templates"])
        if folder.startswith("macos"):
            docs = ROOT / folder
        else:
            docs = ROOT / "windows/docs"
        for name in ("Quick-start-en.txt", "Mail-account-setup-en.txt"):
            text += "\n" + (docs / name).read_text(encoding="utf-8")
        words.update(word.lower() for word in re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", text))
    target = Path(__file__).with_name("chinglish-words.json")
    labels = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    labels.update({word: phonetic(pronunciations[word][0]) for word in sorted(words) if word in pronunciations})
    labels.update(OVERRIDES)
    target.write_text(json.dumps(dict(sorted(labels.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "docs/Chinglish-lexicon-LICENSE.txt").write_text(cmudict.license_string(), encoding="utf-8")
    print("Phonetic words:", len(labels))


if __name__ == "__main__":
    main()
