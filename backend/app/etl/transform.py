"""批次查詢 transform：正規化 + 完整 3+3。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from app.zipcode.engine import lookup_address

from .io import NORM_COL, STATUS_COL, ZIP_COL, detect_columns


def enrich_rows(
    columns: list[str],
    rows: list[dict[str, str]],
    address_column: str | None = None,
    name_column: str | None = None,
    *,
    use_post_ws: bool = True,
    workers: int = 8,
) -> tuple[list[str], list[dict[str, str]], dict]:
    mapping = detect_columns(columns)
    addr_col = address_column or mapping["address"]
    name_col = name_column or mapping["name"]

    if not addr_col or addr_col not in columns:
        raise ValueError("找不到地址欄位，請指定 address_column，或使用「地址」等欄名")

    out_columns = list(columns)
    for col in (NORM_COL, ZIP_COL, STATUS_COL):
        if col not in out_columns:
            out_columns.append(col)

    # 先準備結果容器，保持原列順序
    results: list[dict[str, str] | None] = [None] * len(rows)

    def _process(idx: int, row: dict[str, str]) -> tuple[int, dict[str, str], str]:
        new_row = dict(row)
        addr = str(row.get(addr_col, "") or "").strip()
        if not addr:
            new_row[NORM_COL] = ""
            new_row[ZIP_COL] = ""
            new_row[STATUS_COL] = "空白地址"
            return idx, new_row, "failed"
        result = lookup_address(
            addr,
            name=str(row.get(name_col, "") or "").strip() if name_col else None,
            use_post_ws=use_post_ws,
        )
        new_row[NORM_COL] = result.normalized or ""
        new_row[ZIP_COL] = result.zipcode or ""
        if result.status == "exact":
            if result.source == "bulk":
                new_row[STATUS_COL] = "大宗專用"
            else:
                new_row[STATUS_COL] = "精確"
            return idx, new_row, "exact"
        if result.status == "district":
            new_row[STATUS_COL] = "行政區"
            return idx, new_row, "district"
        new_row[STATUS_COL] = "查無"
        return idx, new_row, "failed"

    ok = partial = fail = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_process, i, row) for i, row in enumerate(rows)]
        for fut in as_completed(futures):
            idx, new_row, kind = fut.result()
            results[idx] = new_row
            if kind == "exact":
                ok += 1
            elif kind == "district":
                partial += 1
            else:
                fail += 1

    out_rows = [r if r is not None else dict(rows[i]) for i, r in enumerate(results)]
    stats = {
        "total": len(out_rows),
        "exact": ok,
        "district": partial,
        "failed": fail,
        "address_column": addr_col,
        "name_column": name_col,
    }
    return out_columns, out_rows, stats
