"""
hardware_detector.py
Detects CPU / RAM / GPU capabilities and returns the optimal
Whisper model, chunk size, compute type, and thread count.
"""

import logging
import psutil
import os

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
    cpu_cores = psutil.cpu_count(logical=True) or 4
    ram_bytes = psutil.virtual_memory().total
    ram_gb = round(ram_bytes / (1024 ** 3), 1)

    # ── GPU ────────────────────────────────────────────────────
    gpu_available = False
    gpu_name = None
    gpu_vram_gb = None

    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_vram_bytes = torch.cuda.get_device_properties(0).total_memory
            gpu_vram_gb = round(gpu_vram_bytes / (1024 ** 3), 1)
    except Exception as e:
        logger.warning(f"Could not query GPU via torch: {e}")

    # ── Tier classification ────────────────────────────────────
    if gpu_available and gpu_vram_gb and gpu_vram_gb >= 6:
        tier = "heavy"
        device = "cuda"
        model_name = "large-v3" if gpu_vram_gb >= 10 else "medium"
        compute_type = "float16"
        chunk_seconds = 300           # 5 min
        threads = min(cpu_cores, 8)

    elif ram_gb >= 16:
        tier = "medium"
        device = "cpu"
        model_name = "base"
        compute_type = "int8"
        chunk_seconds = 180           # 3 min
        threads = min(cpu_cores, 4)

    else:
        tier = "light"
        device = "cpu"
        model_name = "small"
        compute_type = "int8"
        chunk_seconds = 120           # 2 min
        threads = min(cpu_cores, 2)

    profile = {
        "tier": tier,
        "device": device,
        "model_name": model_name,
        "compute_type": compute_type,
        "chunk_seconds": chunk_seconds,
        "threads": threads,
        "cpu_cores": cpu_cores,
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
