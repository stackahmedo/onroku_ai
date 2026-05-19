"""
base.py - Base helper functions and state management for transcription engines.
"""

import logging
import time
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Cancellation and Pause support ─────────────────────────────────
_CANCELLED_JOBS: set = set()
_PAUSED_JOBS: set = set()


def cancel_job(job_id: str):
    _CANCELLED_JOBS.add(job_id)


def is_cancelled(job_id: str) -> bool:
    return job_id in _CANCELLED_JOBS


def clear_cancel(job_id: str):
    _CANCELLED_JOBS.discard(job_id)
    _PAUSED_JOBS.discard(job_id)


def pause_job(job_id: str):
    _PAUSED_JOBS.add(job_id)


def resume_job(job_id: str):
    _PAUSED_JOBS.discard(job_id)


def is_paused(job_id: str) -> bool:
    return job_id in _PAUSED_JOBS


def check_pause_cancel(job_id: str):
    """Block execution while job is paused; raise InterruptedError if cancelled."""
    if is_paused(job_id):
        logger.info(f"Job {job_id} paused. Waiting...")
    while is_paused(job_id):
        if is_cancelled(job_id):
            raise InterruptedError("Job cancelled while paused")
        time.sleep(0.5)
    if is_cancelled(job_id):
        raise InterruptedError("Job cancelled")


# ── Shared Helpers ──────────────────────────────────────────────────

def _progress(cb: Optional[Callable], pct: int, label: str):
    if cb:
        try:
            cb(pct, label)
        except Exception as e:
            logger.warning(f"Failed to call progress callback: {e}")


def _get_duration(wav_path: str) -> float:
    """Return duration in seconds by reading WAV header directly (zero subprocess cost)."""
    try:
        import wave
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / rate
    except Exception:
        pass
    try:
        import soundfile as sf
        info = sf.info(wav_path)
        return info.duration
    except Exception:
        pass
    return 0.0


def _assign_speaker(seg: Dict, speaker_segs: List[Dict]) -> str:
    """Return the speaker label with the most overlap with seg; falls back to nearest speaker."""
    seg_start, seg_end = seg["start"], seg["end"]
    best_speaker = "Speaker 1"
    best_overlap = 0.0

    for sp in speaker_segs:
        overlap = max(0.0, min(seg_end, sp["end"]) - max(seg_start, sp["start"]))
        if overlap > best_overlap:
            best_overlap = overlap
            raw = sp["speaker"]
            try:
                num = int(raw.split("_")[-1]) + 1
                best_speaker = f"Speaker {num}"
            except Exception:
                best_speaker = raw

    # Fallback to closest segment in time
    if best_overlap == 0.0 and speaker_segs:
        best_dist = float("inf")
        for sp in speaker_segs:
            if sp["end"] < seg_start:
                dist = seg_start - sp["end"]
            elif sp["start"] > seg_end:
                dist = sp["start"] - seg_end
            else:
                dist = 0.0

            if dist < best_dist:
                best_dist = dist
                raw = sp["speaker"]
                try:
                    num = int(raw.split("_")[-1]) + 1
                    best_speaker = f"Speaker {num}"
                except Exception:
                    best_speaker = raw

    return best_speaker
