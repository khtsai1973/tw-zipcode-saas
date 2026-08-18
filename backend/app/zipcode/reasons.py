"""查詢原因代碼與中文標籤。"""

from __future__ import annotations

# 與產品文案對齊的原因代碼
FORMAT_ERROR = "format_error"
MISSING_CITY = "missing_city"
MISSING_ROAD = "missing_road"
NO_ROAD_MATCH = "no_road_match"
HOUSE_NUMBER_UNKNOWN = "house_number_unknown"
EXTERNAL_TIMEOUT = "external_timeout"
API_ERROR = "api_error"
LOCAL_FALLBACK_OK = "local_fallback_ok"
POST_OK = "post_ok"
BULK_OK = "bulk_ok"
DISTRICT_FALLBACK = "district_fallback"
BLANK_ADDRESS = "blank_address"
UNKNOWN = "unknown"

REASON_LABELS: dict[str, str] = {
    FORMAT_ERROR: "地址格式錯誤",
    MISSING_CITY: "缺少縣市",
    MISSING_ROAD: "缺少路段",
    NO_ROAD_MATCH: "查無對應路段",
    HOUSE_NUMBER_UNKNOWN: "門牌無法判斷",
    EXTERNAL_TIMEOUT: "外部服務逾時",
    API_ERROR: "API錯誤",
    LOCAL_FALLBACK_OK: "使用本地Fallback成功",
    POST_OK: "中華郵政查詢成功",
    BULK_OK: "大宗郵件專用",
    DISTRICT_FALLBACK: "僅行政區備援",
    BLANK_ADDRESS: "地址格式錯誤",
    UNKNOWN: "無法判斷原因",
}


def label(code: str | None) -> str:
    if not code:
        return REASON_LABELS[UNKNOWN]
    return REASON_LABELS.get(code, code)
