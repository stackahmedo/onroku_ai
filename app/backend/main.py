"""
main.py  –  V2 FastAPI backend
Routes:
  GET  /health
  GET  /hardware
  POST /upload
  GET  /job/{job_id}
  GET  /jobs
  GET  /progress/{job_id}    ← SSE stream
  POST /cancel/{job_id}
  POST /export/{job_id}      ← query param: format=txt|csv|excel
  DELETE /job/{job_id}
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from database_service import DatabaseService
from export_service import export_transcript
from hardware_detector import detect_hardware
from transcription_service import TranscriptionService, cancel_job, pause_job, resume_job

# ── Logging & Path Setup ───────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent.parent
UPLOAD_DIR     = BASE_DIR / "app" / "storage" / "uploads"
TRANSCRIPT_DIR  = BASE_DIR / "app" / "storage" / "transcripts"
EXPORT_DIR     = BASE_DIR / "app" / "storage" / "exports"
DB_PATH        = BASE_DIR / "app" / "database" / "app.db"
LOGS_DIR       = BASE_DIR / "app" / "storage" / "logs"
SETTINGS_FILE  = BASE_DIR / "app" / "storage" / "settings.json"

for d in [UPLOAD_DIR, TRANSCRIPT_DIR, EXPORT_DIR, DB_PATH.parent, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "backend.log"

# Clean up older backend logs on startup so the file doesn't grow infinitely
if LOG_FILE.exists():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.truncate(0)
    except:
        pass

# Configure root logger with custom formatters to write to both stdout and backend.log
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# File Handler for developer background logs
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# ── Settings helper functions ──────────────────────────────────────
def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read settings: {e}")
    return {"transcript_export_dir": str(EXPORT_DIR)}


def save_settings(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write settings: {e}")

# ── Hardware detection (done once at startup) ───────────────────────
HARDWARE = detect_hardware()
logger.info(f"Hardware profile: {HARDWARE}")

# ── Service singletons ──────────────────────────────────────────────
transcription_service = TranscriptionService(HARDWARE)
db_service = DatabaseService(DB_PATH)

# ── FastAPI app ─────────────────────────────────────────────────────
app = FastAPI(title="Transcript AI V2", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Progress store (in-memory; job_id → {pct, label}) ──────────────
_PROGRESS: dict[str, dict] = {}


@app.on_event("startup")
async def startup():
    db_service.init_db()
    logger.info("Transcript AI V2 started")


# ── Routes ──────────────────────────────────────────────────────────

@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "version": "2.0.0"}


@app.get("/hardware")
@app.head("/hardware")
async def hardware():
    return HARDWARE


@app.post("/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Query(default="ja"),
    model: str = Query(default="auto"),
    speaker_count: int | None = Query(default=None),
    chunk_seconds: int | None = Query(default=None),
):
    try:
        file_id = str(uuid.uuid4())
        suffix = Path(file.filename).suffix or ".wav"
        upload_path = UPLOAD_DIR / f"{file_id}{suffix}"

        # Stream file to disk
        with open(upload_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        actual_model_name = HARDWARE["model_name"] if model == "auto" else model

        job_id = db_service.create_job(
            file_id=file_id,
            filename=file.filename,
            file_path=str(upload_path),
            hardware_tier=HARDWARE["tier"],
            model_name=actual_model_name,
            language=language,
        )

        _PROGRESS[job_id] = {"pct": 0, "label": "待機中... / Waiting..."}
        background_tasks.add_task(_run_transcription, job_id, str(upload_path), language, actual_model_name, speaker_count, chunk_seconds)

        logger.info(f"Uploaded: {file.filename} → job {job_id} with model {actual_model_name}")
        return {
            "job_id": job_id,
            "file_id": file_id,
            "filename": file.filename,
            "status": "processing",
            "hardware_tier": HARDWARE["tier"],
            "model_name": actual_model_name,
        }

    except Exception as e:
        logger.exception("Upload error")
        raise HTTPException(status_code=400, detail=str(e))


def _run_transcription(job_id: str, file_path: str, language: str, model_name: str, speaker_count: int | None = None, chunk_seconds: int | None = None):
    """Background task: run full transcription pipeline."""
    import time
    last_db_pct = -1
    last_db_time = 0.0

    def _progress_cb(pct: int, label: str):
        nonlocal last_db_pct, last_db_time
        # Update live memory status immediately (for instant SSE stream updates)
        _PROGRESS[job_id] = {"pct": pct, "label": label}
        
        # Only commit to SQLite on major checkpoints, when progress changes by >= 5%, 
        # or when at least 3 seconds have passed since the last disk commit.
        # This completely resolves the SQLite disk I/O bottleneck on Windows during rapid segment yields.
        now = time.time()
        is_major = pct in (0, 1, 2, 5, 8, 10, 82, 98, 100)
        if is_major or (pct - last_db_pct >= 5) or (now - last_db_time >= 3.0):
            try:
                db_service.update_progress(job_id, pct, label)
                last_db_pct = pct
                last_db_time = now
            except Exception as e:
                logger.warning(f"Throttled progress DB write failed: {e}")

    def _duration_cb(dur: float):
        try:
            db_service.update_job_duration(job_id, dur)
        except Exception as e:
            logger.warning(f"Failed to update duration in DB: {e}")

    def _lang_cb(detected_lang: str):
        try:
            db_service.update_job_language(job_id, detected_lang)
            logger.info(f"Auto-detected language for job {job_id}: {detected_lang}")
        except Exception as e:
            logger.warning(f"Failed to update auto-detected language in DB: {e}")

    try:
        db_service.update_job_status(job_id, "transcribing")
        _progress_cb(1, "開始中... / Starting...")

        segments = transcription_service.transcribe_file(
            file_path,
            job_id,
            language=language,
            model_name=model_name,
            progress_cb=_progress_cb,
            on_duration_known=_duration_cb,
            num_speakers=speaker_count,
            chunk_seconds=chunk_seconds,
            on_language_detected=_lang_cb,
        )

        # Save JSON transcript
        file_id = db_service.get_job(job_id)["file_id"]
        transcript_path = TRANSCRIPT_DIR / f"{file_id}_transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

        speakers = len({s["speaker"] for s in segments})
        db_service.save_transcript(job_id, str(transcript_path), len(segments), speakers)
        db_service.update_job_status(job_id, "completed")
        _progress_cb(100, "完了 / Completed")
        logger.info(f"Transcription done: {job_id} ({len(segments)} segments)")

    except InterruptedError:
        db_service.update_job_status(job_id, "cancelled")
        _progress_cb(0, "キャンセル済み / Cancelled")
    except Exception as e:
        logger.exception(f"Transcription error for job {job_id}")
        db_service.update_job_status(job_id, "failed", error_message=str(e))
        _progress_cb(0, f"エラー / Error: {e}")
    finally:
        # Optionally clean up upload file
        pass


@app.get("/job/{job_id}")
async def get_job(job_id: str):
    job = db_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Merge live progress
    if job_id in _PROGRESS:
        job["progress_pct"] = _PROGRESS[job_id]["pct"]
        job["progress_label"] = _PROGRESS[job_id]["label"]
    return job


@app.get("/jobs")
async def list_jobs(skip: int = 0, limit: int = 20):
    jobs = db_service.get_jobs(skip, limit)
    return {"jobs": jobs, "total": len(jobs)}


@app.get("/progress/{job_id}")
async def progress_stream(job_id: str):
    """Server-Sent Events stream for real-time progress."""
    async def generator():
        while True:
            job = db_service.get_job(job_id)
            if not job:
                yield {"event": "error", "data": json.dumps({"error": "not found"})}
                break

            prog = _PROGRESS.get(job_id, {"pct": job.get("progress_pct", 0), "label": job.get("progress_label", "")})
            
            elapsed = 0
            if "created_at" in job:
                try:
                    created_at = datetime.fromisoformat(job["created_at"])
                    elapsed = int((datetime.now() - created_at).total_seconds())
                except:
                    pass

            data = {
                "pct":              prog["pct"],
                "label":            prog["label"],
                "status":           job["status"],
                "duration_seconds": job.get("duration_seconds"),
                "elapsed_seconds":  elapsed,
            }
            yield {"event": "progress", "data": json.dumps(data)}

            if job["status"] in ("completed", "failed", "cancelled"):
                yield {"event": "done", "data": json.dumps(data)}
                break

            await asyncio.sleep(1)

    return EventSourceResponse(generator())


@app.post("/cancel/{job_id}")
async def cancel(job_id: str):
    job = db_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cancel_job(job_id)
    return {"message": "Cancel requested", "job_id": job_id}


@app.post("/pause/{job_id}")
async def pause(job_id: str):
    job = db_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    pause_job(job_id)
    db_service.update_job_status(job_id, "paused")
    # Instantly reflect in the live SSE progress dictionary
    if job_id in _PROGRESS:
        _PROGRESS[job_id]["label"] = "一時停止中 / Paused..."
    return {"message": "Pause requested", "job_id": job_id}


@app.post("/resume/{job_id}")
async def resume(job_id: str):
    job = db_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    resume_job(job_id)
    db_service.update_job_status(job_id, "transcribing")
    # Instantly reflect in the live SSE progress dictionary
    if job_id in _PROGRESS:
        _PROGRESS[job_id]["label"] = "再開中 / Resuming..."
    return {"message": "Resume requested", "job_id": job_id}


@app.post("/export/{job_id}")
async def export(job_id: str, format: str = Query(default="excel")):
    if format not in ("txt", "csv", "excel"):
        raise HTTPException(status_code=400, detail="format must be txt, csv, or excel")

    job = db_service.get_job(job_id)
    if not job or not job.get("transcript_file"):
        raise HTTPException(status_code=404, detail="Transcript not found")

    mime_map = {
        "txt":   "text/plain; charset=utf-8",
        "csv":   "text/csv; charset=utf-8",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    ext_map = {"txt": "txt", "csv": "csv", "excel": "xlsx"}

    try:
        settings = load_settings()
        custom_dir = settings.get("transcript_export_dir")
        if custom_dir:
            target_dir = Path(custom_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            target_dir = EXPORT_DIR

        out_path = export_transcript(job["transcript_file"], format, target_dir)
        filename = f"transcript_{job_id[:8]}.{ext_map[format]}"
        return FileResponse(
            out_path,
            media_type=mime_map[format],
            filename=filename,
        )
    except Exception as e:
        logger.exception("Export error")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    job = db_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_service.delete_job(job_id)
    _PROGRESS.pop(job_id, None)
    return {"message": "Deleted", "job_id": job_id}


@app.get("/transcript/{job_id}")
async def get_transcript(job_id: str):
    job = db_service.get_job(job_id)
    if not job or not job.get("transcript_file"):
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    transcript_path = Path(job["transcript_file"])
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail="Transcript file not found on disk")
        
    with open(transcript_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
    return {"segments": segments}


from fastapi import Body

@app.post("/transcript/{job_id}/rename-speakers")
async def rename_speakers(job_id: str, payload: dict = Body(...)):
    job = db_service.get_job(job_id)
    if not job or not job.get("transcript_file"):
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    transcript_path = Path(job["transcript_file"])
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail="Transcript file not found on disk")
        
    mapping = payload.get("mapping", {})
    if not mapping:
        return {"message": "No mapping provided"}
        
    with open(transcript_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
        
    changed = False
    for seg in segments:
        current_spk = seg.get("speaker", "Unknown")
        if current_spk in mapping:
            seg["speaker"] = mapping[current_spk]
            changed = True
            
    if changed:
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
            
        speakers = len({s["speaker"] for s in segments})
        db_service.save_transcript(job_id, str(transcript_path), len(segments), speakers)
        
    return {"message": "Speakers renamed successfully", "speaker_count": len({s["speaker"] for s in segments})}


# ── Settings & Logs Endpoints ─────────────────────────────────────

@app.get("/settings")
async def get_settings():
    return load_settings()


@app.post("/settings")
async def update_settings(payload: dict):
    settings = load_settings()
    if "transcript_export_dir" in payload:
        path_str = payload["transcript_export_dir"]
        if path_str:
            p = Path(path_str)
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid folder path: {e}")
        settings["transcript_export_dir"] = path_str
    save_settings(settings)
    return settings


@app.get("/logs")
async def get_logs(limit: int = 150):
    if not LOG_FILE.exists():
        return {"logs": []}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        recent = lines[-limit:] if len(lines) > limit else lines
        return {"logs": [line.strip() for line in recent]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
