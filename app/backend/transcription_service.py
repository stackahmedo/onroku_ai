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

        # Lazy-loaded models (loaded once on first use)
        self._whisper_model = None
        self._current_whisper_model_name = None
        self._pyannote_pipeline = None
        self._qwen3_model = None
        self._current_qwen3_model_name = None

    def _normalize_model_name_for_engine(self, model_name: Optional[str]) -> Optional[str]:
        """Map whisper.cpp-only quantized names back to faster-whisper model ids when needed."""
        if not model_name or self.engine == "whisper.cpp":
            return model_name
        if isinstance(model_name, str) and model_name.endswith("-q5_0"):
            return model_name[:-5]
        return model_name

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
            kwargs["cpu_threads"] = max(2, min(4, self.hw.get("cpu_cores", 4)))
            kwargs["num_workers"] = 1
        else:
            kwargs["num_workers"] = 1

        self._whisper_model = WhisperModel(
            target_model,
            **kwargs
        )
        self._current_whisper_model_name = target_model
        logger.info("Whisper model loaded")

    def _load_qwen3_asr(self, model_name: str):
        """Lazy-load the Qwen3-ASR model on CPU or CUDA GPU."""
        if self._qwen3_model is not None and self._current_qwen3_model_name == model_name:
            return
            
        import torch
        try:
            from qwen_asr import Qwen3ASRModel
        except ImportError as e:
            logger.error(f"qwen-asr library not installed: {e}. Please run pip install qwen-asr.")
            raise RuntimeError("qwen-asr library is required to run Qwen3-ASR models.")
            
        model_dir = Path(__file__).parent.parent.parent / "app" / "models" / "qwen3-asr"
        if "0.6b" in model_name.lower():
            local_model_path = model_dir / "Qwen3-ASR-0.6B"
            repo_id = "Qwen/Qwen3-ASR-0.6B"
        else:
            local_model_path = model_dir / "Qwen3-ASR-1.7B"
            repo_id = "Qwen/Qwen3-ASR-1.7B"
            
        model_path_to_load = str(local_model_path) if local_model_path.exists() and any(local_model_path.iterdir()) else repo_id
        
        # Optimize dtype and device mapping
        if self.device == "cuda":
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            device_map = self.device
        else:
            dtype = torch.float32
            device_map = "cpu"
            torch.set_num_threads(max(2, min(4, self.hw.get("cpu_cores", 4))))
            
        logger.info(f"Loading Qwen3-ASR model: {model_name} from {model_path_to_load} on {device_map} with dtype {dtype}...")
        
        try:
            self._qwen3_model = Qwen3ASRModel.from_pretrained(
                model_path_to_load,
                dtype=dtype,
                device_map=device_map
            )
            self._current_qwen3_model_name = model_name
            logger.info("Qwen3-ASR model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Qwen3-ASR model: {e}", exc_info=True)
            raise e

    def _download_ggml_model(self, model_name: str, progress_cb: Optional[Callable] = None) -> str:
        """Download GGML model from Hugging Face if not present."""
        ggml_dir = Path(__file__).parent.parent.parent / "app" / "models" / "ggml"
        ggml_dir.mkdir(parents=True, exist_ok=True)
        
        # Map target model name to GGML filename
        # e.g. "large-v3" -> "ggml-large-v3.bin", "small" -> "ggml-small.bin"
        model_filename = f"ggml-{model_name}.bin"
        model_path = ggml_dir / model_filename
        
        if model_path.exists():
            logger.info(f"GGML model already exists: {model_path}")
            return str(model_path)
            
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_filename}"
        logger.info(f"Downloading GGML model from {url} to {model_path}...")
        
        import requests
        
        _progress(progress_cb, 8, f"AIモデル({model_name})ダウンロード中... / Downloading AI model ({model_name})...")
        
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download GGML model: HTTP {response.status_code}")
            
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        
        with open(model_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_cb:
                        pct = 8 + int(15 * (downloaded / total_size)) # Use 8% - 23% for download progress
                        _progress(progress_cb, pct, f"AIモデル({model_name})ダウンロード中 ({downloaded//(1024*1024)}MB / {total_size//(1024*1024)}MB)...")
                        
        logger.info(f"GGML model successfully downloaded: {model_path}")
        return str(model_path)

    def _transcribe_chunk_whisper_cpp(
        self,
        chunk_path: str,
        model_path: str,
        language: str,
        offset: float,
        total_duration: float,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        chunk_idx: int = 0,
        n_chunks: int = 1,
        job_id: str = "",
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with whisper.cpp executable."""
        import tempfile
        import json
        import subprocess
        
        # If language is 'auto', we pass 'auto' to let Whisper auto-detect
        active_lang = "auto" if language == "auto" else language
        
        segments_out = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                json_prefix = Path(tmpdir) / "output"
                
                cmd = [
                    str(self.whisper_cpp_path),
                    "-m", model_path,
                    "-f", chunk_path,
                    "-oj",
                    "-of", str(json_prefix),
                    "-t", str(self.threads),
                    "-sow",  # Split on word for precise word-timestamps
                ]
                if active_lang and active_lang != "auto":
                    cmd.extend(["-l", active_lang])
                else:
                    cmd.extend(["-l", "auto"])
                
                logger.info(f"Running whisper.cpp command: {' '.join(cmd)}")
                
                # Execute whisper.cpp
                # We hide the window on Windows using creationflags
                kwargs = {}
                if os.name == "nt":
                    kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
                
                # We capture standard error to log it in case of failure
                result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
                
                if result.returncode != 0:
                    logger.error(f"whisper.cpp process failed with code {result.returncode}:\n{result.stderr}")
                    return []
                
                json_file = Path(tmpdir) / "output.json"
                if not json_file.exists():
                    logger.error(f"whisper.cpp JSON output file not found at {json_file}")
                    return []
                
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Parse output segments
                transcription = data.get("transcription", [])
                
                # If this is the first chunk and language callback is provided, extract detected language
                if on_language_detected:
                    detected_lang = data.get("result", {}).get("language", "ja")
                    try:
                        on_language_detected(detected_lang)
                    except Exception as e:
                        logger.warning(f"Failed to call on_language_detected: {e}")
                
                for seg in transcription:
                    check_pause_cancel(job_id)
                    
                    # Convert offsets (milliseconds) to seconds (float)
                    seg_start = round(float(seg["offsets"]["from"]) / 1000.0 + offset, 3)
                    seg_end = round(float(seg["offsets"]["to"]) / 1000.0 + offset, 3)
                    seg_text = seg["text"].strip()
                    
                    words_list = []
                    for w in seg.get("tokens", []):
                        # Skip special tokens or empty text tokens
                        w_text = w.get("text", "").strip()
                        if not w_text or w_text.startswith("[") or w_text.startswith("("):
                            continue
                        w_start = round(float(w["offsets"]["from"]) / 1000.0 + offset, 3)
                        w_end = round(float(w["offsets"]["to"]) / 1000.0 + offset, 3)
                        words_list.append({
                            "start": w_start,
                            "end": w_end,
                            "text": w_text,
                        })
                    
                    segments_out.append({
                        "start": seg_start,
                        "end": seg_end,
                        "speaker": "Speaker 1",
                        "text": seg_text,
                        "words": words_list,
                    })
                    
                    if total_duration > 0 and progress_cb:
                        processed_secs = min(offset + (float(seg["offsets"]["to"]) / 1000.0), total_duration)
                        pct = 10 + int(70 * (processed_secs / total_duration))
                        pct = min(pct, 79)
                        _progress(
                            progress_cb, pct,
                            f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
                        )
                        
        except Exception as e:
            logger.error(f"whisper.cpp chunk transcription error: {e}")
            
        return segments_out

    # ── Pyannote pipeline ────────────────────────────────────

    def _load_pyannote(self, diarization_mode: str = "accurate"):
        if self._pyannote_pipeline is not None:
            # Dynamically update embedding batch size in case mode changed
            try:
                import torch
                device = torch.device(self.device if self.device == "cuda" else "cpu")
                if device.type != "cuda":
                    self._pyannote_pipeline.embedding_batch_size = 4 if diarization_mode == "fast" else 1
                    logger.info(f"Dynamically updated Pyannote embedding_batch_size = {self._pyannote_pipeline.embedding_batch_size}")
            except Exception as e:
                logger.warning(f"Could not update Pyannote embedding_batch_size: {e}")
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
                torch.set_num_threads(max(2, min(4, self.hw.get("cpu_cores", 4))))
            
            self._pyannote_pipeline.to(device)

            # Optimize embedding batch size for maximum processing speed
            try:
                if device.type == "cuda":
                    self._pyannote_pipeline.embedding_batch_size = 16
                else:
                    self._pyannote_pipeline.embedding_batch_size = 4 if diarization_mode == "fast" else 1
                logger.info(f"Configured Pyannote embedding_batch_size = {self._pyannote_pipeline.embedding_batch_size}")
            except Exception as e:
                logger.warning(f"Could not set Pyannote embedding_batch_size: {e}")

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
        """Convert any audio/video to mono 16kHz WAV with noise reduction & amplitude normalization."""
        ffmpeg = TranscriptionService._find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-threads", "0",  # Use all CPU cores for decoding (2-3x faster)
            "-i", input_path,
            "-vn",            # skip video stream decoding for huge speedup on video uploads
            "-af", "afftdn,loudnorm", # FFT noise reduction + EBU R128 loudness normalization
            "-ac", "1",       # mono
            "-ar", "16000",   # 16 kHz
            "-acodec", "pcm_s16le",
            "-loglevel", "error",  # suppress verbose logging overhead
            output_path,
        ]
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
        # Fallback: use soundfile
        try:
            import soundfile as sf
            info = sf.info(wav_path)
            return info.duration
        except Exception:
            pass
        # Last resort: ffprobe subprocess
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
            # ── Step 2.5: Load / Downloader Whisper or Qwen model ────────
            from hardware_detector import select_best_engine
            best_cfg = select_best_engine(self.hw)
            
            # Start with specified model name or fallback to hardware default
            base_model = model_name if model_name and model_name != "auto" else best_cfg["model"]
            base_model = self._normalize_model_name_for_engine(base_model)
            
            # Apply performance profile settings
            if performance_mode == "eco":
                active_model = "small" if "qwen" not in base_model.lower() else "qwen3-asr-0.6b"
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
            else: # "auto" / Recommended
                active_model = base_model
                if active_model == best_cfg["model"]:
                    beam_size = best_cfg["beam_size"]
                else:
                    is_large = "large" in active_model.lower() or "1.7b" in active_model.lower()
                    beam_size = 3 if is_large else 1

            active_model = self._normalize_model_name_for_engine(active_model)
            is_qwen3 = active_model and "qwen3" in active_model.lower()
            is_whisper_cpp = self.engine == "whisper.cpp" and not is_qwen3

            if is_qwen3:
                _progress(progress_cb, 8, "モデル読み込み中... / Loading AI model...")
                self._load_qwen3_asr(active_model)
            elif is_whisper_cpp:
                # If target model doesn't end in q5_0 and is not a Qwen model, use quantized GGML counterpart
                if not active_model.endswith("-q5_0") and not active_model.startswith("qwen3"):
                    ggml_model = f"{active_model}-q5_0"
                else:
                    ggml_model = active_model
                _progress(progress_cb, 8, "モデル確認中... / Checking AI model...")
                model_path = self._download_ggml_model(ggml_model, progress_cb)
            else:
                _progress(progress_cb, 8, "モデル読み込み中... / Loading AI model...")
                self._load_whisper(active_model)

            check_pause_cancel(job_id)
            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 3: Transcribe each chunk ──────────────
            import concurrent.futures
            
            # Determine concurrency max_workers
            if is_qwen3 or self.device != "cpu":
                # Qwen3 models or GPU execution are single-threaded to prevent VRAM OOM or overloading
                max_workers = 1
            else:
                # CPU transcription (faster-whisper/whisper.cpp) scales with multi-core concurrent chunk processing
                max_workers = min(3, n_chunks)

            logger.info(f"Starting chunk transcription with max_workers={max_workers}")
            
            results = [None] * n_chunks
            
            def run_one_chunk(idx):
                chunk_path, offset = chunks[idx]
                check_pause_cancel(job_id)
                if is_cancelled(job_id):
                    raise InterruptedError("Job cancelled")
                
                if is_qwen3:
                    segs = self._transcribe_chunk_qwen3_asr(
                        chunk_path=chunk_path,
                        offset=offset,
                        total_duration=duration,
                        progress_cb=None, # Disable internal progress callbacks inside concurrent threads to avoid UI flashing
                        chunk_idx=idx,
                        n_chunks=n_chunks,
                        job_id=job_id,
                        on_language_detected=on_language_detected if idx == 0 else None,
                    )
                elif is_whisper_cpp:
                    segs = self._transcribe_chunk_whisper_cpp(
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
                    segs = self._transcribe_chunk(
                        chunk_path=chunk_path,
                        language=language,
                        offset=offset,
                        total_duration=duration,
                        progress_cb=None,
                        chunk_idx=idx,
                        n_chunks=n_chunks,
                        job_id=job_id,
                        on_language_detected=on_language_detected if idx == 0 else None,
                        diarization_mode=diarization_mode,
                        model_name=active_model,
                        beam_size=beam_size,
                    )
                return idx, segs

            # Execute thread pool
            if max_workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(run_one_chunk, idx): idx for idx in range(n_chunks)}
                    for fut in concurrent.futures.as_completed(futures):
                        check_pause_cancel(job_id)
                        if is_cancelled(job_id):
                            raise InterruptedError("Job cancelled")
                        try:
                            idx, segs = fut.result()
                            results[idx] = segs
                            # Emit clean grouped progress updates
                            completed = sum(1 for r in results if r is not None)
                            prog_pct = 10 + int(70 * (completed / n_chunks))
                            _progress(
                                progress_cb, prog_pct,
                                f"文字起こし中 {completed}/{n_chunks}... / Transcribing chunk {completed}/{n_chunks}..."
                            )
                        except Exception as e:
                            logger.error(f"Error transcribing chunk: {e}")
                            raise e
            else:
                # Fallback to sequential to guarantee exact ordered execution and callbacks
                for idx in range(n_chunks):
                    check_pause_cancel(job_id)
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

            check_pause_cancel(job_id)
            if is_cancelled(job_id):
                raise InterruptedError("Job cancelled")

            # ── Step 4: Speaker diarization ────────────────
            _progress(progress_cb, 82, "話者認識中... / Detecting speakers...")
            all_segments = self._diarize(wav_path, all_segments, num_speakers, diarization_mode, model_name=active_model, speaker_range=speaker_range)

            # ── Step 5: Done ───────────────────────────────
            _progress(progress_cb, 98, "後処理中... / Finalizing...")
            return all_segments

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _transcribe_chunk_qwen3_asr(
        self,
        chunk_path: str,
        offset: float,
        total_duration: float,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        chunk_idx: int = 0,
        n_chunks: int = 1,
        job_id: str = "",
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with Qwen3-ASR."""
        try:
            logger.info(f"Running Qwen3-ASR transcription on chunk {chunk_idx+1}/{n_chunks} (offset={offset:.1f}s)...")
            results = self._qwen3_model.transcribe(chunk_path)
            
            # Handle return format robustly
            if isinstance(results, list):
                result = results[0]
            else:
                result = results
                
            text = ""
            if hasattr(result, "text"):
                text = result.text
            elif isinstance(result, dict) and "text" in result:
                text = result["text"]
            else:
                text = str(result)
                
            text = text.strip()
            if not text:
                return []
                
            if on_language_detected:
                try:
                    lang = "ja"
                    if hasattr(result, "language") and result.language:
                        lang = "ja" if "ja" in result.language.lower() or "japanese" in result.language.lower() else "en"
                    on_language_detected(lang)
                except Exception as e:
                    logger.warning(f"Failed to call on_language_detected in Qwen3-ASR runner: {e}")
                    
            chunk_duration = self._get_duration(chunk_path)
            if chunk_duration <= 0:
                chunk_duration = 30.0
                
            segments_out = [{
                "start": round(offset, 3),
                "end":   round(offset + chunk_duration, 3),
                "speaker": "Speaker 1",
                "text": text,
                "words": [],
            }]
            
            if total_duration > 0 and progress_cb:
                processed_secs = min(offset + chunk_duration, total_duration)
                pct = 10 + int(70 * (processed_secs / total_duration))
                pct = min(pct, 79)
                _progress(
                    progress_cb, pct,
                    f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
                )
                
            return segments_out
        except Exception as e:
            logger.error(f"Qwen3-ASR chunk transcription error: {e}", exc_info=True)
            return []

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
        diarization_mode: str = "accurate",
        model_name: Optional[str] = None,
        beam_size: Optional[int] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with faster-whisper."""
        # Set beam_size based on model profiles if not explicitly passed
        if beam_size is None:
            resolved_model = model_name if model_name else self._current_whisper_model_name
            is_large = resolved_model and "large" in resolved_model.lower()
            beam_size = 3 if is_large else 1

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
                word_timestamps=True,  # Mandatory for speaker label merging
                condition_on_previous_text=False,  # Prevent hallucination loops & speed boost
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

    def _diarize_sherpa_onnx(self, wav_path: str, num_speakers: Optional[int] = None) -> List[Dict]:
        """Perform speaker diarization using Sherpa-ONNX offline engine."""
        try:
            import sherpa_onnx
            import soundfile as sf
        except ImportError as e:
            logger.error(f"sherpa_onnx or soundfile library not installed: {e}. Please run pip install sherpa-onnx.")
            return []

        try:
            model_dir = Path(__file__).parent.parent.parent / "app" / "models" / "sherpa-onnx"
            segmentation_model = str(model_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx")
            embedding_model = str(model_dir / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")

            if not os.path.exists(segmentation_model) or not os.path.exists(embedding_model):
                logger.error(f"Sherpa-ONNX model files are missing at {segmentation_model} or {embedding_model}.")
                return []

            config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
                segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                    pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                        model=segmentation_model
                    ),
                ),
                embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=embedding_model
                ),
                clustering=sherpa_onnx.FastClusteringConfig(
                    num_clusters=num_speakers if (num_speakers is not None and num_speakers > 0) else -1,
                    threshold=0.5
                ),
                min_duration_on=0.3,
                min_duration_off=0.5,
            )

            if not config.validate():
                logger.error("Sherpa-ONNX config validation failed.")
                return []

            logger.info("Initializing Sherpa-ONNX offline speaker diarizer...")
            sd = sherpa_onnx.OfflineSpeakerDiarization(config)

            logger.info("Reading audio file for diarization...")
            audio, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
            audio = audio[:, 0]

            logger.info("Running Sherpa-ONNX diarization process...")
            result = sd.process(audio).sort_by_start_time()

            speaker_segments = []
            for r in result:
                speaker_segments.append({
                    "start": r.start,
                    "end": r.end,
                    "speaker": f"Speaker {r.speaker + 1}"
                })

            return speaker_segments
        except Exception as e:
            logger.error(f"Sherpa-ONNX diarization process failed: {e}", exc_info=True)
            return []

    def _diarize(
        self,
        wav_path: str,
        segments: List[Dict],
        num_speakers: Optional[int] = None,
        diarization_mode: str = "accurate",
        model_name: Optional[str] = None,
        speaker_range: str = "normal",
    ) -> List[Dict]:
        """Run Pyannote and assign speaker labels to transcript segments, splitting segments by speaker change."""
        if diarization_mode == "off":
            logger.info("Speaker diarization is disabled ('off' mode). Skipping diarization.")
            for seg in segments:
                seg["speaker"] = "Speaker 1"
                seg.pop("words", None)
            return segments

        if num_speakers == 1:
            logger.info("Single speaker requested. Bypassing diarization models and labeling all segments as 'Speaker 1'.")
            for seg in segments:
                seg["speaker"] = "Speaker 1"
                seg.pop("words", None)
            return segments

        if diarization_mode == "sherpa-onnx":
            logger.info("Using Sherpa-ONNX (ONNX Runtime) for Speaker Diarization...")
            speaker_segments = self._diarize_sherpa_onnx(wav_path, num_speakers)
            if not speaker_segments:
                logger.warning("Sherpa-ONNX diarization failed or returned no speaker tracks. Falling back to Speaker 1.")
                for seg in segments:
                    seg["speaker"] = "Speaker 1"
                    seg.pop("words", None)
                return segments

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
                        "start":   block_words[0]["start"],
                        "end":     block_words[-1]["end"],
                        "speaker": spk,
                        "text":    sub_text,
                    })
            return final_segments

        ok = self._load_pyannote(diarization_mode)
        if not ok or not segments:
            for seg in segments:
                seg["speaker"] = "Speaker 1"
                seg.pop("words", None)
            return segments

        try:
            kwargs = {}
            if num_speakers is not None and num_speakers > 0:
                kwargs["num_speakers"] = num_speakers
            else:
                if speaker_range == "large":
                    kwargs["min_speakers"] = 2
                    kwargs["max_speakers"] = 15
                else:
                    kwargs["min_speakers"] = 2
                    kwargs["max_speakers"] = 7
            
            if diarization_mode == "fast":
                kwargs["segmentation_step"] = 0.25
                logger.info("Applying fast speaker detection optimization: segmentation_step = 0.25")

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

            # Renumber speakers serially in chronological order of appearance
            speaker_mapping = {}
            next_speaker_num = 1
            for seg in final_segments:
                spk = seg["speaker"]
                if spk not in speaker_mapping:
                    speaker_mapping[spk] = f"Speaker {next_speaker_num}"
                    next_speaker_num += 1
                seg["speaker"] = speaker_mapping[spk]

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
