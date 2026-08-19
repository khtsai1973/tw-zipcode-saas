"""地址自動正規化。"""

from __future__ import annotations

import re

# 縣市簡稱 / 改制（長字串優先套用）
CITY_ALIASES: dict[str, str] = {
    "台北縣": "新北市",
    "臺北縣": "新北市",
    "桃園縣": "桃園市",
    "台中縣": "臺中市",
    "臺中縣": "臺中市",
    "台南縣": "臺南市",
    "臺南縣": "臺南市",
    "高雄縣": "高雄市",
    "員林鎮": "員林市",
    "頭份鎮": "頭份市",
    "台北市": "臺北市",
    "台中市": "臺中市",
    "台南市": "臺南市",
    "台東縣": "臺東縣",
    "北市": "臺北市",
    "北縣": "新北市",
    "桃縣": "桃園市",
    "中市": "臺中市",
    "南市": "臺南市",
    "高市": "高雄市",
    "竹市": "新竹市",
    "竹縣": "新竹縣",
}

# 舊鄉鎮市名 → 改制後完整「縣市+行政區」
TOWNSHIP_UPGRADES: dict[str, str] = {
    # 高雄
    "鳳山市": "高雄市鳳山區",
    "岡山鎮": "高雄市岡山區",
    "旗山鎮": "高雄市旗山區",
    "美濃鎮": "高雄市美濃區",
    "林園鄉": "高雄市林園區",
    "大寮鄉": "高雄市大寮區",
    "大樹鄉": "高雄市大樹區",
    "仁武鄉": "高雄市仁武區",
    "大社鄉": "高雄市大社區",
    "鳥松鄉": "高雄市鳥松區",
    "橋頭鄉": "高雄市橋頭區",
    "燕巢鄉": "高雄市燕巢區",
    "田寮鄉": "高雄市田寮區",
    "阿蓮鄉": "高雄市阿蓮區",
    "路竹鄉": "高雄市路竹區",
    "湖內鄉": "高雄市湖內區",
    "茄萣鄉": "高雄市茄萣區",
    "永安鄉": "高雄市永安區",
    "彌陀鄉": "高雄市彌陀區",
    "梓官鄉": "高雄市梓官區",
    "六龜鄉": "高雄市六龜區",
    "甲仙鄉": "高雄市甲仙區",
    "杉林鄉": "高雄市杉林區",
    "內門鄉": "高雄市內門區",
    "茂林鄉": "高雄市茂林區",
    "桃源鄉": "高雄市桃源區",
    "那瑪夏鄉": "高雄市那瑪夏區",
    "三民鄉": "高雄市那瑪夏區",
    # 新北（原臺北縣）
    "板橋市": "新北市板橋區",
    "三重市": "新北市三重區",
    "中和市": "新北市中和區",
    "永和市": "新北市永和區",
    "新莊市": "新北市新莊區",
    "新店市": "新北市新店區",
    "樹林市": "新北市樹林區",
    "鶯歌鎮": "新北市鶯歌區",
    "三峽鎮": "新北市三峽區",
    "淡水鎮": "新北市淡水區",
    "汐止市": "新北市汐止區",
    "瑞芳鎮": "新北市瑞芳區",
    "土城市": "新北市土城區",
    "蘆洲市": "新北市蘆洲區",
    "五股鄉": "新北市五股區",
    "泰山鄉": "新北市泰山區",
    "林口鄉": "新北市林口區",
    "深坑鄉": "新北市深坑區",
    "石碇鄉": "新北市石碇區",
    "坪林鄉": "新北市坪林區",
    "三芝鄉": "新北市三芝區",
    "石門鄉": "新北市石門區",
    "八里鄉": "新北市八里區",
    "平溪鄉": "新北市平溪區",
    "雙溪鄉": "新北市雙溪區",
    "貢寮鄉": "新北市貢寮區",
    "金山鄉": "新北市金山區",
    "萬里鄉": "新北市萬里區",
    "烏來鄉": "新北市烏來區",
    # 桃園
    "中壢市": "桃園市中壢區",
    "平鎮市": "桃園市平鎮區",
    "八德市": "桃園市八德區",
    "楊梅市": "桃園市楊梅區",
    "蘆竹鄉": "桃園市蘆竹區",
    "大溪鎮": "桃園市大溪區",
    "大園鄉": "桃園市大園區",
    "龜山鄉": "桃園市龜山區",
    "龍潭鄉": "桃園市龍潭區",
    "新屋鄉": "桃園市新屋區",
    "觀音鄉": "桃園市觀音區",
    "復興鄉": "桃園市復興區",
    # 臺中
    "豐原市": "臺中市豐原區",
    "大里市": "臺中市大里區",
    "太平市": "臺中市太平區",
    "東勢鎮": "臺中市東勢區",
    "大甲鎮": "臺中市大甲區",
    "清水鎮": "臺中市清水區",
    "沙鹿鎮": "臺中市沙鹿區",
    "梧棲鎮": "臺中市梧棲區",
    "后里鄉": "臺中市后里區",
    "神岡鄉": "臺中市神岡區",
    "潭子鄉": "臺中市潭子區",
    "大雅鄉": "臺中市大雅區",
    "新社鄉": "臺中市新社區",
    "石岡鄉": "臺中市石岡區",
    "外埔鄉": "臺中市外埔區",
    "大安鄉": "臺中市大安區",
    "烏日鄉": "臺中市烏日區",
    "大肚鄉": "臺中市大肚區",
    "龍井鄉": "臺中市龍井區",
    "霧峰鄉": "臺中市霧峰區",
    "和平鄉": "臺中市和平區",
    # 臺南
    "新營市": "臺南市新營區",
    "永康市": "臺南市永康區",
    "鹽水鎮": "臺南市鹽水區",
    "白河鎮": "臺南市白河區",
    "柳營鄉": "臺南市柳營區",
    "後壁鄉": "臺南市後壁區",
    "東山鄉": "臺南市東山區",
    "麻豆鎮": "臺南市麻豆區",
    "下營鄉": "臺南市下營區",
    "六甲鄉": "臺南市六甲區",
    "官田鄉": "臺南市官田區",
    "大內鄉": "臺南市大內區",
    "佳里鎮": "臺南市佳里區",
    "西港鄉": "臺南市西港區",
    "七股鄉": "臺南市七股區",
    "將軍鄉": "臺南市將軍區",
    "學甲鎮": "臺南市學甲區",
    "北門鄉": "臺南市北門區",
    "新化鎮": "臺南市新化區",
    "善化鎮": "臺南市善化區",
    "新市鄉": "臺南市新市區",
    "安定鄉": "臺南市安定區",
    "山上鄉": "臺南市山上區",
    "玉井鄉": "臺南市玉井區",
    "楠西鄉": "臺南市楠西區",
    "南化鄉": "臺南市南化區",
    "左鎮鄉": "臺南市左鎮區",
    "仁德鄉": "臺南市仁德區",
    "歸仁鄉": "臺南市歸仁區",
    "關廟鄉": "臺南市關廟區",
    "龍崎鄉": "臺南市龍崎區",
}

