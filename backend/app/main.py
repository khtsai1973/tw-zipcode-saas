"""FastAPI 應用：單筆查詢 + 檔案批次 ETL。"""

from __future__ import annotations

import copy
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.etl.io import MAX_ROWS, SUPPORTED_EXT, read_table, resolve_output_path, write_table
from app.etl.transform import enrich_rows
from app.zipcode.engine import lookup_address, stats


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
STORAGE = Path(__file__).resolve().parents[1] / "storage"
UPLOADS = STORAGE / "uploads"
RESULTS = STORAGE / "results"
UPLOADS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

app = FastAPI(title="台灣 3+3 郵遞區號查詢", version="0.6.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_html_cache(request, call_next):
    """避免瀏覽器快取舊版首頁，把非同步任務初始狀態誤顯示成「完成 0 筆」。"""
    response = await call_next(request)
    path = request.url.path
    ctype = (response.headers.get("content-type") or "").lower()
    if path in {"/", "/index.html"} or "text/html" in ctype:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class LookupRequest(BaseModel):
    address: str = Field(..., min_length=1, description="完整地址")
    name: str | None = None
    use_post_ws: bool = True


def _blank_stats() -> dict:
    return {
        "total": 0,
        "done": 0,
        "success": 0,
        "needs_review": 0,
        "not_found": 0,
        "failed": 0,
        "exact": 0,
        "district": 0,
        "address_column": None,
        "name_column": None,
    }


def _update_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def _safe_unlink(path: Path | None) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _run_job(
    job_id: str,
    upload_path: Path,
    filename: str,
    address_column: str | None,
    name_column: str | None,
) -> None:
    _update_job(job_id, status="processing")
    try:
        columns, rows = read_table(upload_path)
        if len(rows) > MAX_ROWS:
            raise ValueError(f"最多 {MAX_ROWS} 筆，目前 {len(rows)} 筆")

        _update_job(
            job_id,
            progress={"done": 0, "total": len(rows)},
            stats={**_blank_stats(), "total": len(rows)},
        )

        def on_progress(payload: dict) -> None:
            _update_job(
                job_id,
                progress={"done": payload["done"], "total": payload["total"]},
                stats=payload["stats"],
                anomalies=payload["anomalies"],
            )

        out_columns, out_rows, job_stats, anomalies = enrich_rows(
            columns,
            rows,
            address_column,
            name_column,
            on_progress=on_progress,
        )
        out_path = resolve_output_path(filename, job_id, RESULTS)
        write_table(out_columns, out_rows, out_path)
        _update_job(
            job_id,
            status="completed",
            result_file=out_path.name,
            progress={"done": job_stats["total"], "total": job_stats["total"]},
            stats=job_stats,
            anomalies=anomalies,
        )
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, status="failed", error=str(exc))
    finally:
        # 上傳原檔僅暫存，處理結束即清除（不論成功或失敗）
        _safe_unlink(upload_path)


@app.get("/api/health")
def health():
    meta = stats()
    return {
        "ok": True,
        "service": "tw-zipcode-saas",
        "version": "0.6.2",
        "street_rules": meta["street_rules"],
        "bulk_rules": meta["bulk_rules"],
        "post_ws": True,
        "lookup_order": ["normalize", "bulk", "post_ws", "local", "district"],
    }


@app.post("/api/lookup")
def api_lookup(body: LookupRequest):
    result = lookup_address(body.address, name=body.name, use_post_ws=body.use_post_ws)
    data = result.to_dict()
    data["name"] = body.name
    return data


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    address_column: str | None = Form(None),
    name_column: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "未提供檔名")
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXT:
        raise HTTPException(400, f"僅支援：{', '.join(sorted(SUPPORTED_EXT))}")

    job_id = uuid.uuid4().hex
    upload_path = UPLOADS / f"{job_id}{ext}"
    with upload_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    job = {
        "id": job_id,
        "status": "queued",
        "filename": file.filename,
        "result_file": None,
        "progress": {"done": 0, "total": 0},
        "stats": _blank_stats(),
        "anomalies": [],
        "error": None,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, upload_path, file.filename, address_column, name_column),
        daemon=True,
    )
    thread.start()
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "找不到任務")
        return copy.deepcopy(job)


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "找不到任務")
        if job.get("status") != "completed" or not job.get("result_file"):
            raise HTTPException(400, "任務尚未完成")
        result_name = job["result_file"]
        # 下載後即清除結果檔與任務紀錄，避免檔案留存
        job["result_file"] = None
        job["status"] = "downloaded"
    path = RESULTS / result_name
    if not path.exists():
        raise HTTPException(404, "結果檔不存在")
    return FileResponse(
        path,
        filename=path.name,
        background=BackgroundTask(_safe_unlink, path),
    )


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
