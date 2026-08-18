"""FastAPI 應用：單筆查詢 + 檔案批次 ETL。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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

app = FastAPI(title="台灣 3+3 郵遞區號查詢", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LookupRequest(BaseModel):
    address: str = Field(..., min_length=1, description="完整地址")
    name: str | None = None
    use_post_ws: bool = True


@app.get("/api/health")
def health():
    meta = stats()
    return {
        "ok": True,
        "service": "tw-zipcode-saas",
        "version": "0.4.0",
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

    try:
        columns, rows = read_table(upload_path)
        if len(rows) > MAX_ROWS:
            raise HTTPException(400, f"最多 {MAX_ROWS} 筆，目前 {len(rows)} 筆")
        out_columns, out_rows, stats = enrich_rows(columns, rows, address_column, name_column)
        out_path = resolve_output_path(file.filename, job_id, RESULTS)
        write_table(out_columns, out_rows, out_path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc

    JOBS[job_id] = {
        "id": job_id,
        "status": "completed",
        "filename": file.filename,
        "result_file": str(out_path.name),
        "stats": stats,
    }
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "找不到任務")
    return job


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "找不到任務")
    path = RESULTS / job["result_file"]
    if not path.exists():
        raise HTTPException(404, "結果檔不存在")
    return FileResponse(path, filename=path.name)


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
