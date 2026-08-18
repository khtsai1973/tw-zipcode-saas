"""台灣地址解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass

CITY_PATTERN = (
    r"(臺北市|台北市|新北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|"
    r"基隆市|新竹市|嘉義市|新竹縣|苗栗縣|彰化縣|南投縣|雲林縣|嘉義縣|"
    r"屏東縣|宜蘭縣|花蓮縣|臺東縣|台東縣|澎湖縣|金門縣|連江縣)"
)

DISTRICT_PATTERN = r"([\u4e00-\u9fff]{1,4}[鄉鎮市區])"

# 村里：僅當後面接著「鄰」或「路/街/大道/巷/弄」時才視為村里名
# 避免誤刪「仁里路」「里港路」等路名中的「里」
VILLAGE_PATTERN = (
    r"^([\u4e00-\u9fff]{1,8}[村里])"
    r"(?=(?:\d+鄰)|(?:[\u4e00-\u9fff0-9]*?(?:路|街|大道|巷|弄)))"
)

NEIGHBOR_PATTERN = r"^\d+鄰"

# 路/街/大道 + 可選段
ROAD_PATTERN = (
    r"("
    r"[\u4e00-\u9fff0-9０-９]+?"
    r"(?:路|街|大道|道)"
    r"(?:[一二三四五六七八九十百零\d]+段)?"
    r")"
)

ALLEY_PATTERN = r"(?:(\d+)巷)?(?:(\d+)弄)?"
NUMBER_PATTERN = r"(\d+)(?:之\d+)?號?"


from .district_infer import infer_district


@dataclass
class ParsedAddress:
    raw: str
    city: str | None = None
    district: str | None = None
    village: str | None = None
    road: str | None = None
    alley: str | None = None
    number: int | None = None
    normalized: str = ""
    district_inferred: bool = False


def _normalize_chars(text: str) -> str:
    text = text.strip()
    text = text.replace("台", "臺")
    trans = str.maketrans("０１２３４５６７８９－—", "0123456789--")
    text = text.translate(trans)
    text = re.sub(r"\s+", "", text)
    return text


def parse_address(address: str) -> ParsedAddress:
    raw = address or ""
    text = _normalize_chars(raw)
    result = ParsedAddress(raw=raw, normalized=text)

    city_m = re.search(CITY_PATTERN, text)
    if city_m:
        result.city = city_m.group(1)
        text_after = text[city_m.end() :]
    else:
        text_after = text

    district_m = re.match(DISTRICT_PATTERN, text_after)
    if district_m:
        result.district = district_m.group(1)
        text_after = text_after[district_m.end() :]

    # 村里（安全剝離：後面必須是鄰或路街）
    village_m = re.match(VILLAGE_PATTERN, text_after)
    if village_m:
        result.village = village_m.group(1)
        text_after = text_after[village_m.end() :]

    neighbor_m = re.match(NEIGHBOR_PATTERN, text_after)
    if neighbor_m:
        text_after = text_after[neighbor_m.end() :]

    road_m = re.match(ROAD_PATTERN, text_after)
    if road_m:
        result.road = road_m.group(1)
        text_after = text_after[road_m.end() :]

        alley_m = re.match(ALLEY_PATTERN, text_after)
        if alley_m and (alley_m.group(1) or alley_m.group(2)):
            parts = []
            if alley_m.group(1):
                parts.append(f"{alley_m.group(1)}巷")
            if alley_m.group(2):
                parts.append(f"{alley_m.group(2)}弄")
            result.alley = "".join(parts)
            text_after = text_after[alley_m.end() :]

    num_m = re.search(NUMBER_PATTERN, text_after)
    if num_m:
        result.number = int(num_m.group(1))

    # 省轄市缺行政區時，依路名推論（基隆／新竹／嘉義）
    if result.city and not result.district and result.road:
        inferred = infer_district(result.city, result.road)
        if inferred:
            result.district = inferred
            result.district_inferred = True

    # 正規化輸出：縣市+行政區+路+巷弄+號（不含村里/鄰，利於郵政查詢）
    parts = [p for p in [result.city, result.district, result.road, result.alley] if p]
    if result.number is not None:
        parts.append(f"{result.number}號")
    result.normalized = "".join(parts) if parts else result.normalized
    return result
