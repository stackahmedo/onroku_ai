"""
transcription_service.py  –  V2
Handles the full pipeline:
  1. FFmpeg preprocess (mono 16 kHz WAV)
  2. Chunk splitting (hardware-aware)
  3. faster-whisper transcription per chunk (Japanese primary)
  4. WhisperX word-level alignment (optional, graceful fallback)
  5. Pyannote speaker diarization (optional, graceful fallback)
  6. Merge chunks + assign speaker labels
  7. Return final list of {start, end, speaker, text} dicts
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  Cancellation and Pause support
# ─────────────────────────────────────────────────────────────
import time

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
    """Block the pipeline execution while job is paused; raise InterruptedError if cancelled."""
    if is_paused(job_id):
        logger.info(f"Job {job_id} paused. Waiting...")
    while is_paused(job_id):
        if is_cancelled(job_id):
            raise InterruptedError("Job cancelled while paused")
        time.sleep(0.5)
    if is_cancelled(job_id):
        raise InterruptedError("Job cancelled")


# ─────────────────────────────────────────────────────────────


class TranscriptionService:
    def __init__(self, hw: Dict):
        """
        hw: result from hardware_detector.detect_hardware()
        """
        self.hw = hw
        self.model_name = hw["model_name"]
        self.device = hw["device"]
        self.compute_type = hw["compute_type"]
        self.chunk_seconds = hw["chunk_seconds"]
        self.threads = hw["threads"]

        # Lazy-loaded models (loaded once on first use)
        self._whisper_model = None
        self._current_whisper_model_name = None
        self._pyannote_pipeline = None

    # ── Whisper model ────────────────────────────────────────

    def _load_whisper(self, requested_model_name: Optional[str] = None):
        target_model = requested_model_name if requested_model_name else self.model_name
        if self._whisper_model is not None and self._current_whisper_model_name == target_model:
            return
        logger.info(
            f"Loading faster-whisper model: {target_model} "
            f"on {self.device} ({self.compute_type})"
        )
        from faster_whisper import WhisperModel
        # Cache models inside project models dir if available
        model_dir = Path(__file__).parent.parent.parent / "app" / "models" / "whisper"
        model_dir.mkdir(parents=True, exist_ok=True)

        # Optimize threading parameters to avoid CPU contention
        kwargs = {
            "device": self.device,
            "compute_type": self.compute_type,
            "download_root": str(model_dir),
        }
        if self.device == "cpu":
            # Fully utilize all logical CPU cores during inference
            kwargs["cpu_threads"] = self.hw["cpu_cores"]
            kwargs["num_workers"] = 1
        else:
            # Maximize CUDA pipeline occupancy with multiple parallel GPU workers
            kwargs["num_workers"] = 2

        self._whisper_model = WhisperModel(
            target_model,
            **kwargs
        )
        self._current_whisper_model_name = target_model
        logger.info("Whisper model loaded")

    # ── Pyannote pipeline ────────────────────────────────────

    def _load_pyannote(self):
        if self._pyannote_pipeline is not None:
            return True
        try:
            from pyannote.audio import Pipeline
            import torch

            model_cache = Path(__file__).parent.parent.parent / "app" / "models" / "pyannote"
            model_cache.mkdir(parents=True, exist_ok=True)
            
            # Check multiple potential token file paths for maximum user convenience
            root_dir = Path(__file__).parent.parent.parent
            token_candidates = [
                root_dir / "app" / "models" / "hf_token.txt",
                root_dir / "models" / "hf_token.txt",
                root_dir / "hf_token.txt",
            ]
            
            hf_token = None
            for candidate in token_candidates:
                if candidate.exists():
                    try:
                        hf_token = candidate.read_text().strip()
                        if hf_token:
                            logger.info(f"Loaded Hugging Face token from: {candidate.name}")
                            break
                    except Exception as e:
                        logger.warning(f"Error reading token from {candidate}: {e}")

            logger.info("Loading Pyannote speaker diarization pipeline...")
            kwargs = {"token": hf_token} if hf_token else {}
            kwargs["cache_dir"] = str(model_cache)
            self._pyannote_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", **kwargs
            )
            device = torch.device(self.device if self.device == "cuda" else "cpu")
            if device.type == "cpu":
                # For maximum multi-core PyTorch CPU execution
                torch.set_num_threads(self.hw["cpu_cores"])
            self._pyannote_pipeline.to(device)
            logger.info("Pyannote pipeline loaded")
            return True
        except Exception as e:
            logger.warning(f"Pyannote unavailable: {e}. Speaker diarization disabled.")
            self._pyannote_pipeline = None
            return False

    # ── FFmpeg helpers ───────────────────────────────────────

    @staticmethod
    def _find_ffmpeg() -> str:
        """
        Locate the ffmpeg binary. Checks:
          1. PATH (shutil.which)
          2. Common Windows install locations (winget / choco / manual)
        Returns the full path or raises FileNotFoundError with helpful message.
        """
        import shutil, os

        # Check PATH first
        found = shutil.which("ffmpeg")
        if found:
            return found

        # Common Windows install paths (including WinGet user and system paths)
        userprofile = os.environ.get("USERPROFILE", "C:\\Users\\AHMED")
        localappdata = os.environ.get("LOCALAPPDATA", os.path.join(userprofile, "AppData", "Local"))

        candidates = [
            # WinGet Gyan.FFmpeg (user)
            os.path.join(localappdata, "Microsoft", "WinGet", "Packages",
                         "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
                         "ffmpeg-8.1.1-full_build", "bin", "ffmpeg.exe"),
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\tools\ffmpeg\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        ]

        for path in candidates:
            if os.path.isfile(path):
                # Add to PATH for this process so future calls (ffprobe etc.) also work
                bin_dir = os.path.dirname(path)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return path

        # Deep scan WinGet packages folder
        winget_base = os.path.join(localappdata, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_base):
            for root, dirs, files in os.walk(winget_base):
                if "ffmpeg.exe" in files:
                    path = os.path.join(root, "ffmpeg.exe")
                    bin_dir = os.path.dirname(path)
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                    return path

        raise FileNotFoundError(
            "ffmpeg not found. Please install it:\n"
            "  winget install --id Gyan.FFmpeg -e\n"
            "Then restart the application so the new PATH is picked up."
        )

    @staticmethod
    def _find_ffprobe() -> str:
        """Locate ffprobe alongside ffmpeg."""
        import shutil, os
        found = shutil.which("ffprobe")
        if found:
            return found
        ffmpeg = TranscriptionService._find_ffmpeg()
        ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe.exe")
        if os.path.isfile(ffprobe):
            return ffprobe
        return "ffprobe"  # fallback, may fail gracefully

    @staticmethod
    def _ffmpeg_preprocess(input_path: str, output_path: str):
        """Convert any audio/video to mono 16kHz WAV."""
        ffmpeg = TranscriptionService._find_ffmpeg()
        cmd = [
            ffmpeg, "-y", "-i", input_path,
            "-vn",            # skip video stream decoding for huge speedup on video uploads
            "-ac", "1",       # mono
            "-ar", "16000",   # 16 kHz
            "-acodec", "pcm_s16le",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg preprocessing failed:\n{result.stderr[-2000:]}")

    @staticmethod
    def _get_duration(wav_path: str) -> float:
        """Return duration in seconds via ffprobe."""
        try:
            ffprobe = TranscriptionService._find_ffprobe()
            cmd = [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            return float(out)
        except Exception:
            # Fallback: use soundfile
            try:
                import soundfile as sf
                info = sf.info(wav_path)
                return info.duration
            except Exception:
                return 0.0

    @staticmethod
    def _split_chunks(wav_path: str, chunk_seconds: int, chunks_dir: Path) -> List[Tuple[str, float]]:
        """
        Split WAV into timed chunks using ffmpeg segment muxer.
        Returns list of (chunk_path, offset_seconds).
        """
        chunks_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg = TranscriptionService._find_ffmpeg()
        pattern = str(chunks_dir / "chunk_%04d.wav")
        cmd = [
            ffmpeg, "-y", "-i", wav_path,
            "-f", "segment",
            "-segment_time", str(chunk_seconds),
            "-c", "copy",
            "-reset_timestamps", "1",
            pattern,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg chunk split failed:\n{result.stderr[-2000:]}")

        chunks = sorted(chunks_dir.glob("chunk_*.wav"))
        result_list = []
        for i, chunk_path in enumerate(chunks):
            # Mathematically compute the offset based on chunk index and size
            # This completely avoids running slow ffprobe subprocess calls for every chunk on Windows
            offset = i * chunk_seconds
            result_list.append((str(chunk_path), offset))
        return result_list

    # ── Core transcription ───────────────────────────────────

    def transcribe_file(
        self,
        file_path: str,
        job_id: str,
        language: str = "ja",
        model_name: Optional[str] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        on_duration_known: Optional[Callable[[float], None]] = None,
        num_speakers: Optional[int] = None,
        chunk_seconds: Optional[int] = None,
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """
        Full pipeline: preprocess → chunk → transcribe → diarize → merge.
        Returns list of segment dicts.
        """
        clear_cancel(job_id)

        tmp_dir = Path(tempfile.mkdtemp(prefix=f"tscr_{job_id}_"))
        try:
            # ── Step 1: Preprocess ─────────────────────────
            _progress(progress_cb, 2, "前処理中... / Preprocessing audio...")
            wav_path = str(tmp_dir / "audio.wav")
            self._ffmpeg_preprocess(file_path, wav_path)
            duration = self._get_duration(wav_path)
            logger.info(f"Preprocessed: {duration:.1f}s")

            if on_duration_known:
                try:
                    on_duration_known(duration)
                except Exception as e:
                    logger.warning(f"Failed to call on_duration_known: {e}")

            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 2: Split into chunks ──────────────────
            _progress(progress_cb, 5, "チャンク分割中... / Splitting chunks...")
            chunks_dir = tmp_dir / "chunks"
            
            active_chunk_secs = chunk_seconds if chunk_seconds is not None else self.chunk_seconds
            if active_chunk_secs <= 0 or active_chunk_secs >= duration:
                chunks = [(wav_path, 0.0)]
                n_chunks = 1
                logger.info("No chunking requested or file shorter than chunk size. Transcribing full file.")
            else:
                chunks = self._split_chunks(wav_path, active_chunk_secs, chunks_dir)
                n_chunks = len(chunks)
                logger.info(f"Split into {n_chunks} chunk(s) of {active_chunk_secs}s")

            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            check_pause_cancel(job_id)
            # ── Step 2.5: Load Whisper model ───────────────
            _progress(progress_cb, 8, "モデル読み込み中... / Loading AI model...")
            self._load_whisper(model_name)

            check_pause_cancel(job_id)
            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 3: Transcribe each chunk ──────────────
            all_segments: List[Dict] = []
            for i, (chunk_path, offset) in enumerate(chunks):
                check_pause_cancel(job_id)
                if is_cancelled(job_id):
                    raise InterruptedError("Job cancelled")

                # Emit initial chunk transcription progress
                initial_chunk_pct = 10 + int(70 * (offset / duration)) if duration > 0 else (10 + int(70 * i / n_chunks))
                _progress(
                    progress_cb, initial_chunk_pct,
                    f"文字起こし中 {i+1}/{n_chunks}... / Transcribing chunk {i+1}/{n_chunks}..."
                )

                segs = self._transcribe_chunk(
                    chunk_path=chunk_path,
                    language=language,
                    offset=offset,
                    total_duration=duration,
                    progress_cb=progress_cb,
                    chunk_idx=i,
                    n_chunks=n_chunks,
                    job_id=job_id,
                    on_language_detected=on_language_detected if i == 0 else None,
                )
                all_segments.extend(segs)
                logger.info(f"Chunk {i+1}/{n_chunks}: {len(segs)} segments")

            check_pause_cancel(job_id)
            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 4: Speaker diarization ────────────────
            _progress(progress_cb, 82, "話者認識中... / Detecting speakers...")
            all_segments = self._diarize(wav_path, all_segments, num_speakers)

            # ── Step 5: Done ───────────────────────────────
            _progress(progress_cb, 98, "後処理中... / Finalizing...")
            return all_segments

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _transcribe_chunk(
        self,
        chunk_path: str,
        language: str,
        offset: float,
        total_duration: float,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        chunk_idx: int = 0,
        n_chunks: int = 1,
        job_id: str = "",
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with faster-whisper."""
        # Optimize beam search decoding for CPU to speed up inference
        beam_size = 3 if self.device == "cpu" else 5

        # If language is 'auto', we pass None to let Whisper auto-detect
        active_lang = None if language == "auto" else language

        segments_out = []
        try:
            segments, info = self._whisper_model.transcribe(
                chunk_path,
                language=active_lang,
                beam_size=beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                word_timestamps=True,
            )
            logger.info(
                f"  Detected language: {info.language} "
                f"(prob={info.language_probability:.2f})"
            )
            if on_language_detected:
                try:
                    on_language_detected(info.language)
                except Exception as e:
                    logger.warning(f"Failed to call on_language_detected callback: {e}")
            for seg in segments:
                check_pause_cancel(job_id)
                words_list = []
                if seg.words:
                    for w in seg.words:
                        words_list.append({
                            "start": round(w.start + offset, 3),
                            "end":   round(w.end + offset, 3),
                            "text":  w.word,
                        })
                segments_out.append({
                    "start": round(seg.start + offset, 3),
                    "end":   round(seg.end   + offset, 3),
                    "speaker": "Speaker 1",
                    "text": seg.text.strip(),
                    "words": words_list,
                })
                if total_duration > 0 and progress_cb:
                    # Current progress is based on the end timestamp of the segment relative to the total audio duration
                    processed_secs = min(offset + seg.end, total_duration)
                    # We map the transcription phase to 10% - 80% range (70% total)
                    pct = 10 + int(70 * (processed_secs / total_duration))
                    # Prevent going over 80% during transcription
                    pct = min(pct, 79)
                    _progress(
                        progress_cb, pct,
                        f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
                    )
        except Exception as e:
            logger.error(f"Chunk transcription error: {e}")
        return segments_out

    # ── Speaker diarization ──────────────────────────────────

    def _diarize(self, wav_path: str, segments: List[Dict], num_speakers: Optional[int] = None) -> List[Dict]:
        """Run Pyannote and assign speaker labels to transcript segments, splitting segments by speaker change."""
        ok = self._load_pyannote()
        if not ok or not segments:
            return segments

        try:
            kwargs = {}
            if num_speakers is not None and num_speakers > 0:
                kwargs["num_speakers"] = num_speakers
            diarization_input = _load_audio_for_pyannote(wav_path)
            diarization = self._pyannote_pipeline(diarization_input, **kwargs)
            diarization_tracks = _get_diarization_annotation(diarization)
            speaker_segments = [
                {"start": turn.start, "end": turn.end, "speaker": spk}
                for turn, _, spk in diarization_tracks.itertracks(yield_label=True)
            ]
            logger.info(
                "Diarization produced %s speaker turn(s), %s unique speaker(s).",
                len(speaker_segments),
                len({sp["speaker"] for sp in speaker_segments}),
            )

            # Detect if text has English characters to determine join spacing
            first_text = segments[0]["text"] if segments else ""
            import re
            is_english = bool(re.search(r'[a-zA-Z]', first_text))
            join_char = " " if is_english else ""

            final_segments = []
            for seg in segments:
                words = seg.get("words", [])
                if not words:
                    # Fallback if word-timestamps are missing for this segment
                    seg["speaker"] = _assign_speaker(seg, speaker_segments)
                    seg.pop("words", None)
                    final_segments.append(seg)
                    continue

                # Map each word to its best speaker
                word_speaker_pairs = []
                for w in words:
                    spk = _assign_speaker(w, speaker_segments)
                    word_speaker_pairs.append((w, spk))

                # Group words into contiguous speaker blocks
                blocks = []
                current_block = []
                current_speaker = None

                for w, spk in word_speaker_pairs:
                    if current_speaker is None:
                        current_speaker = spk
                        current_block.append(w)
                    elif spk == current_speaker:
                        current_block.append(w)
                    else:
                        blocks.append((current_speaker, current_block))
                        current_speaker = spk
                        current_block = [w]
                if current_block:
                    blocks.append((current_speaker, current_block))

                # Create sub-segments from blocks
                for spk, block_words in blocks:
                    sub_text = join_char.join([w["text"] for w in block_words]).strip()
                    if not sub_text:
                        continue
                    final_segments.append({
                        "start": block_words[0]["start"],
                        "end":   block_words[-1]["end"],
                        "speaker": spk,
                        "text":  sub_text,
                    })

            logger.info(f"Diarization complete. Aligned and split into {len(final_segments)} segments.")
            return final_segments

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            for seg in segments:
                seg.pop("words", None)
            return segments


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _progress(cb: Optional[Callable], pct: int, label: str):
    if cb:
        try:
            cb(pct, label)
        except Exception as e:
            logger.warning(f"Failed to call progress callback: {e}")


