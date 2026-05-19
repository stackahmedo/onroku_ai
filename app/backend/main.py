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
    default_settings = {
        "transcript_export_dir": str(EXPORT_DIR),
        "pdf_max_chars_per_page": 1000,
        "pdf_template": "corporate"
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge defaults
                for k, v in default_settings.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            logger.warning(f"Failed to read settings: {e}")
    return default_settings


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
app = FastAPI(title="Onroku AI", version="5.5.0")
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
    logger.info("Onroku AI started")


# ── Routes ──────────────────────────────────────────────────────────

@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "version": "5.5.0"}


@app.get("/hardware")
@app.head("/hardware")
async def hardware():
    return HARDWARE


@app.post("/clear-cache")
async def clear_cache():
    try:
        bytes_cleared = 0
        files_cleared = 0
        
        # 1. Clear files in UPLOAD_DIR
        if UPLOAD_DIR.exists():
            for f in UPLOAD_DIR.iterdir():
                if f.is_file():
                    try:
                        bytes_cleared += f.stat().st_size
                        f.unlink()
                        files_cleared += 1
                    except Exception as err:
                        logger.warning(f"Failed to delete upload file {f}: {err}")
        
        # 2. Clear files in EXPORT_DIR
        if EXPORT_DIR.exists():
            for f in EXPORT_DIR.iterdir():
                if f.is_file():
                    try:
                        bytes_cleared += f.stat().st_size
                        f.unlink()
                        files_cleared += 1
                    except Exception as err:
                        logger.warning(f"Failed to delete export file {f}: {err}")
                        
        # 3. Clean up temp folder files starting with tscr_
        import tempfile
        temp_root = Path(tempfile.gettempdir())
        if temp_root.exists():
            for item in temp_root.iterdir():
                if item.name.startswith("tscr_"):
                    try:
                        if item.is_dir():
                            for sub in item.glob("**/*"):
                                if sub.is_file():
                                    bytes_cleared += sub.stat().st_size
                            shutil.rmtree(item, ignore_errors=True)
                        elif item.is_file():
                            bytes_cleared += item.stat().st_size
                            item.unlink()
                        files_cleared += 1
                    except Exception as err:
                        logger.warning(f"Failed to delete temp item {item}: {err}")

        mb_cleared = round(bytes_cleared / (1024 * 1024), 2)
        logger.info(f"Cache cleared: {files_cleared} files, {mb_cleared} MB released.")
        return {
            "success": True,
            "files_cleared": files_cleared,
            "mb_cleared": mb_cleared,
            "message": f"Successfully cleared {files_cleared} cache files ({mb_cleared} MB released)."
        }
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        import os
        try:
            file_size_bytes = os.path.getsize(upload_path)
        except Exception:
            file_size_bytes = 0

        actual_model_name = HARDWARE["model_name"] if model == "auto" else model

        job_id = db_service.create_job(
            file_id=file_id,
            filename=file.filename,
            file_path=str(upload_path),
            hardware_tier=HARDWARE["tier"],
            model_name=actual_model_name,
            language=language,
            file_size_bytes=file_size_bytes,
        )

        _PROGRESS[job_id] = {"pct": 0, "label": "待機中... / Waiting..."}
        background_tasks.add_task(_run_transcription, job_id, str(upload_path), language, actual_model_name, speaker_count, chunk_seconds)

        logger.info(f"Uploaded: {file.filename} → job {job_id} with model {actual_model_name} (Size: {file_size_bytes} bytes)")
        return {
            "job_id": job_id,
            "file_id": file_id,
            "filename": file.filename,
            "status": "processing",
            "hardware_tier": HARDWARE["tier"],
            "model_name": actual_model_name,
            "file_size_bytes": file_size_bytes,
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
    
    # Self-heal missing file size
    if (not job.get("file_size_bytes") or job.get("file_size_bytes") == 0) and job.get("file_path"):
        try:
            import os
            p = os.path.getsize(job["file_path"])
            if p > 0:
                job["file_size_bytes"] = p
                db_service.update_job_size(job_id, p)
        except Exception as e:
            logger.warning(f"Self-heal file size failed for {job_id}: {e}")

    # Merge live progress
    if job_id in _PROGRESS:
        job["progress_pct"] = _PROGRESS[job_id]["pct"]
        job["progress_label"] = _PROGRESS[job_id]["label"]
    return job


@app.get("/jobs")
async def list_jobs(skip: int = 0, limit: int = 20):
    jobs = db_service.get_jobs(skip, limit)
    # Self-heal missing file sizes
    import os
    for job in jobs:
        if (not job.get("file_size_bytes") or job.get("file_size_bytes") == 0) and job.get("file_path"):
            try:
                p = os.path.getsize(job["file_path"])
                if p > 0:
                    job["file_size_bytes"] = p
                    db_service.update_job_size(job["id"], p)
            except Exception as e:
                logger.warning(f"Self-heal list file size failed for {job['id']}: {e}")
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

            # Maintain persistent in-memory elapsed timer to halt counting when paused
            prog = _PROGRESS.get(job_id)
            if not prog:
                prog = {
                    "pct": job.get("progress_pct", 0),
                    "label": job.get("progress_label", ""),
                    "elapsed": 0,
                    "last_tick": None
                }
                _PROGRESS[job_id] = prog

            if "elapsed" not in prog:
                prog["elapsed"] = 0
            if "last_tick" not in prog:
                prog["last_tick"] = None

            now_time = datetime.now()
            if job["status"] in ("transcribing", "pending"):
                if prog["last_tick"]:
                    delta = int((now_time - prog["last_tick"]).total_seconds())
                    if delta > 0:
                        prog["elapsed"] += delta
                        prog["last_tick"] = now_time
                else:
                    try:
                        created_at = datetime.fromisoformat(job["created_at"])
                        prog["elapsed"] = int((now_time - created_at).total_seconds())
                    except:
                        prog["elapsed"] = 0
                    prog["last_tick"] = now_time
            elif job["status"] == "paused":
                prog["last_tick"] = now_time
            else:
                prog["last_tick"] = None

            elapsed = prog["elapsed"]

            # Self-heal missing file size in progress stream
            if (not job.get("file_size_bytes") or job.get("file_size_bytes") == 0) and job.get("file_path"):
                try:
                    import os
                    p = os.path.getsize(job["file_path"])
                    if p > 0:
                        job["file_size_bytes"] = p
                        db_service.update_job_size(job_id, p)
                except:
                    pass

            data = {
                "pct":              prog["pct"],
                "label":            prog["label"],
                "status":           job["status"],
                "duration_seconds": job.get("duration_seconds"),
                "file_size_bytes":  job.get("file_size_bytes"),
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
    if format not in ("txt", "csv", "excel", "pdf"):
        raise HTTPException(status_code=400, detail="format must be txt, csv, excel, or pdf")

    job = db_service.get_job(job_id)
    if not job or not job.get("transcript_file"):
        raise HTTPException(status_code=404, detail="Transcript not found")

    mime_map = {
        "txt":   "text/plain; charset=utf-8",
        "csv":   "text/csv; charset=utf-8",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf":   "application/pdf",
    }
    ext_map = {"txt": "txt", "csv": "csv", "excel": "xlsx", "pdf": "pdf"}

    try:
        settings = load_settings()
        custom_dir = settings.get("transcript_export_dir")
        max_chars = settings.get("pdf_max_chars_per_page", 1000)
        pdf_template = settings.get("pdf_template", "corporate")
        
        if custom_dir:
            target_dir = Path(custom_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            target_dir = EXPORT_DIR

        out_path = export_transcript(job["transcript_file"], format, target_dir, max_chars, pdf_template)
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
    if "pdf_max_chars_per_page" in payload:
        try:
            val = int(payload["pdf_max_chars_per_page"])
            if val < 50:
                raise ValueError("PDF characters per page must be at least 50")
            settings["pdf_max_chars_per_page"] = val
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid character limit: {e}")
    if "pdf_template" in payload:
        template_name = payload["pdf_template"]
        allowed_templates = (
            "corporate", "eco", "cyberpunk", "emerald", "amber",
            "serif_court", "cherry_blossom", "crimson", "indigo", "accessibility", "compact_terminal"
        )
        if template_name in allowed_templates:
            settings["pdf_template"] = template_name
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


from fastapi.responses import FileResponse

@app.post("/convert-txt-to-pdf")
async def convert_txt_to_pdf(payload: dict):
    text = payload.get("text", "").strip()
    pdf_template = payload.get("pdf_template", "compact_terminal")
    max_chars = int(payload.get("max_chars", 1000))

    if not text:
        raise HTTPException(status_code=400, detail="Text content cannot be empty")

    import re
    from export_service import export_pdf

    segments = []
    lines = text.splitlines()
    current_speaker = "話者1"
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Ignore markdown-like horizontal dividers or common table headers
        if line_clean.startswith("---") or line_clean.startswith("==="):
            continue
        if re.search(r"^(時間|話者|文字起こし|Time|Speaker|Transcript)\s*(?:\||$)", line_clean, re.IGNORECASE):
            continue
            
        # Try parsing pipe format: Time | Speaker | Text
        if "|" in line_clean:
            parts = line_clean.split("|", 2)
            time_str = parts[0].strip()
            speaker_str = parts[1].strip() if len(parts) > 1 else current_speaker
            text_str = parts[2].strip() if len(parts) > 2 else ""
            
            # Parse timestamp to seconds (can handle HH:MM:SS or MM:SS)
            seconds = 0.0
            time_parts = time_str.split(":")
            try:
                if len(time_parts) == 3:
                    seconds = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(time_parts[2])
                elif len(time_parts) == 2:
                    seconds = float(time_parts[0]) * 60 + float(time_parts[1])
                else:
                    seconds = float(time_str)
            except:
                seconds = 0.0
                
            if speaker_str:
                current_speaker = speaker_str
                
            segments.append({
                "start": seconds,
                "end": seconds + 3.0,
                "speaker": speaker_str or current_speaker,
                "text": text_str
            })
        else:
            # Fallback split by tab or double space
            parts = re.split(r"\t| {2,}", line_clean, 2)
            if len(parts) >= 2:
                time_str = parts[0].strip()
                # If first part looks like a timestamp or number
                if re.match(r"^(\d{1,2}:)?\d{1,2}:\d{1,2}$", time_str):
                    text_str = parts[-1].strip()
                    speaker_str = parts[1].strip() if len(parts) > 2 else current_speaker
                    
                    seconds = 0.0
                    time_parts = time_str.split(":")
                    try:
                        if len(time_parts) == 3:
                            seconds = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(time_parts[2])
                        elif len(time_parts) == 2:
                            seconds = float(time_parts[0]) * 60 + float(time_parts[1])
                    except:
                        pass
                        
                    if speaker_str:
                        current_speaker = speaker_str
                        
                    segments.append({
                        "start": seconds,
                        "end": seconds + 3.0,
                        "speaker": speaker_str,
                        "text": text_str
                    })
                    continue
            
            # Absolute fallback: entire line is text
            segments.append({
                "start": 0.0,
                "end": 3.0,
                "speaker": current_speaker,
                "text": line_clean
            })

    if not segments:
        raise HTTPException(status_code=400, detail="Could not parse any valid lines from the text content")

    # Generate ReportLab PDF inside a temporary file
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="tscr_conv_"))
    try:
        out_pdf_path = temp_dir / "converted_transcript.pdf"
        export_pdf(
            segments=segments,
            export_path=out_pdf_path,
            max_chars_per_page=max_chars,
            pdf_template=pdf_template
        )
        if not out_pdf_path.exists():
            raise HTTPException(status_code=500, detail="PDF generation failed")
            
        # Return the generated PDF file, and schedule directory cleanup after request
        return FileResponse(
            path=str(out_pdf_path),
            media_type="application/pdf",
            filename="converted_transcript.pdf"
        )
    except Exception as e:
        logger.error(f"Error in convert_txt_to_pdf: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
