"""
transcription_service.py  –  V2 (Refactored)
Handles the orchestration of the transcription pipeline:
  1. FFmpeg preprocess (mono 16 kHz WAV)
  2. Chunk splitting (hardware-aware)
  3. Dispatch chunks to active modular engine (faster-whisper, Qwen, or whisper.cpp)
  4. Perform speaker diarization (pyannote or sherpa-onnx)
  5. Merge chunks + assign speaker labels
  6. Return final list of {start, end, speaker, text} dicts
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Import cancellation, pause, and shared state from base engines module
from engines.base import (
    cancel_job,
    is_cancelled,
    clear_cancel,
    pause_job,
    resume_job,
    is_paused,
    check_pause_cancel,
    _progress,
)

# Import engine loaders and availability status
from engines import (
    ENGINE_STATUS,
    WhisperEngine,
    WhisperCppEngine,
    QwenEngine,
    PyannoteDiarizationEngine,
    SherpaDiarizationEngine,
    SenseVoiceEngine,
)


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

        # ── Hybrid Engine Setup ─────────────────────────────
        import platform
        bin_dir = Path(__file__).parent.parent.parent / "app" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        
        binary_name = "whisper-cli.exe" if platform.system() == "Windows" else "whisper-cli"
        self.whisper_cpp_path = bin_dir / binary_name
        
        recommended_engine = hw.get("engine", "faster-whisper")
        
        if recommended_engine == "whisper.cpp":
            if self.whisper_cpp_path.exists():
                self.engine = "whisper.cpp"
                logger.info(f"Hybrid Engine: Found whisper.cpp binary at {self.whisper_cpp_path}. Utilizing Vulkan/CoreML GPU path.")
            else:
                self.engine = "faster-whisper"
                self.device = "cpu"
                self.compute_type = "int8"
                hw["engine"] = self.engine
                hw["device"] = self.device
                hw["compute_type"] = self.compute_type
                logger.warning(
                    f"Hybrid Engine: Recommended engine is whisper.cpp (for AMD/Intel GPU or Apple Silicon), "
                    f"but no binary was found at {self.whisper_cpp_path}."
                )
                logger.warning("To enable AMD Radeon GPU (Vulkan) or macOS (Metal) acceleration:")
                logger.warning(f"  1. Download a precompiled 'whisper-cli' executable for your system.")
                logger.warning(f"  2. Place it exactly at: {self.whisper_cpp_path}")
                logger.warning("Gracefully falling back to CPU execution (faster-whisper INT8)...")
        else:
            self.engine = "faster-whisper"

        hw["runtime_asr_engine"] = self.engine
        hw["runtime_asr_device"] = self.device
        hw["runtime_compute_type"] = self.compute_type
        hw["runtime_whisper_cpp_available"] = self.whisper_cpp_path.exists()
        hw["runtime_whisper_cpp_path"] = str(self.whisper_cpp_path)

        # Instantiate modular engines
        self.whisper_engine = WhisperEngine(hw) if WhisperEngine else None
        self.whisper_cpp_engine = WhisperCppEngine(hw, self.whisper_cpp_path, self.threads) if WhisperCppEngine else None
        self.qwen_engine = QwenEngine(hw) if QwenEngine else None
        self.pyannote_engine = PyannoteDiarizationEngine(hw) if PyannoteDiarizationEngine else None
        self.sherpa_engine = SherpaDiarizationEngine(hw) if SherpaDiarizationEngine else None
        self.sensevoice_engine = SenseVoiceEngine(hw) if SenseVoiceEngine else None

    def _ensure_engine(self, engine_name: str, instance):
        """Raise a descriptive error if the requested engine failed to import at startup."""
        if instance is None:
            err = ENGINE_STATUS.get(engine_name, {}).get("error") or "Import error or dependency missing."
            raise RuntimeError(
                f"The '{engine_name}' engine is currently unavailable because of a loading/dependency error:\n"
                f"{err}\n"
                f"Please ensure all required dependencies are installed correctly."
            )
        return instance

    def _normalize_model_name_for_engine(self, model_name: Optional[str]) -> Optional[str]:
        """Normalize requested model names for the active backend engine."""
        if not model_name:
            return model_name

        normalized = str(model_name).lower()

        if self.engine == "whisper.cpp":
            forced = None
            if normalized.endswith("-q5_0"):
                forced = normalized
            elif normalized in ("small", "base"):
                forced = "small-q5_0"
            elif normalized == "medium":
                forced = "medium-q5_0"
            elif "large" in normalized or "1.7b" in normalized:
                forced = "medium-q5_0" if self.hw.get("ram_gb", 0.0) >= 16.0 else "small-q5_0"
            else:
                forced = "medium-q5_0" if self.hw.get("ram_gb", 0.0) >= 16.0 else "small-q5_0"

            if forced != normalized:
                logger.warning(
                    f"Whisper.cpp runtime requires a GGML q5_0 model; mapping '{model_name}' to '{forced}'."
                )
            return forced

        if self.engine == "faster-whisper" and normalized.endswith("-q5_0"):
            return normalized[:-5]

        if self.engine == "faster-whisper" and self.device == "cpu" and ("large" in normalized or "1.7b" in normalized):
            fallback = "medium" if self.hw.get("ram_gb", 0.0) >= 16.0 else "small"
            if fallback != normalized:
                logger.warning(
                    f"CPU execution is not optimal for '{model_name}'; falling back to '{fallback}' for speed and memory.")
            return fallback

        return model_name

    # ── FFmpeg helpers ───────────────────────────────────────

    @staticmethod
    def _find_ffmpeg() -> str:
        """
        Locate the ffmpeg binary. Checks:
          1. PATH (shutil.which)
          2. Common Windows install locations (winget / choco / manual)
        Returns the full path or raises FileNotFoundError.
        """
        import shutil, os

        found = shutil.which("ffmpeg")
        if found:
            return found

        userprofile = os.environ.get("USERPROFILE", "C:\\Users\\AHMED")
        localappdata = os.environ.get("LOCALAPPDATA", os.path.join(userprofile, "AppData", "Local"))

        candidates = [
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
                bin_dir = os.path.dirname(path)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return path

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
        return "ffprobe"

    @staticmethod
    def _ffmpeg_preprocess(input_path: str, output_path: str, performance_mode: str = "auto"):
        """Convert any audio/video to mono 16kHz WAV with noise reduction & amplitude normalization based on performance mode."""
        ffmpeg = TranscriptionService._find_ffmpeg()
        
        # Optimize audio filter chain based on performance mode to speed up preprocessing
        if performance_mode in ("eco", "fast"):
            filter_chain = []
        elif performance_mode == "balanced":
            filter_chain = ["dynaudnorm=f=75:g=15"]
        else:
            filter_chain = ["afftdn", "loudnorm"]
            
        cmd = [
            ffmpeg, "-y",
            "-threads", "0",
            "-i", input_path,
            "-vn",
        ]
        
        if filter_chain:
            cmd.extend(["-af", ",".join(filter_chain)])
            
        cmd.extend([
            "-ac", "1",
            "-ar", "16000",
            "-acodec", "pcm_s16le",
            "-loglevel", "error",
            output_path,
        ])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg preprocessing failed:\n{result.stderr[-2000:]}")

    @staticmethod
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
            return 0.0

    @staticmethod
    def _split_chunks(wav_path: str, chunk_seconds: int, chunks_dir: Path) -> List[Tuple[str, float]]:
        """Split WAV into timed chunks using ffmpeg segment muxer."""
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
        diarization_mode: str = "accurate",
        performance_mode: str = "auto",
        speaker_range: str = "normal",
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
            self._ffmpeg_preprocess(file_path, wav_path, performance_mode)
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
            if active_chunk_secs <= 0:
                if duration > 180:
                    active_chunk_secs = 30 if self.device == "cpu" else 60
                elif duration > 90:
                    active_chunk_secs = 30
                else:
                    active_chunk_secs = int(duration)
                logger.info(f"Auto chunking for duration {duration:.1f}s: using {active_chunk_secs}s chunks")

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

            check_pause_cancel(job_id, release_lock=True)
            
            # ── Step 2.5: Select and Load target Engine ────
            from hardware_detector import select_best_engine
            best_cfg = select_best_engine(self.hw)
            
            base_model = model_name if model_name and model_name != "auto" else best_cfg["model"]
            base_model = self._normalize_model_name_for_engine(base_model)
            
            # Apply performance profile settings
            if "sensevoice" in base_model.lower():
                active_model = "sensevoice"
                beam_size = 1
            elif performance_mode == "eco":
                active_model = "small" if "qwen" not in base_model.lower() else "qwen3-asr-0.6b"
                beam_size = 1
            elif performance_mode == "fast":
                if "qwen" in base_model.lower():
                    active_model = "qwen3-asr-0.6b"
                elif self.engine == "whisper.cpp":
                    active_model = "small-q5_0"
                elif self.device == "cpu":
                    active_model = "base" if self.hw["ram_gb"] >= 16 else "small"
                else:
                    active_model = "medium"
                beam_size = 1
            elif performance_mode == "balanced":
                is_best_whisper_cpp = self.engine == "whisper.cpp"
                active_model = "medium-q5_0" if is_best_whisper_cpp else "medium"
                if "qwen" in base_model.lower():
                    active_model = "qwen3-asr-0.6b"
                beam_size = 1
            elif performance_mode == "accurate":
                active_model = "large-v3" if "qwen" not in base_model.lower() else "qwen3-asr-1.7b"
                beam_size = 3
            else:  # "auto"
                active_model = base_model
                if active_model == best_cfg["model"]:
                    beam_size = best_cfg["beam_size"]
                else:
                    is_large = "large" in active_model.lower() or "1.7b" in active_model.lower()
                    beam_size = 3 if is_large else 1

            active_model = self._normalize_model_name_for_engine(active_model)
            is_sensevoice = active_model and "sensevoice" in active_model.lower()
            is_qwen3 = active_model and "qwen3" in active_model.lower() and not is_sensevoice
            is_whisper_cpp = self.engine == "whisper.cpp" and not is_qwen3 and not is_sensevoice

            if is_sensevoice:
                _progress(progress_cb, 8, "モデル読み込み中... / Loading AI model...")
                engine = self._ensure_engine("sensevoice", self.sensevoice_engine)
                engine.load(active_model, progress_cb)
            elif is_qwen3:
                _progress(progress_cb, 8, "モデル読み込み中... / Loading AI model...")
                engine = self._ensure_engine("qwen", self.qwen_engine)
                engine.load(active_model)
            elif is_whisper_cpp:
                if not active_model.endswith("-q5_0") and not active_model.startswith("qwen3"):
                    ggml_model = f"{active_model}-q5_0"
                else:
                    ggml_model = active_model
                _progress(progress_cb, 8, "モデル確認中... / Checking AI model...")
                engine = self._ensure_engine("whisper_cpp", self.whisper_cpp_engine)
                model_path = engine.download_ggml_model(ggml_model, progress_cb)
            else:
                _progress(progress_cb, 8, "モデル読み込み中... / Loading AI model...")
                engine = self._ensure_engine("whisper", self.whisper_engine)
                engine.load(active_model)

            check_pause_cancel(job_id, release_lock=True)
            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 3: Transcribe each chunk ──────────────
            import concurrent.futures
            
            if is_qwen3 or is_sensevoice or self.device == "cpu":
                max_workers = 1
            else:
                max_workers = min(2, n_chunks)

            logger.info(f"Starting chunk transcription with max_workers={max_workers}")
            results = [None] * n_chunks
            
            def run_one_chunk(idx):
                chunk_path, offset = chunks[idx]
                if is_cancelled(job_id):
                    raise InterruptedError("Job cancelled")
                
                if is_sensevoice:
                    segs = self.sensevoice_engine.transcribe_chunk(
                        chunk_path=chunk_path,
                        language=language,
                        offset=offset,
                        total_duration=duration,
                        progress_cb=None,
                        chunk_idx=idx,
                        n_chunks=n_chunks,
                        job_id=job_id,
                        on_language_detected=on_language_detected if idx == 0 else None,
                    )
                elif is_qwen3:
                    segs = self.qwen_engine.transcribe_chunk(
                        chunk_path=chunk_path,
                        offset=offset,
                        total_duration=duration,
                        progress_cb=None,
                        chunk_idx=idx,
                        n_chunks=n_chunks,
                        job_id=job_id,
                        on_language_detected=on_language_detected if idx == 0 else None,
                    )
                elif is_whisper_cpp:
                    segs = self.whisper_cpp_engine.transcribe_chunk(
                        chunk_path=chunk_path,
                        model_path=model_path,
                        language=language,
                        offset=offset,
                        total_duration=duration,
                        progress_cb=None,
                        chunk_idx=idx,
                        n_chunks=n_chunks,
                        job_id=job_id,
                        on_language_detected=on_language_detected if idx == 0 else None,
                    )
                else:
                    segs = self.whisper_engine.transcribe_chunk(
                        chunk_path=chunk_path,
                        language=language,
                        offset=offset,
                        total_duration=duration,
                        progress_cb=None,
                        chunk_idx=idx,
                        n_chunks=n_chunks,
                        job_id=job_id,
                        on_language_detected=on_language_detected if idx == 0 else None,
                        beam_size=beam_size,
                    )
                return idx, segs

            # Execute thread pool
            if max_workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    next_chunk_idx = 0
                    
                    # Submit initial batch
                    for _ in range(min(max_workers, n_chunks)):
                        futures[executor.submit(run_one_chunk, next_chunk_idx)] = next_chunk_idx
                        next_chunk_idx += 1
                        
                    while futures:
                        check_pause_cancel(job_id, release_lock=True)
                        if is_cancelled(job_id):
                            raise InterruptedError("Job cancelled")
                            
                        # Wait for at least one chunk to finish
                        done, _ = concurrent.futures.wait(
                            futures.keys(),
                            return_when=concurrent.futures.FIRST_COMPLETED
                        )
                        
                        for fut in done:
                            idx = futures.pop(fut)
                            try:
                                _, segs = fut.result()
                                results[idx] = segs
                                completed = sum(1 for r in results if r is not None)
                                prog_pct = 10 + int(70 * (completed / n_chunks))
                                _progress(
                                    progress_cb, prog_pct,
                                    f"文字起こし中 {completed}/{n_chunks}... / Transcribing chunk {completed}/{n_chunks}..."
                                )
                            except Exception as e:
                                logger.error(f"Error transcribing chunk: {e}")
                                raise e
                                
                        # Submit next chunks if not paused
                        while len(futures) < max_workers and next_chunk_idx < n_chunks:
                            if is_paused(job_id):
                                break
                            futures[executor.submit(run_one_chunk, next_chunk_idx)] = next_chunk_idx
                            next_chunk_idx += 1
            else:
                for idx in range(n_chunks):
                    check_pause_cancel(job_id, release_lock=True)
                    if is_cancelled(job_id):
                        raise InterruptedError("Job cancelled")
                    
                    initial_chunk_pct = 10 + int(70 * (chunks[idx][1] / duration)) if duration > 0 else (10 + int(70 * idx / n_chunks))
                    _progress(
                        progress_cb, initial_chunk_pct,
                        f"文字起こし中 {idx+1}/{n_chunks}... / Transcribing chunk {idx+1}/{n_chunks}..."
                    )
                    _, segs = run_one_chunk(idx)
                    results[idx] = segs
                    logger.info(f"Chunk {idx+1}/{n_chunks}: {len(segs)} segments")

            all_segments: List[Dict] = []
            for segs in results:
                if segs:
                    all_segments.extend(segs)

            check_pause_cancel(job_id, release_lock=True)
            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 4: Speaker diarization ────────────────
            _progress(progress_cb, 82, "話者認識中... / Detecting speakers...")
            all_segments = self._diarize(
                wav_path,
                all_segments,
                num_speakers,
                diarization_mode,
                model_name=active_model,
                speaker_range=speaker_range,
                progress_cb=progress_cb
            )

            # ── Step 5: Done ───────────────────────────────
            _progress(progress_cb, 98, "後処理中... / Finalizing...")
            return all_segments

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _diarize(
        self,
        wav_path: str,
        segments: List[Dict],
        num_speakers: Optional[int] = None,
        diarization_mode: str = "accurate",
        model_name: Optional[str] = None,
        speaker_range: str = "normal",
        progress_cb: Optional[Callable] = None,
    ) -> List[Dict]:
        """Route to appropriate speaker diarization engine wrapper."""
        if diarization_mode == "off" or num_speakers == 1 or not segments:
            logger.info("Diarization disabled or bypassed.")
            for seg in segments:
                seg["speaker"] = "Speaker 1"
                seg.pop("words", None)
            return segments

        if diarization_mode == "sherpa-onnx":
            engine = self._ensure_engine("sherpa", self.sherpa_engine)
            try:
                return engine.diarize(wav_path, segments, num_speakers, progress_cb)
            except Exception as e:
                logger.warning(f"Sherpa-ONNX diarization failed: {e}. Falling back to Speaker 1.")
                for seg in segments:
                    seg["speaker"] = "Speaker 1"
                    seg.pop("words", None)
                return segments
        else:
            # Pyannote
            try:
                engine = self._ensure_engine("pyannote", self.pyannote_engine)
                engine.load(diarization_mode)
                return engine.diarize(wav_path, segments, num_speakers, diarization_mode, speaker_range)
            except Exception as e:
                logger.warning(f"Pyannote diarization failed: {e}. Attempting Sherpa-ONNX fallback.")
                try:
                    engine_sherpa = self._ensure_engine("sherpa", self.sherpa_engine)
                    return engine_sherpa.diarize(wav_path, segments, num_speakers, progress_cb)
                except Exception as sherpa_e:
                    logger.warning(f"Sherpa-ONNX fallback also failed: {sherpa_e}. Falling back to Speaker 1.")
                for seg in segments:
                    seg["speaker"] = "Speaker 1"
                    seg.pop("words", None)
                return segments
