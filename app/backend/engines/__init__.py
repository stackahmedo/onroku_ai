"""
engines package entrypoint.
Imports all engine classes under try/except to prevent import errors of one
engine from crashing others or blocking backend startup.
"""

ENGINE_STATUS = {}
WhisperEngine = None
WhisperCppEngine = None
QwenEngine = None
PyannoteDiarizationEngine = None
SherpaDiarizationEngine = None

try:
    from .whisper import WhisperEngine
    ENGINE_STATUS["whisper"] = {"available": True, "error": None}
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Whisper engine import failed: {e}")
    ENGINE_STATUS["whisper"] = {"available": False, "error": str(e)}

try:
    from .whisper_cpp import WhisperCppEngine
    ENGINE_STATUS["whisper_cpp"] = {"available": True, "error": None}
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"WhisperCpp engine import failed: {e}")
    ENGINE_STATUS["whisper_cpp"] = {"available": False, "error": str(e)}

try:
    from .qwen import QwenEngine
    ENGINE_STATUS["qwen"] = {"available": True, "error": None}
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Qwen engine import failed: {e}")
    ENGINE_STATUS["qwen"] = {"available": False, "error": str(e)}

try:
    from .pyannote import PyannoteDiarizationEngine
    ENGINE_STATUS["pyannote"] = {"available": True, "error": None}
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Pyannote engine import failed: {e}")
    ENGINE_STATUS["pyannote"] = {"available": False, "error": str(e)}

try:
    from .sherpa import SherpaDiarizationEngine
    ENGINE_STATUS["sherpa"] = {"available": True, "error": None}
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Sherpa engine import failed: {e}")
    ENGINE_STATUS["sherpa"] = {"available": False, "error": str(e)}
