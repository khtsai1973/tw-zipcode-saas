"""舊址／門牌整編對照（可維護）。

全國門牌整編無單一開放總表，各縣市戶政各自公告。
此檔供商務客戶放入「舊地址 → 新地址」對照；查詢前優先套用。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "address_remap.json"


@lru_cache(maxsize=1)
def load_remap_table() -> dict[str, tuple[str, str]]:
    """回傳 {正規化舊址: (新址, 備註)}。"""
    if not DATA_PATH.exists():
        return {}
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    table: dict[str, tuple[str, str]] = {}
    if not isinstance(raw, list):
        return {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        old = str(item.get("old") or "").strip()
        new = str(item.get("new") or "").strip()
        note = str(item.get("note") or "").strip()
        if not old or not new or old == new:
            continue
        table[old] = (new, note or "門牌整編／舊址對照")
        # 台/臺 雙向
        alt = old.replace("臺", "台")
        if alt != old:
            table[alt] = (new, note or "門牌整編／舊址對照")
    return table


def apply_address_remap(address: str) -> tuple[str, bool, str]:
    """若命中對照表，回傳 (新址, 是否改正, 說明)。"""
    text = (address or "").strip()
    if not text:
        return "", False, ""
    table = load_remap_table()
    if not table:
        return text, False, ""
    hit = table.get(text) or table.get(text.replace("台", "臺"))
    if not hit:
        return text, False, ""
    new_addr, note = hit
    return new_addr, True, note


def remap_rule_count() -> int:
    return len(load_remap_table())
