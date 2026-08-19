"""3+3 郵遞區號查詢引擎：正規化 → 大宗專用 → 郵政 WS → 本地 → 行政區。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .bulk_store import bulk_rule_count, lookup_bulk
from .data import DISTRICT_ZIP3
from .normalize import normalize_address
from .parser import ParsedAddress, parse_address
from .post_client import lookup_post
from . import reasons as R
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
    reason_code: str = R.UNKNOWN
    reason: str = ""
    reordered: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _set_reason(result: LookupResult, code: str, extra: str = "") -> None:
    result.reason_code = code
    result.reason = R.label(code)
    if extra:
        result.message = (
            f"{result.message}；{extra}" if result.message else extra
        )


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


@dataclass
class _LocalProbe:
    zip6: str | None = None
    matched_road: str = ""
    # none | hit | road_missing | road_unmatched | number_unmatched
    detail: str = "none"


def _probe_local_street(parsed: ParsedAddress) -> _LocalProbe:
    if not (parsed.city and parsed.district and parsed.road):
        return _LocalProbe(detail="road_missing" if not parsed.road else "none")
    if parsed.city in _OFFICIAL_ONLY_CITIES:
        return _LocalProbe(detail="none")

    index = street_index()
    found_rules = False
    for road in _road_candidates(parsed.road):
        rules = index.get((parsed.city, parsed.district, road))
        if not rules:
            continue
        found_rules = True
        for rule in rules:
            if parsed.number is None:
                # 有路段規則但缺門牌 → 無法精準判斷
                continue
            if _rule_matches_number(rule, parsed.number):
                return _LocalProbe(zip6=str(rule["zip6"]), matched_road=road, detail="hit")
        # 此路有規則但門牌未命中
        return _LocalProbe(matched_road=road, detail="number_unmatched")

    if found_rules:
        return _LocalProbe(detail="number_unmatched")
    return _LocalProbe(detail="road_unmatched")


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
        reason_code=R.UNKNOWN,
        reason=R.label(R.UNKNOWN),
        reordered=bool(getattr(parsed, "reordered", False)),
    )


def _structural_reason(parsed: ParsedAddress, normalized: str) -> str | None:
    """結構性問題優先於外部服務問題。"""
    if not (normalized or "").strip():
        return R.FORMAT_ERROR
    if not parsed.city:
        # 正規化後仍無縣市：偏格式或內容無法辨識
        if not re.search(r"[縣市]", normalized):
            return R.MISSING_CITY
        return R.FORMAT_ERROR
    if not parsed.road:
        return R.MISSING_ROAD
    return None


def _service_or_match_reason(
    *,
    parsed: ParsedAddress,
    post_error_kind: str,
    local: _LocalProbe,
) -> str:
    """在結構完整時，依外部服務／本地比對結果判定原因。"""
    if post_error_kind == "timeout":
        return R.EXTERNAL_TIMEOUT
    if post_error_kind == "api_error":
        return R.API_ERROR
    if parsed.number is None or local.detail == "number_unmatched":
        return R.HOUSE_NUMBER_UNKNOWN
    if local.detail in {"road_unmatched", "road_missing", "none"}:
        return R.NO_ROAD_MATCH
    return R.NO_ROAD_MATCH


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
    reorder_note = "已重排地址元件順序" if parsed.reordered else ""
    prefix_notes = "；".join(n for n in (reorder_note, inferred_note) if n)

    # 結構性早退（仍允許大宗／郵政嘗試較少？大宗可能靠名稱。先跑大宗）
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
        _set_reason(result, R.BULK_OK)
        return result

    post_error_kind = ""
    last_msg = ""

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

        for query_addr in candidates:
            post = lookup_post(query_addr)
            if post.ok and post.zipcode:
                result.zipcode = post.zipcode
                result.zip3 = post.zipcode[:3]
                result.status = "exact"
                result.source = post.source
                result.message = post.message or "中華郵政查詢成功"
                if prefix_notes:
                    result.message = f"{prefix_notes}；{result.message}"
                if post.normalized:
                    result.normalized = normalize_address(post.normalized)
                else:
                    result.normalized = parsed.normalized or normalized
                _set_reason(result, R.POST_OK)
                return result
            if post.message:
                last_msg = post.message
            # 保留最嚴重的錯誤類型
            if post.error_kind == "timeout":
                post_error_kind = "timeout"
            elif post.error_kind == "api_error" and post_error_kind != "timeout":
                post_error_kind = "api_error"
            elif post.error_kind and not post_error_kind:
                post_error_kind = post.error_kind
        if last_msg:
            result.message = last_msg

    # 3) 本地路段備援
    local = _probe_local_street(parsed)
    if local.zip6:
        key = f"{parsed.city}{parsed.district}" if parsed.city and parsed.district else ""
        result.zipcode = local.zip6
        result.zip3 = local.zip6[:3]
        result.status = "exact"
        result.source = "local"
        result.message = f"本地路段命中（{local.matched_road}）"
        if prefix_notes:
            result.message = f"{prefix_notes}；{result.message}"
        result.normalized = parsed.normalized or normalized
        if key and key in DISTRICT_ZIP3:
            result.zip3 = DISTRICT_ZIP3[key]
        _set_reason(result, R.LOCAL_FALLBACK_OK)
        return result

    # 結構性原因（缺縣市／路段／格式）
    structural = _structural_reason(parsed, normalized)
    match_reason = _service_or_match_reason(
        parsed=parsed,
        post_error_kind=post_error_kind,
        local=local,
    )
    # 結構問題優先；但外部逾時／API 錯誤在結構完整時優先標出
    if structural in {R.FORMAT_ERROR, R.MISSING_CITY, R.MISSING_ROAD}:
        final_reason = structural
    elif post_error_kind in {"timeout", "api_error"}:
        final_reason = match_reason
    elif structural:
        final_reason = structural
    else:
        final_reason = match_reason

    # 4) 行政區備援
    if parsed.city and parsed.district:
        key = f"{parsed.city}{parsed.district}"
        zip3 = DISTRICT_ZIP3.get(key)
        if zip3:
            result.zipcode = f"{zip3}000"
            result.zip3 = zip3
            result.status = "district"
            result.source = "district"
            note = "僅行政區前3碼，後3碼000（官方服務未命中或不可用）"
            result.message = (result.message + "；" if result.message else "") + note
            result.normalized = parsed.normalized or normalized
            _set_reason(result, final_reason)
            return result

    result.message = result.message or "無法解析或查詢郵遞區號"
    result.normalized = normalized
    _set_reason(result, final_reason)
    return result


def street_rule_count() -> int:
    return len(load_street_rules())


def stats() -> dict:
    return {
        "street_rules": street_rule_count(),
        "bulk_rules": bulk_rule_count(),
    }
