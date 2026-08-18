"""大宗郵件專用郵遞區號查詢（正規化後優先）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .normalize import normalize_address

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BULK_FILE = DATA_DIR / "bulk_zipcodes.json"


@dataclass
class BulkHit:
    zipcode: str
    matched_address: str
    matched_name: str | None
    note: str = ""


def _builtin_samples() -> list[dict]:
    """示範用大宗專用碼（可被 data/bulk_zipcodes.json 覆寫／擴充）。"""
    return [
        {
            "name": "",
            "address": "臺北市信義區市府路1號",
            "zip6": "110208",
            "note": "示範：臺北市政府（請替換為貴司大宗專用表）",
        },
    ]


@lru_cache(maxsize=1)
def load_bulk_rules() -> list[dict]:
    if BULK_FILE.exists():
        raw = json.loads(BULK_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict) and r.get("zip6")]
    return _builtin_samples()


@lru_cache(maxsize=1)
def _bulk_indexes() -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    """
    回傳：
    - by_addr: 正規化地址 → rule
    - by_name_addr: (正規化名稱, 正規化地址) → rule
    """
    by_addr: dict[str, dict] = {}
    by_name_addr: dict[tuple[str, str], dict] = {}
    for rule in load_bulk_rules():
        zip6 = str(rule.get("zip6", "")).strip()
        if not zip6 or len(zip6) != 6 or not zip6.isdigit():
            continue
        addr = normalize_address(str(rule.get("address", "") or ""))
        name = str(rule.get("name", "") or "").strip().replace(" ", "")
        if addr:
            # 後寫入覆蓋先寫入；檔案後面的規則優先
            by_addr[addr] = rule
        if name and addr:
            by_name_addr[(name, addr)] = rule
    return by_addr, by_name_addr


def reload_bulk_rules() -> int:
    load_bulk_rules.cache_clear()
    _bulk_indexes.cache_clear()
    return len(load_bulk_rules())


def lookup_bulk(address: str, name: str | None = None) -> BulkHit | None:
    """
    大宗專用碼優先比對：
    1. 名稱 + 正規化地址
    2. 僅正規化地址
    """
    addr = normalize_address(address or "")
    if not addr:
        return None
    name_key = (name or "").strip().replace(" ", "")
    by_addr, by_name_addr = _bulk_indexes()

    if name_key:
        rule = by_name_addr.get((name_key, addr))
        if rule:
            return BulkHit(
                zipcode=str(rule["zip6"]),
                matched_address=addr,
                matched_name=name_key,
                note=str(rule.get("note", "") or "大宗郵件專用郵遞區號"),
            )

    rule = by_addr.get(addr)
    if rule:
        return BulkHit(
            zipcode=str(rule["zip6"]),
            matched_address=addr,
            matched_name=None,
            note=str(rule.get("note", "") or "大宗郵件專用郵遞區號"),
        )
    return None


def bulk_rule_count() -> int:
    return len(load_bulk_rules())
