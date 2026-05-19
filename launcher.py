"""
launcher.py  –  V2
Starts the FastAPI backend in a separate console window,
waits for it to be healthy, then launches the Electron frontend.
"""

import os
import sys
import subprocess
import time
import signal
import http.client
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_DIR  = Path(__file__).parent.absolute()
BACKEND_DIR  = PROJECT_DIR / "app" / "backend"
# Try V2 venv first, then fall back to V1 venv (which has all packages)
V1_PYTHON    = Path(r"i:\smart_grid_home\projects\transcript_ai\venv\Scripts\python.exe")
VENV_PYTHON  = PROJECT_DIR / "venv" / "Scripts" / "python.exe"
PYTHON       = str(VENV_PYTHON) if VENV_PYTHON.exists() else (str(V1_PYTHON) if V1_PYTHON.exists() else sys.executable)
NPM          = "npm.cmd" if os.name == "nt" else "npm"
import sys
IS_PROD      = "--prod" in sys.argv
processes = []


def log(msg): print(f"[Launcher] {msg}", flush=True)


def wait_for_backend(host="127.0.0.1", port=8000, timeout=60):
    """Poll /health until backend responds or timeout."""
    log("Waiting for backend to start...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            if resp.status == 200:
                log("Backend is healthy ✅")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_backend():
    log("Starting FastAPI backend...")
    cmd = [
        PYTHON, "-m", "uvicorn", "main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--log-level", "info",
    ]
    kwargs = {"cwd": str(BACKEND_DIR)}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000 # CREATE_NO_WINDOW
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    proc = subprocess.Popen(cmd, **kwargs)
    log(f"Backend PID: {proc.pid}")
    return proc


def start_react_dev():
    log("Starting React dev server...")
    cmd = [NPM, "run", "react-start"]
    env = os.environ.copy()
    env["BROWSER"] = "none"
    kwargs = {"env": env, "cwd": str(PROJECT_DIR)}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000 # CREATE_NO_WINDOW
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    proc = subprocess.Popen(cmd, **kwargs)
    log(f"React PID: {proc.pid}")
    return proc


def wait_for_react(host="127.0.0.1", port=3000, timeout=60):
    log("Waiting for React dev server...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/")
            resp = conn.getresponse()
            if resp.status in (200, 304):
                log("React dev server is healthy ✅")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_frontend():
    log("Starting Electron frontend...")
    if IS_PROD:
        cmd = [NPM, "exec", "electron", "app/frontend/main.js"]
    else:
        cmd = [NPM, "run", "electron-dev"]
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_DIR))
    log(f"Frontend PID: {proc.pid}")
    return proc


def cleanup(sig=None, frame=None):
    log("Shutting down...")
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try: p.kill()
            except Exception: pass
    log("Done.")
    sys.exit(0)


def main():
    print("=" * 56)
    print(f"  🎙️  Onroku AI V6.0  –  Application Launcher ({'PROD' if IS_PROD else 'DEV'})")
    print("=" * 56)

    signal.signal(signal.SIGINT,  cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    backend = start_backend()
    processes.append(backend)

    if not wait_for_backend(timeout=60):
        log("❌ Backend did not start in time. Check for errors.")
        cleanup()
        return

    if not IS_PROD:
        react = start_react_dev()
        processes.append(react)

        if not wait_for_react(timeout=60):
            log("❌ React dev server did not start in time. Check for errors.")
            cleanup()
            return

    frontend = start_frontend()
    processes.append(frontend)

    log("Application running. Press Ctrl+C to stop.\n")
    log("  Backend:   http://127.0.0.1:8000")
    log("  API docs:  http://127.0.0.1:8000/docs")

    # Watch for process death
    while True:
        time.sleep(2)
        if backend.poll() is not None:
            log("⚠️  Backend died — restarting...")
            backend = start_backend()
            processes[0] = backend
            if not wait_for_backend(timeout=30):
                log("❌ Backend restart failed.")
                break
        if frontend.poll() is not None:
            log("Frontend closed — exiting.")
            break

    cleanup()


if __name__ == "__main__":
    main()
