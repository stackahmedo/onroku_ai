"""
hardware_detector.py
Detects CPU / RAM / GPU capabilities and returns the optimal
Whisper model, chunk size, compute type, and thread count.
"""

import logging
import psutil
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_hardware() -> dict:
    """
    Probe the system and return a hardware profile dict:
    {
        tier: "light" | "medium" | "heavy",
        device: "cuda" | "cpu",
        model_name: str,
        compute_type: str,
        chunk_seconds: int,
        threads: int,
        cpu_cores: int,
        ram_gb: float,
        gpu_name: str | None,
        gpu_vram_gb: float | None,
    }
    """
    # ── CPU / RAM ──────────────────────────────────────────────
    # Use physical cores rather than logical threads to eliminate thread thrashing and contention
    cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 4
    ram_bytes = psutil.virtual_memory().total
    ram_gb = round(ram_bytes / (1024 ** 3), 1)

    cpu_name = f"CPU ({cpu_cores} Cores)"
    try:
        import platform
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        elif platform.system() == "Darwin":
            import subprocess
            cpu_name = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
        elif platform.system() == "Linux":
            import subprocess
            cpu_name = subprocess.check_output("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True).decode().strip()
    except Exception as e:
        logger.warning(f"Could not query exact CPU name: {e}")

    # ── GPU / Platforms ────────────────────────────────────────
    gpu_available = False
    gpu_name = None
    gpu_vram_gb = None
    gpu_type = "none"  # "nvidia" | "amd_intel" | "apple_silicon" | "none"
    engine = "faster-whisper"

    import platform
    is_windows = platform.system() == "Windows"
    is_mac = platform.system() == "Darwin"

    app_root = Path(__file__).resolve().parent.parent
    bin_dir = app_root / "bin"
    binary_name = "whisper-cli.exe" if is_windows else "whisper-cli"
    whisper_cli_local = bin_dir / binary_name
    whisper_cpp_available = shutil.which(binary_name) is not None or whisper_cli_local.exists()

    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_vram_bytes = torch.cuda.get_device_properties(0).total_memory
            gpu_vram_gb = round(gpu_vram_bytes / (1024 ** 3), 1)
            gpu_type = "nvidia"
            engine = "faster-whisper"
        elif is_mac:
            # Check if Apple Silicon (M1/M2/M3/M4)
            # Typically brand string contains "Apple"
            if "Apple" in cpu_name:
                gpu_name = cpu_name  # e.g. "Apple M4"
                gpu_type = "apple_silicon"
                gpu_available = whisper_cpp_available
                engine = "whisper.cpp" if whisper_cpp_available else "faster-whisper"
        elif is_windows:
            # Fallback for non-NVIDIA cards (AMD / Intel) so they are displayed correctly!
            import subprocess
            try:
                out = subprocess.check_output(
                    ['powershell', '-Command', 'Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name'],
                    stderr=subprocess.DEVNULL
                ).decode()
                names = [l.strip() for l in out.split('\n') if l.strip()]
                valid_gpus = [n for n in names if "Microsoft" not in n and "Basic Render" not in n]
                if valid_gpus:
                    gpu_name = valid_gpus[0]
                    gpu_type = "amd_intel"
                    gpu_available = whisper_cpp_available
                    engine = "whisper.cpp" if whisper_cpp_available else "faster-whisper"
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not query GPU/platform details: {e}")

    # ── Tier classification ────────────────────────────────────
    if gpu_type == "nvidia" and gpu_vram_gb:
        if gpu_vram_gb >= 8:
            tier = "heavy"
            device = "cuda"
            model_name = "large-v3"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 8)
        elif gpu_vram_gb >= 4:
            tier = "medium"
            device = "cuda"
            model_name = "medium"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 4)
        else:
            tier = "light"
            device = "cuda"
            model_name = "small"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 2)
    elif gpu_type == "apple_silicon" and engine == "whisper.cpp":
        # Apple Silicon unified memory accelerated by whisper.cpp/CoreML
        if ram_gb >= 16:
            tier = "heavy"
            device = "coreml"
            model_name = "medium"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 8)
        else:
            tier = "medium"
            device = "coreml"
            model_name = "small"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 4)
    elif gpu_type == "apple_silicon":
        # Apple Silicon fallback to CPU-only if whisper.cpp is not available
        device = "cpu"
        engine = "faster-whisper"
        if ram_gb >= 16:
            tier = "medium"
            model_name = "base"
            compute_type = "int8"
            chunk_seconds = 0
            threads = min(cpu_cores, 4)
        else:
            tier = "light"
            model_name = "small"
            compute_type = "int8"
            chunk_seconds = 0
            threads = min(cpu_cores, 2)
    elif gpu_type == "amd_intel" and engine == "whisper.cpp":
        # AMD / Intel GPU running on Vulkan (whisper.cpp only)
        if ram_gb >= 16:
            tier = "heavy"
            device = "vulkan"
            model_name = "medium"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 8)
        else:
            tier = "medium"
            device = "vulkan"
            model_name = "small"
            compute_type = "float16"
            chunk_seconds = 0
            threads = min(cpu_cores, 4)
    elif gpu_type == "amd_intel":
        # AMD / Intel fallback to CPU-only if whisper.cpp is not available
        device = "cpu"
        engine = "faster-whisper"
        if ram_gb >= 16:
            tier = "medium"
            model_name = "base"
            compute_type = "int8"
            chunk_seconds = 0
            threads = min(cpu_cores, 4)
        else:
            tier = "light"
            model_name = "small"
            compute_type = "int8"
            chunk_seconds = 0
            threads = min(cpu_cores, 2)
    else:
        # CPU-only fallback
        device = "cpu"
        engine = "faster-whisper"
        if ram_gb >= 16:
            tier = "medium"
            model_name = "base"
            compute_type = "int8"
            chunk_seconds = 0
            threads = min(cpu_cores, 4)
        else:
            tier = "light"
            model_name = "small"
            compute_type = "int8"
            chunk_seconds = 0
            threads = min(cpu_cores, 2)

    profile = {
        "tier": tier,
        "device": device,
        "engine": engine,
        "gpu_type": gpu_type,
        "model_name": model_name,
        "compute_type": compute_type,
        "chunk_seconds": chunk_seconds,
        "threads": threads,
        "cpu_cores": cpu_cores,
        "cpu_name": cpu_name,
        "ram_gb": ram_gb,
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram_gb,
    }

    logger.info(
        f"Hardware detected: tier={tier}, device={device}, "
        f"model={model_name}, RAM={ram_gb}GB, GPU={gpu_name or 'none'}"
    )
    return profile