ROAD_ALIASES: dict[str, str] = {
    "台灣大道": "臺灣大道",
}

# 全形數字 / 常見全形符號 → 半形
_TRANS = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "－": "-",
        "—": "-",
        "─": "-",
        "～": "~",
        "／": "/",
        "＃": "#",
        "　": "",
        " ": "",
        "\t": "",
        "\u3000": "",
    }
)

_ZIP_PREFIX = re.compile(r"^(?:\d{3}|\d{5,6})(?![號巷弄樓鄰之\d])")
_SORTED_TOWNSHIPS = sorted(TOWNSHIP_UPGRADES.items(), key=lambda x: len(x[0]), reverse=True)
_SORTED_CITIES = sorted(CITY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)

# 國字數字（含大寫）→ 值
_DIGIT_MAP: dict[str, int] = {
    "〇": 0,
    "○": 0,
    "零": 0,
    "０": 0,
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "壹": 1,
    "貳": 2,
    "贰": 2,
    "參": 3,
    "叁": 3,
    "肆": 4,
    "伍": 5,
    "陸": 6,
    "陆": 6,
    "柒": 7,
    "捌": 8,
    "玖": 9,
}
_UNIT_MAP: dict[str, int] = {
    "十": 10,
    "拾": 10,
    "廿": 20,
    "卅": 30,
    "百": 100,
    "佰": 100,
    "千": 1000,
    "仟": 1000,
}
_CN_NUM_CHARS = "".join(_DIGIT_MAP) + "".join(_UNIT_MAP)
# 國字數字串 + 號/巷/弄/樓/鄰/之
_CN_NUM_BEFORE_UNIT = re.compile(
    rf"([{re.escape(_CN_NUM_CHARS)}]+)(之(?=[{re.escape(_CN_NUM_CHARS)}\d])|[號巷弄樓鄰])"
)


def _parse_chinese_number(text: str) -> int | None:
    """將國字數字轉成整數。支援『一五七』逐位與『一百五十七』進位兩種。"""
    if not text:
        return None

    # 含十/百/千 → 進位制
    if any(u in text for u in _UNIT_MAP):
        total = 0
        current = 0
        for ch in text:
            if ch in _DIGIT_MAP:
                current = _DIGIT_MAP[ch]
            elif ch in _UNIT_MAP:
                unit = _UNIT_MAP[ch]
                if unit in (20, 30):  # 廿、卅
                    total += unit
                    current = 0
                    continue
                if current == 0 and unit == 10:
                    current = 1  # 「十二」的「十」
                total += current * unit
                current = 0
            else:
                return None
        return total + current

    # 逐位：一五七 → 157
    digits: list[str] = []
    for ch in text:
        if ch not in _DIGIT_MAP:
            return None
        digits.append(str(_DIGIT_MAP[ch]))
    if not digits:
        return None
    return int("".join(digits))