def _load_audio_for_pyannote(wav_path: str) -> Dict:
    """
    Load audio in-memory for pyannote.

    pyannote.audio 4.x defaults to torchcodec for path-based decoding. On some
    Windows installs torchcodec is present but cannot load its FFmpeg DLLs.
    Recent torchaudio builds can use the same decoder, so this intentionally
    uses stdlib wave + numpy for the PCM WAV produced by ffmpeg preprocessing.
    """
    import wave
    import numpy as np
    import torch

    with wave.open(wav_path, "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sample_width == 1:
        audio = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width for diarization: {sample_width} bytes")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    waveform = torch.from_numpy(audio).unsqueeze(0)

    return {
        "waveform": waveform.to(dtype=torch.float32).contiguous(),
        "sample_rate": sample_rate,
    }


def _get_diarization_annotation(diarization):
    """Return a pyannote Annotation from both pyannote 3.x and 4.x outputs."""
    if hasattr(diarization, "itertracks"):
        return diarization
    if hasattr(diarization, "exclusive_speaker_diarization"):
        return diarization.exclusive_speaker_diarization
    if hasattr(diarization, "speaker_diarization"):
        return diarization.speaker_diarization
    raise TypeError(f"Unsupported diarization output type: {type(diarization)!r}")


def _assign_speaker(seg: Dict, speaker_segs: List[Dict]) -> str:
    """Return the speaker label with the most overlap with seg; falls back to the nearest speaker in time."""
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

    # If there is absolutely no overlapping speech turn detected (e.g. during very brief silence or low volume),
    # assign the segment to the closest active speaker segment in time.
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
