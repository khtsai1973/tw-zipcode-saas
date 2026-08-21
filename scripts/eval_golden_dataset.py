"""Golden Dataset 自動評測（200 筆回歸）。

用法（在 backend 目錄）：
  set PYTHONPATH=.
  python ..\\scripts\\eval_golden_dataset.py

選項：
  --limit N          只跑前 N 筆（除錯用）
  --no-post-ws       不呼叫中華郵政（僅本地／行政區）
  --input PATH       金標 CSV（預設 samples/golden/golden_dataset_200.csv）
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.zipcode.engine import lookup_address  # noqa: E402


DEFAULT_INPUT = ROOT / "samples" / "golden" / "golden_dataset_200.csv"
OUT_DIR = ROOT / "samples" / "golden" / "eval"


def _norm(s: str | None) -> str:
    return (s or "").strip().replace("台", "臺")


def _zip3(z: str | None) -> str:
    z = (z or "").strip()
    return z[:3] if len(z) >= 3 else z


def soft_reason_match(expected: str, actual: str) -> bool:
    exp = _norm(expected)
    act = _norm(actual)
    if not exp:
        return True
    if not act:
        return False
    if exp == act:
        return True
    # 關鍵詞互相包含
    if exp in act or act in exp:
        return True
    # 常見同義
    aliases = [
        {"地址格式錯誤", "空白地址", "格式錯誤"},
        {"缺少縣市", "缺縣市"},
        {"缺少路段", "缺路段"},
        {"查無對應路段", "查無"},
        {"門牌無法判斷", "無名牌"},
        {"舊行政區已改制", "舊行政區", "改制"},
        {"舊址已改正", "舊址"},
        {"使用本地Fallback成功", "本地路段", "本地備援"},
        {"中華郵政查詢成功", "中華郵政", "快取命中"},
    ]
    for group in aliases:
        if any(g in exp for g in group) and any(g in act for g in group):
            return True
    return False


def score_row(expected: dict, got) -> dict:
    exp_zip = _norm(expected.get("expected_zipcode"))
    exp_status = _norm(expected.get("expected_status"))
    exp_reason = _norm(expected.get("expected_reason"))

    if got is None:
        got_zip = got_status = got_reason = got_norm = got_source = ""
    else:
        got_zip = _norm(got.zipcode)
        got_status = _norm(got.status)
        got_reason = _norm(got.reason)
        got_norm = _norm(got.normalized)
        got_source = _norm(got.source)

    zip_scored = bool(exp_zip)
    zip_exact = (got_zip == exp_zip) if zip_scored else None
    zip3_ok = (_zip3(got_zip) == _zip3(exp_zip) and bool(_zip3(exp_zip))) if zip_scored else None
    status_scored = bool(exp_status)
    status_ok = (got_status == exp_status) if status_scored else None
    reason_scored = bool(exp_reason)
    reason_ok = soft_reason_match(exp_reason, got_reason) if reason_scored else None

    # 列通過條件：有金標的 zip / status 都要過；reason 僅列入分數不擋 pass
    checks = []
    if zip_scored:
        checks.append(bool(zip_exact))
    if status_scored:
        checks.append(bool(status_ok))
    row_pass = all(checks) if checks else True

    return {
        "got_zipcode": got_zip,
        "got_status": got_status,
        "got_reason": got_reason,
        "got_normalized": got_norm,
        "got_source": got_source,
        "zip_scored": zip_scored,
        "zip_exact": zip_exact,
        "zip3_ok": zip3_ok,
        "status_scored": status_scored,
        "status_ok": status_ok,
        "reason_scored": reason_scored,
        "reason_ok": reason_ok,
        "pass": row_pass,
    }


def load_golden(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def evaluate(
    rows: list[dict],
    *,
    use_post_ws: bool = True,
    limit: int | None = None,
) -> dict:
    selected = rows[:limit] if limit else rows
    detail: list[dict] = []
    cat_stats: dict[str, Counter] = defaultdict(Counter)

    t0 = time.time()
    for i, row in enumerate(selected, start=1):
        addr = row.get("address") or ""
        cid = row.get("id") or f"R{i}"
        category = row.get("category") or "unknown"

        try:
            if not str(addr).strip():
                # 空白地址：模擬引擎外的失敗語意
                class _Blank:
                    zipcode = ""
                    status = "not_found"
                    reason = "地址格式錯誤"
                    normalized = ""
                    source = "none"

                got = _Blank()
            else:
                got = lookup_address(addr, use_post_ws=use_post_ws)
        except Exception as exc:  # noqa: BLE001
            class _Err:
                zipcode = ""
                status = "not_found"
                reason = f"API錯誤（{exc}）"
                normalized = ""
                source = "none"

            got = _Err()

        scored = score_row(row, got)
        rec = {
            "id": cid,
            "category": category,
            "address": addr,
            "expected_zipcode": row.get("expected_zipcode") or "",
            "expected_status": row.get("expected_status") or "",
            "expected_reason": row.get("expected_reason") or "",
            **scored,
        }
        detail.append(rec)

        cat_stats[category]["total"] += 1
        cat_stats[category]["pass" if scored["pass"] else "fail"] += 1
        if scored["zip_exact"] is True:
            cat_stats[category]["zip_hit"] += 1
        if scored["zip_scored"]:
            cat_stats[category]["zip_n"] += 1
        if scored["status_ok"] is True:
            cat_stats[category]["status_hit"] += 1
        if scored["status_scored"]:
            cat_stats[category]["status_n"] += 1
        if scored["reason_ok"] is True:
            cat_stats[category]["reason_hit"] += 1
        if scored["reason_scored"]:
            cat_stats[category]["reason_n"] += 1

        flag = "PASS" if scored["pass"] else "FAIL"
        print(
            f"[{i}/{len(selected)}] {cid} {flag} "
            f"zip={scored['got_zipcode'] or '—'} "
            f"exp={row.get('expected_zipcode') or '—'} "
            f"| {addr[:28]}",
            flush=True,
        )
        if i % 20 == 0:
            time.sleep(0.3)

    elapsed = time.time() - t0
    total = len(detail)
    passed = sum(1 for d in detail if d["pass"])
    zip_n = sum(1 for d in detail if d["zip_scored"])
    zip_hit = sum(1 for d in detail if d["zip_exact"] is True)
    zip3_hit = sum(1 for d in detail if d["zip3_ok"] is True)
    status_n = sum(1 for d in detail if d["status_scored"])
    status_hit = sum(1 for d in detail if d["status_ok"] is True)
    reason_n = sum(1 for d in detail if d["reason_scored"])
    reason_hit = sum(1 for d in detail if d["reason_ok"] is True)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_rows": total,
        "use_post_ws": use_post_ws,
        "elapsed_sec": round(elapsed, 2),
        "pass": passed,
        "fail": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "zip_exact_rate": round(zip_hit / zip_n, 4) if zip_n else None,
        "zip3_rate": round(zip3_hit / zip_n, 4) if zip_n else None,
        "status_rate": round(status_hit / status_n, 4) if status_n else None,
        "reason_rate": round(reason_hit / reason_n, 4) if reason_n else None,
        "zip_n": zip_n,
        "zip_hit": zip_hit,
        "status_n": status_n,
        "status_hit": status_hit,
        "reason_n": reason_n,
        "reason_hit": reason_hit,
        "by_category": {
            cat: {
                "total": int(c["total"]),
                "pass": int(c["pass"]),
                "fail": int(c["fail"]),
                "pass_rate": round(c["pass"] / c["total"], 4) if c["total"] else 0.0,
                "zip_exact_rate": round(c["zip_hit"] / c["zip_n"], 4) if c["zip_n"] else None,
                "status_rate": round(c["status_hit"] / c["status_n"], 4) if c["status_n"] else None,
                "reason_rate": round(c["reason_hit"] / c["reason_n"], 4) if c["reason_n"] else None,
            }
            for cat, c in sorted(cat_stats.items())
        },
    }
    return {"summary": summary, "detail": detail}


def write_outputs(report: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"eval_report_{stamp}.json"
    latest_json = OUT_DIR / "eval_report_latest.json"
    csv_path = OUT_DIR / f"eval_failures_{stamp}.csv"
    md_path = OUT_DIR / f"eval_summary_{stamp}.md"
    latest_md = OUT_DIR / "eval_summary_latest.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fails = [d for d in report["detail"] if not d["pass"]]
    fields = [
        "id",
        "category",
        "address",
        "expected_zipcode",
        "got_zipcode",
        "expected_status",
        "got_status",
        "expected_reason",
        "got_reason",
        "got_normalized",
        "got_source",
        "zip_exact",
        "status_ok",
        "reason_ok",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in fails:
            w.writerow(row)

    s = report["summary"]
    lines = [
        f"# Golden Dataset 自動評測報告",
        "",
        f"- 時間：`{s['generated_at']}`",
        f"- 筆數：{s['input_rows']}",
        f"- 使用郵政 WS：{s['use_post_ws']}",
        f"- 耗時：{s['elapsed_sec']} 秒",
        "",
        "## 總覽",
        "",
        f"| 指標 | 數值 |",
        f"|------|------|",
        f"| 通過 | {s['pass']} / {s['input_rows']}（{s['pass_rate']*100:.1f}%） |",
        f"| 失敗 | {s['fail']} |",
        f"| 郵遞區號完全相符 | {s['zip_hit']} / {s['zip_n']}（{(s['zip_exact_rate'] or 0)*100:.1f}%） |",
        f"| 前3碼相符 | {(s['zip3_rate'] or 0)*100:.1f}% |",
        f"| 狀態相符 | {s['status_hit']} / {s['status_n']}（{(s['status_rate'] or 0)*100:.1f}%） |",
        f"| 原因相符（寬鬆） | {s['reason_hit']} / {s['reason_n']}（{(s['reason_rate'] or 0)*100:.1f}%） |",
        "",
        "## 分類",
        "",
        "| category | total | pass | fail | pass% | zip% | status% |",
        "|----------|------:|-----:|-----:|------:|-----:|--------:|",
    ]
    for cat, c in s["by_category"].items():
        lines.append(
            f"| {cat} | {c['total']} | {c['pass']} | {c['fail']} | "
            f"{c['pass_rate']*100:.1f}% | "
            f"{(c['zip_exact_rate'] or 0)*100:.1f}% | "
            f"{(c['status_rate'] or 0)*100:.1f}% |"
        )
    lines += [
        "",
        f"失敗明細：`{csv_path.name}`（共 {len(fails)} 筆）",
        "",
    ]
    md = "\n".join(lines)
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")

    print(md)
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    return latest_md


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate golden dataset")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-post-ws", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"找不到金標檔：{args.input}")

    rows = load_golden(args.input)
    report = evaluate(rows, use_post_ws=not args.no_post_ws, limit=args.limit)
    write_outputs(report)


if __name__ == "__main__":
    main()