def _replace_chinese_door_numbers(text: str) -> str:
    """一五七號 → 157號；貳拾巷 → 20巷；十二樓 → 12樓。"""

    def repl(match: re.Match[str]) -> str:
        cn = match.group(1)
        suffix = match.group(2)
        value = _parse_chinese_number(cn)
        if value is None:
            return match.group(0)
        return f"{value}{suffix}"

    # 可能連續出現（號之三 → 先號後之），多跑兩次較穩
    prev = None
    while prev != text:
        prev = text
        text = _CN_NUM_BEFORE_UNIT.sub(repl, text)
    return text


def _city_prefix(full: str) -> str:
    m = re.match(r"^(.+?[縣市])", full)
    return m.group(1) if m else ""


def _apply_city_aliases(text: str) -> str:
    for src, dst in _SORTED_CITIES:
        src_n = src.replace("台", "臺")
        if text.startswith(src):
            return dst + text[len(src) :]
        if text.startswith(src_n):
            return dst + text[len(src_n) :]
    return text


def _apply_township_upgrades(text: str) -> str:
    """舊鄉鎮市 → 新直轄市行政區。例：鳳山市 → 高雄市鳳山區（含錯序出現在字串中後段）。"""
    # 特例：舊縣轄「桃園市」
    if text.startswith("桃園縣桃園市"):
        return "桃園市桃園區" + text[len("桃園縣桃園市") :]
    if text.startswith("桃園市桃園市"):
        return "桃園市桃園區" + text[len("桃園市桃園市") :]

    for old, full in _SORTED_TOWNSHIPS:
        city = _city_prefix(full)
        new_district = full[len(city) :]
        old_county = city.replace("市", "縣") if city.endswith("市") else ""

        # 高雄市鳳山市 / 高雄縣鳳山市 / 鳳山市（開頭）
        for prefix in (city, old_county, ""):
            token = f"{prefix}{old}"
            if text.startswith(token):
                return full + text[len(token) :]

        # 縣市已正確，僅行政區仍是舊名
        if city and text.startswith(city):
            rest = text[len(city) :]
            if rest.startswith(old):
                return city + new_district + rest[len(old) :]

    # 錯序：舊鄉鎮市名出現在字串中後段（如「文化路…板橋市」）
    for old, full in _SORTED_TOWNSHIPS:
        if old not in text:
            continue
        if full in text:
            # 已含完整新政區時，去掉殘留舊名
            text = text.replace(old, "")
            continue
        text = text.replace(old, full, 1)

    return text


def normalize_address(address: str) -> str:
    """清洗並正規化台灣地址字串（查詢前必跑）。"""
    if not address:
        return ""

    text = str(address).strip()
    # 全形數字 / 空白 → 半形
    text = text.translate(_TRANS)
    text = text.replace("台", "臺")
    text = _ZIP_PREFIX.sub("", text)

    text = _apply_city_aliases(text)
    text = _apply_township_upgrades(text)

    for src, dst in ROAD_ALIASES.items():
        text = text.replace(src.replace("台", "臺"), dst)
        text = text.replace(src, dst)

    # 國字／大寫數字 → 半形阿拉伯數字（一五七號→157號）
    text = _replace_chinese_door_numbers(text)
    # 12號之三 → 12號之3
    text = re.sub(
        rf"之([{re.escape(_CN_NUM_CHARS)}]+)(?=號|$)",
        lambda m: (
            f"之{n}"
            if (n := _parse_chinese_number(m.group(1))) is not None
            else m.group(0)
        ),
        text,
    )
    # 第十二樓 → 12樓
    text = re.sub(
        rf"第([{re.escape(_CN_NUM_CHARS)}]+)樓",
        lambda m: (
            f"{n}樓"
            if (n := _parse_chinese_number(m.group(1))) is not None
            else m.group(0)
        ),
        text,
    )

    text = re.sub(r"(\d+)[-~](\d+)號?", r"\1之\2號", text)
    text = re.sub(r"(\d+)號之(\d+)", r"\1之\2號", text)
    text = re.sub(r"(\d+)[FfＦｆ]", r"\1樓", text)
    text = re.sub(r"第(\d+)樓", r"\1樓", text)
    text = re.sub(r"[，,。.、；;]+", "", text)
    text = re.sub(r"[()（）\[\]【】]", "", text)
    text = re.sub(r"號+", "號", text)
    return text.strip()
