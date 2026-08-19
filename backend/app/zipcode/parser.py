"""台灣地址解析（含元件錯位重排）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

CITY_PATTERN = (
    r"(臺北市|台北市|新北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|"
    r"基隆市|新竹市|嘉義市|新竹縣|苗栗縣|彰化縣|南投縣|雲林縣|嘉義縣|"
    r"屏東縣|宜蘭縣|花蓮縣|臺東縣|台東縣|澎湖縣|金門縣|連江縣)"
)

DISTRICT_PATTERN = r"([\u4e00-\u9fff]{1,3}[鄉鎮市區])"

# 村里：僅當後面接著「鄰」或「路/街/大道/巷/弄」時才視為村里名
VILLAGE_PATTERN = (
    r"([\u4e00-\u9fff]{1,8}[村里])"
    r"(?=(?:\d+鄰)|(?:[\u4e00-\u9fff0-9]*?(?:路|街|大道|巷|弄)))"
)

ROAD_PATTERN = (
    r"("
    r"(?!號)[\u4e00-\u9fff]+"  # 不以「號」開頭，避免「216號愛國東路」誤拼
    r"[\u4e00-\u9fff0-9]*?"
    r"(?:路|街|大道|道)"
    r"(?:[一二三四五六七八九十百零\d]+段)?"
    r")"
)

ALLEY_PATTERN = r"(?:(\d+)巷)?(?:(\d+)弄)?"
NUMBER_PATTERN = r"(\d+)(?:之\d+)?號"

_CITY_RE = re.compile(CITY_PATTERN)
_DISTRICT_RE = re.compile(DISTRICT_PATTERN)
_VILLAGE_RE = re.compile(VILLAGE_PATTERN)
_ROAD_RE = re.compile(ROAD_PATTERN)
_ALLEY_RE = re.compile(r"(?:(\d+)巷)(?:(\d+)弄)?|(?:(\d+)弄)")
_NUMBER_RE = re.compile(NUMBER_PATTERN)
_NEIGHBOR_RE = re.compile(r"\d+鄰")

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
    reordered: bool = False


def _normalize_chars(text: str) -> str:
    text = text.strip()
    text = text.replace("台", "臺")
    trans = str.maketrans("０１２３４５６７８９－—", "0123456789--")
    text = text.translate(trans)
    text = re.sub(r"\s+", "", text)
    return text


def _mask_span(chars: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        chars[i] = "\0"


def _extract_components(text: str) -> tuple[dict, bool]:
    """
    不依輸入順序抽取縣市／行政區／村里／路／巷弄／號，
    並判斷是否需要重排（元件出現順序非標準）。
    """
    chars = list(text)
    found: dict = {
        "city": None,
        "district": None,
        "village": None,
        "road": None,
        "alley": None,
        "number": None,
    }
    spans: dict[str, tuple[int, int]] = {}

    city_m = _CITY_RE.search(text)
    if city_m:
        found["city"] = city_m.group(1).replace("台", "臺")
        spans["city"] = city_m.span()
        _mask_span(chars, *city_m.span())

    masked = "".join(chars)

    # 行政區：略過已被遮罩區；偏好「區」
    district_candidates = list(_DISTRICT_RE.finditer(masked))
    district_m = None
    for m in district_candidates:
        token = m.group(1)
        # 避免把殘留「Ｘ市」誤當行政區（縣市已抽走後理論上少見）
        if token.endswith("市") and len(token) <= 3:
            continue
        district_m = m
        if token.endswith("區"):
            break
    if district_m:
        found["district"] = district_m.group(1)
        spans["district"] = district_m.span()
        _mask_span(chars, *district_m.span())
        masked = "".join(chars)

    village_m = _VILLAGE_RE.search(masked)
    if village_m:
        found["village"] = village_m.group(1)
        spans["village"] = village_m.span()
        _mask_span(chars, *village_m.span())
        masked = "".join(chars)

    # 鄰不保留在正規化輸出，但遮掉以免干擾門牌
    for m in _NEIGHBOR_RE.finditer(masked):
        _mask_span(chars, *m.span())
    masked = "".join(chars)

    road_m = _ROAD_RE.search(masked)
    if road_m:
        found["road"] = road_m.group(1)
        spans["road"] = road_m.span()
        _mask_span(chars, *road_m.span())
        masked = "".join(chars)

    alley_m = _ALLEY_RE.search(masked)
    if alley_m:
        if alley_m.group(1) and alley_m.group(2):
            found["alley"] = f"{alley_m.group(1)}巷{alley_m.group(2)}弄"
        elif alley_m.group(1):
            found["alley"] = f"{alley_m.group(1)}巷"
        elif alley_m.group(3):
            found["alley"] = f"{alley_m.group(3)}弄"
        spans["alley"] = alley_m.span()
        _mask_span(chars, *alley_m.span())
        masked = "".join(chars)

    num_m = _NUMBER_RE.search(masked)
    if not num_m:
        # 容忍「216」無「號」但前面已有路
        if found["road"]:
            num_m = re.search(r"(\d{1,5})(?:之\d+)?(?!\d)", masked)
    if num_m:
        found["number"] = int(num_m.group(1))
        spans["number"] = num_m.span()

    # 標準順序：縣市 < 行政區 < 路 < 巷弄 < 號
    order_keys = [k for k in ("city", "district", "road", "alley", "number") if k in spans]
    positions = [spans[k][0] for k in order_keys]
    reordered = False
    if len(positions) >= 2:
        reordered = positions != sorted(positions)
    # 若縣市不在開頭也視為重排（前面有其他有效元件）
    if spans.get("city") and spans["city"][0] > 0 and (found["road"] or found["district"]):
        reordered = True

    return found, reordered


def rebuild_normalized(found: dict) -> str:
    parts = [
        found.get("city"),
        found.get("district"),
        found.get("road"),
        found.get("alley"),
    ]
    if found.get("number") is not None:
        parts.append(f"{found['number']}號")
    return "".join(p for p in parts if p)


def parse_address(address: str) -> ParsedAddress:
    raw = address or ""
    text = _normalize_chars(raw)
    result = ParsedAddress(raw=raw, normalized=text)
    if not text:
        return result

    found, reordered = _extract_components(text)
    result.city = found.get("city")
    result.district = found.get("district")
    result.village = found.get("village")
    result.road = found.get("road")
    result.alley = found.get("alley")
    result.number = found.get("number")
    result.reordered = reordered

    # 省轄市缺行政區時，依路名推論（基隆／新竹／嘉義）
    if result.city and not result.district and result.road:
        inferred = infer_district(result.city, result.road)
        if inferred:
            result.district = inferred
            result.district_inferred = True

    rebuilt = rebuild_normalized(
        {
            "city": result.city,
            "district": result.district,
            "road": result.road,
            "alley": result.alley,
            "number": result.number,
        }
    )
    result.normalized = rebuilt if rebuilt else text
    if rebuilt and rebuilt != text and (result.city or result.road):
        # 字串已重組成標準序
        result.reordered = result.reordered or (rebuilt != text)
    return result
