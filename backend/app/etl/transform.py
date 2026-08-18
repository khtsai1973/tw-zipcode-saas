"""批次查詢 transform：正規化 + 完整 3+3。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.zipcode.engine import lookup_address

from .io import NORM_COL, STATUS_COL, ZIP_COL, detect_columns

ProgressCallback = Callable[[dict], None]


def _empty_counts() -> dict[str, int]:
    return {
        "total": 0,
        "done": 0,
        "success": 0,
        "needs_review": 0,
        "not_found": 0,
        "failed": 0,
        # 向後相容舊欄位
        "exact": 0,
        "district": 0,
    }


def enrich_rows(
    columns: list[str],
    rows: list[dict[str, str]],
    address_column: str | None = None,
    name_column: str | None = None,
    *,
    use_post_ws: bool = True,
    workers: int = 8,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[str], list[dict[str, str]], dict, list[dict]]:
    mapping = detect_columns(columns)
    addr_col = address_column or mapping["address"]
    name_col = name_column or mapping["name"]

    if not addr_col or addr_col not in columns:
        raise ValueError("找不到地址欄位，請指定 address_column，或使用「地址」等欄名")

    out_columns = list(columns)
    for col in (NORM_COL, ZIP_COL, STATUS_COL):
        if col not in out_columns:
            out_columns.append(col)

    results: list[dict[str, str] | None] = [None] * len(rows)
    anomalies: list[dict] = []
    counts = _empty_counts()
    counts["total"] = len(rows)

    def _emit() -> None:
        if on_progress is None:
            return
        on_progress(
            {
                "done": counts["done"],
                "total": counts["total"],
                "stats": {
                    "total": counts["total"],
                    "done": counts["done"],
                    "success": counts["success"],
                    "needs_review": counts["needs_review"],
                    "not_found": counts["not_found"],
                    "failed": counts["failed"],
                    "exact": counts["success"],
                    "district": counts["needs_review"],
                    "address_column": addr_col,
                    "name_column": name_col,
                },
                "anomalies": list(anomalies),
            }
        )

    def _process(idx: int, row: dict[str, str]) -> tuple[int, dict[str, str], str, dict | None]:
        new_row = dict(row)
        name_val = str(row.get(name_col, "") or "").strip() if name_col else ""
        addr = str(row.get(addr_col, "") or "").strip()
        if not addr:
            new_row[NORM_COL] = ""
            new_row[ZIP_COL] = ""
            new_row[STATUS_COL] = "空白地址"
            anomaly = {
                "row": idx + 1,
                "name": name_val,
                "address": "",
                "normalized": "",
                "zipcode": "",
                "status": "失敗",
                "status_raw": "空白地址",
                "category": "failed",
            }
            return idx, new_row, "failed", anomaly

        try:
            result = lookup_address(
                addr,
                name=name_val or None,
                use_post_ws=use_post_ws,
            )
        except Exception as exc:  # noqa: BLE001
            new_row[NORM_COL] = ""
            new_row[ZIP_COL] = ""
            new_row[STATUS_COL] = "失敗"
            anomaly = {
                "row": idx + 1,
                "name": name_val,
                "address": addr,
                "normalized": "",
                "zipcode": "",
                "status": "失敗",
                "status_raw": str(exc),
                "category": "failed",
            }
            return idx, new_row, "failed", anomaly

        new_row[NORM_COL] = result.normalized or ""
        new_row[ZIP_COL] = result.zipcode or ""

        if result.status == "exact":
            if result.source == "bulk":
                new_row[STATUS_COL] = "大宗專用"
            else:
                new_row[STATUS_COL] = "精確"
            return idx, new_row, "success", None

        if result.status == "district":
            new_row[STATUS_COL] = "行政區"
            anomaly = {
                "row": idx + 1,
                "name": name_val,
                "address": addr,
                "normalized": new_row[NORM_COL],
                "zipcode": new_row[ZIP_COL],
                "status": "需確認",
                "status_raw": "行政區",
                "category": "needs_review",
            }
            return idx, new_row, "needs_review", anomaly

        new_row[STATUS_COL] = "查無"
        anomaly = {
            "row": idx + 1,
            "name": name_val,
            "address": addr,
            "normalized": new_row[NORM_COL],
            "zipcode": new_row[ZIP_COL],
            "status": "查無資料",
            "status_raw": "查無",
            "category": "not_found",
        }
        return idx, new_row, "not_found", anomaly

    _emit()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_process, i, row) for i, row in enumerate(rows)]
        for fut in as_completed(futures):
            idx, new_row, kind, anomaly = fut.result()
            results[idx] = new_row
            counts["done"] += 1
            counts[kind] += 1
            if anomaly is not None:
                anomalies.append(anomaly)
            _emit()

    anomalies.sort(key=lambda item: item["row"])
    out_rows = [r if r is not None else dict(rows[i]) for i, r in enumerate(results)]
    stats = {
        "total": len(out_rows),
        "done": counts["done"],
        "success": counts["success"],
        "needs_review": counts["needs_review"],
        "not_found": counts["not_found"],
        "failed": counts["failed"],
        "exact": counts["success"],
        "district": counts["needs_review"],
        "address_column": addr_col,
        "name_column": name_col,
    }
    return out_columns, out_rows, stats, anomalies
