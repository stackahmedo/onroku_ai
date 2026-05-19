# 🍎 Running Onroku AI V5.5 on macOS

This guide provides step-by-step instructions to configure, launch, and optimize **Onroku AI V5.5** on macOS platforms. The application fully supports both **Intel-based Macs** and **Apple Silicon (M1, M2, M3, M4) Macs**.

---

## 📋 1. Prerequisites

To run Onroku AI locally on macOS, you must install a few system dependencies. The easiest way is using the macOS package manager **[Homebrew](https://brew.sh/)**.

Open your Terminal app and run:

```bash
# 1. Install Node.js & npm (Required for the Electron/React UI)
brew install node

# 2. Install Python 3.10 or 3.11 (Required for the FastAPI backend)
brew install python@3.10

# 3. Install FFmpeg (Crucial for audio extraction and conversion)
brew install ffmpeg
```

---

## 🛠️ 2. Step-by-Step Installation

Once the prerequisites are ready, set up your project environment:

### Step 1: Install Frontend Packages
Navigate to the project root directory and run:
```bash
npm install
```

### Step 2: Set Up Python Virtual Environment
Creating a virtual environment ensures that backend dependencies do not interfere with system-wide Python modules:
```bash
# 1. Create a virtual environment named 'venv'
python3 -m venv venv

# 2. Activate the environment
source venv/bin/activate

# 3. Install all required packages
pip install -r requirements.txt
```

---

## 🚀 3. Starting the Application

You can start Onroku AI in developer mode or package it for normal use:

### 💻 Starting in Developer Mode (With Hot-Reload)
Run the dynamic python launcher to automatically start the background server and open the Electron shell:
```bash
# Ensure your virtual environment is active
source venv/bin/activate

# Run the launcher
python3 launcher.py
```
*Press `Ctrl+C` in the terminal at any time to safely shut down both the client and backend processes.*

---

## ⚡ 4. Enabling Apple Silicon Neural Engine & GPU (CoreML)

On Apple Silicon (M1/M2/M3/M4) systems, Onroku AI's **Hybrid Engine** is pre-configured to utilize your Mac's **Neural Engine (ANE)** and integrated **Apple GPU** via `whisper.cpp`. 

If no custom binary is added, the app gracefully falls back to CPU mode using Apple's built-in **Apple Accelerate framework**, which is still extremely fast.

To activate 100% hardware-acceleration:

### Step A: Compile the CoreML whisper-cli Binary
1. Open a new terminal window and clone the official repository:
   ```bash
   git clone https://github.com/ggerganov/whisper.cpp.git
   cd whisper.cpp
   ```
2. Compile the executable with **CoreML** enabled:
   ```bash
   WHISPER_COREML=1 make -j
   ```
3. This creates a highly optimized compiled binary at `build/bin/whisper-cli`.

### Step B: Copy the Binary to Onroku AI
Move the compiled binary into Onroku AI’s local binary folder:
```bash
# Create the binary directory if it doesn't exist
mkdir -p /path/to/transcript_ai_v2/app/bin

# Copy the binary
cp ./build/bin/whisper-cli /path/to/transcript_ai_v2/app/bin/whisper-cli
```

### Step C: Grant macOS Execution Permissions
Because macOS blocks unidentified binaries by default, you must flag it as safe and executable:
```bash
# Grant execution permissions
chmod +x /path/to/transcript_ai_v2/app/bin/whisper-cli

# Bypass Gatekeeper quarantine (if macOS blocks it on startup)
xattr -d com.apple.quarantine /path/to/transcript_ai_v2/app/bin/whisper-cli
```

---

## 🔍 5. Troubleshooting macOS Bottlenecks

### 1. "Permission Denied" when running `whisper-cli`
* **Cause:** The binary file lacks execute permissions.
* **Solution:** Open a Terminal and run: `chmod +x app/bin/whisper-cli`.

### 2. "whisper-cli cannot be opened because developer cannot be verified"
* **Cause:** macOS Gatekeeper blocks self-compiled binaries.
* **Solution:** 
  1. Open Terminal and run: `xattr -d com.apple.quarantine app/bin/whisper-cli`.
  2. Alternatively, go to **System Settings > Privacy & Security**, scroll down, and click **"Allow Anyway"** next to the blocked `whisper-cli` notification.

### 3. High CPU Usage during Speaker Detection (PyTorch)
* **Cause:** PyTorch attempts to leverage all virtual cores on CPU, causing fan speed to rise.
* **Solution:** If speaker labels are not required, **uncheck "Speaker Detection" (話者認識)** when uploading. This skips Pyannote entirely, finishing transcription in seconds.
