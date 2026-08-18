"""3+3 郵遞區號查詢引擎：正規化 → 大宗專用 → 郵政 WS → 本地 → 行政區。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .bulk_store import bulk_rule_count, lookup_bulk
from .data import DISTRICT_ZIP3
from .normalize import normalize_address
from .parser import ParsedAddress, parse_address
from .post_client import lookup_post
from .street_store import load_street_rules, street_index


@dataclass
class LookupResult:
    address: str
    zipcode: str | None
    zip3: str | None
    normalized: str
    status: str  # exact | district | not_found
    city: str | None = None
    district: str | None = None
    road: str | None = None
    number: int | None = None
    message: str = ""
    source: str = ""  # bulk | post_ws | cache | local | district | none

    def to_dict(self) -> dict:
        return asdict(self)


def _road_candidates(road: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    add(road)
    stripped = re.sub(r"\d+巷.*$", "", road)
    stripped = re.sub(r"\d+弄.*$", "", stripped)
    add(stripped)
    base = re.sub(r"[一二三四五六七八九十百零\d]+段.*$", "", stripped)
    if base and base != stripped and (
        base.endswith("路") or base.endswith("街") or base.endswith("大道") or base.endswith("道")
    ):
        add(base)
    return candidates


def _rule_matches_number(rule: dict, number: int | None) -> bool:
    begin, end, side = int(rule["begin"]), int(rule["end"]), int(rule["side"])
    if number is None:
        return True
    if not (begin <= number <= end):
        return False
    if side == 2:
        return True
    if side == 0:
        return number % 2 == 0
    if side == 1:
        return number % 2 == 1
    return False


# 省轄市：本地示範路段碼不準，禁用 local，改以郵政官方 6 碼為準
_OFFICIAL_ONLY_CITIES = {"基隆市", "嘉義市", "新竹市"}


def _match_local_street(parsed: ParsedAddress) -> tuple[str | None, str]:
    if not (parsed.city and parsed.district and parsed.road):
        return None, ""
    # 基隆／嘉義／新竹：不使用本地示範碼，避免誤判為精確
    if parsed.city in _OFFICIAL_ONLY_CITIES:
        return None, ""
    index = street_index()
    for road in _road_candidates(parsed.road):
        rules = index.get((parsed.city, parsed.district, road))
        if not rules:
            continue
        for rule in rules:
            if _rule_matches_number(rule, parsed.number):
                return str(rule["zip6"]), road
    return None, ""


def _base_result(address: str, normalized: str, parsed: ParsedAddress) -> LookupResult:
    return LookupResult(
        address=address,
        zipcode=None,
        zip3=None,
        normalized=normalized or parsed.normalized,
        status="not_found",
        city=parsed.city,
        district=parsed.district,
        road=parsed.road,
        number=parsed.number,
        source="none",
    )


def lookup_address(
    address: str,
    *,
    name: str | None = None,
    use_post_ws: bool = True,
) -> LookupResult:
    """
    查詢流程：
    1. 自動正規化
    2. 大宗郵件專用郵遞區號（優先）
    3. 中華郵政 Web Service
    4. 本地路段庫
    5. 行政區前3碼備援
    """
    raw = address or ""
    normalized = normalize_address(raw)
    parsed = parse_address(normalized)
    result = _base_result(raw, normalized, parsed)
    result.normalized = parsed.normalized or normalized
    inferred_note = (
        f"已推論行政區：{parsed.district}"
        if parsed.district_inferred and parsed.district
        else ""
    )

    # 1) 大宗郵件專用郵遞區號（正規化後優先）
    bulk_query_addr = parsed.normalized or normalized
    bulk = lookup_bulk(bulk_query_addr, name=name)
    if bulk is None and bulk_query_addr != normalized:
        bulk = lookup_bulk(normalized, name=name)
    if bulk is not None:
        result.zipcode = bulk.zipcode
        result.zip3 = bulk.zipcode[:3]
        result.status = "exact"
        result.source = "bulk"
        result.message = bulk.note or "大宗郵件專用郵遞區號"
        result.normalized = bulk.matched_address or result.normalized
        return result

    # 2) 中華郵政官方查詢
    if use_post_ws:
        candidates: list[str] = []
        with_village = "".join(
            p
            for p in [
                parsed.city,
                parsed.district,
                parsed.village,
                parsed.road,
                parsed.alley,
                f"{parsed.number}號" if parsed.number is not None else "",
            ]
            if p
        )
        for cand in (parsed.normalized, with_village, normalized, raw):
            c = (cand or "").strip()
            if c and c not in candidates:
                candidates.append(c)

        last_msg = ""
        for query_addr in candidates:
            post = lookup_post(query_addr)
            if post.ok and post.zipcode:
                result.zipcode = post.zipcode
                result.zip3 = post.zipcode[:3]
                result.status = "exact"
                result.source = post.source
                result.message = post.message or "中華郵政查詢成功"
                if inferred_note:
                    result.message = f"{inferred_note}；{result.message}"
                if post.normalized:
                    result.normalized = normalize_address(post.normalized)
                else:
                    result.normalized = parsed.normalized or normalized
                return result
            if post.message:
                last_msg = post.message
        if last_msg:
            result.message = last_msg

    # 3) 本地路段備援
    zip6, matched_road = _match_local_street(parsed)
    if zip6:
        key = f"{parsed.city}{parsed.district}" if parsed.city and parsed.district else ""
        result.zipcode = zip6
        result.zip3 = zip6[:3]
        result.status = "exact"
        result.source = "local"
        result.message = f"本地路段命中（{matched_road}）"
        if inferred_note:
            result.message = f"{inferred_note}；{result.message}"
        result.normalized = parsed.normalized or normalized
        if key and key in DISTRICT_ZIP3:
            result.zip3 = DISTRICT_ZIP3[key]
        return result

    # 4) 行政區備援
    if parsed.city and parsed.district:
        key = f"{parsed.city}{parsed.district}"
        zip3 = DISTRICT_ZIP3.get(key)
        if zip3:
            result.zipcode = f"{zip3}000"
            result.zip3 = zip3
            result.status = "district"
            result.source = "district"
            result.message = (result.message + "；" if result.message else "") + (
                "僅行政區前3碼，後3碼000（官方服務未命中或不可用）"
            )
            result.normalized = parsed.normalized or normalized
            return result

    result.message = result.message or "無法解析或查詢郵遞區號"
    result.normalized = normalized
    return result


def street_rule_count() -> int:
    return len(load_street_rules())


def stats() -> dict:
    return {
        "street_rules": street_rule_count(),
        "bulk_rules": bulk_rule_count(),
    }
