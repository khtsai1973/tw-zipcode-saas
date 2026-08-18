"""路段級 3+3 規則載入與索引。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# city, district, road, begin, end, side(0雙1單2連), zip6
Rule = dict[str, object]

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STREET_FILE = DATA_DIR / "street_rules.json"


def _builtin_rules() -> list[Rule]:
    """內建精簡規則（檔案缺失時備援）。"""
    return [
        {"city": "臺北市", "district": "大安區", "road": "愛國東路", "begin": 1, "end": 9999, "side": 2, "zip6": "106041"},
        {"city": "臺北市", "district": "中正區", "road": "重慶南路一段", "begin": 1, "end": 9999, "side": 2, "zip6": "100006"},
    ]


@lru_cache(maxsize=1)
def load_street_rules() -> list[Rule]:
    if STREET_FILE.exists():
        raw = json.loads(STREET_FILE.read_text(encoding="utf-8"))
        rules: list[Rule] = []
        for item in raw:
            if isinstance(item, dict):
                rules.append(item)
            else:
                city, district, road, begin, end, side, zip6 = item
                rules.append(
                    {
                        "city": city,
                        "district": district,
                        "road": road,
                        "begin": int(begin),
                        "end": int(end),
                        "side": int(side),
                        "zip6": str(zip6),
                    }
                )
        return rules
    return _builtin_rules()


@lru_cache(maxsize=1)
def street_index() -> dict[tuple[str, str, str], list[Rule]]:
    index: dict[tuple[str, str, str], list[Rule]] = {}
    for rule in load_street_rules():
        key = (str(rule["city"]), str(rule["district"]), str(rule["road"]))
        index.setdefault(key, []).append(rule)
    return index


def reload_street_rules() -> int:
    load_street_rules.cache_clear()
    street_index.cache_clear()
    return len(load_street_rules())