def select_best_engine(hw: dict) -> dict:
    """
    Select the optimal engine settings based on detected hardware profile.
    Returns a config dict containing ASR/speaker engine choices.
    """
    gpu_type = hw.get("gpu_type", "none")
    gpu_vram_gb = hw.get("gpu_vram_gb", 0.0) or 0.0
    ram_gb = hw.get("ram_gb", 8.0)

    asr_engine = hw.get("engine", "faster-whisper")
    asr_device = hw.get("device", "cpu")

    # 1. NVIDIA GPU (CUDA)
    if asr_engine == "faster-whisper" and asr_device == "cuda" and gpu_vram_gb >= 4.0:
        return {
            "asr_engine": "faster-whisper",
            "asr_device": "cuda",
            "model": "medium" if gpu_vram_gb < 8.0 else "large-v3",
            "compute_type": "float16",
            "speaker_engine": "pyannote",
            "speaker_device": "cuda",
            "beam_size": 1,
        }

    # 2. Apple Silicon / AMD / Intel using whisper.cpp
    if asr_engine == "whisper.cpp":
        if gpu_type == "apple_silicon":
            return {
                "asr_engine": "whisper.cpp",
                "asr_device": "coreml",
                "model": "small",
                "compute_type": "float16",
                "speaker_engine": "pyannote",
                "speaker_device": "cpu",
                "beam_size": 1,
            }
        if gpu_type == "amd_intel":
            model = "medium-q5_0" if ram_gb >= 16.0 else "small-q5_0"
            return {
                "asr_engine": "whisper.cpp",
                "asr_device": "vulkan",
                "model": model,
                "compute_type": "float16",
                "speaker_engine": "pyannote",
                "speaker_device": "cpu",
                "beam_size": 1,
            }

    # 3. CPU Only / Fallback
    model = "base" if ram_gb >= 16.0 else "small"
    return {
        "asr_engine": "faster-whisper",
        "asr_device": "cpu",
        "model": model,
        "compute_type": "int8",
        "speaker_engine": "pyannote",
        "speaker_device": "cpu",
        "beam_size": 1,
    }

