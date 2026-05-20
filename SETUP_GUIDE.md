# 📖 Onroku AI Setup & Installation Guide

This guide provides step-by-step instructions on how to download, install, configure, and run **Onroku AI** on your computer.

---

## 📋 1. Prerequisites (What You Need)

Before installing Onroku AI, ensure your system has the following dependencies installed:

### 1. Git (Version Control)
* Required to clone the repository.
* **Windows**: Download from [git-scm.com](https://git-scm.com/).
* **macOS**: Installed automatically with Xcode Command Line Tools, or via Homebrew: `brew install git`.

### 2. Node.js & npm (v18 or newer)
* Required to run and build the Electron and React user interface.
* Download from [nodejs.org](https://nodejs.org/).
* Check version in terminal/command prompt: `node -v`

### 3. Python (v3.10 or v3.11)
* Required for the FastAPI backend and AI processing libraries (Whisper, Pyannote).
* **Important**: Python 3.12+ may have compatibility issues with some ML libraries (PyTorch). Please stick to **3.10.x** or **3.11.x**.
* **Windows**: Download from [python.org](https://www.python.org/downloads/). Ensure you check **"Add Python to PATH"** during installation.
* **macOS**: Install using Homebrew: `brew install python@3.10`
* Check version: `python --version` or `python3 --version`

### 4. FFmpeg (Audio/Video Engine)
* Critical for extracting, decoding, and preprocessing media files.
* **Windows (via Winget)**: Open PowerShell and run:
  ```powershell
  winget install --id Gyan.FFmpeg -e
  ```
  *(Then restart your computer so your system paths are updated).*
* **macOS (via Homebrew)**: Open Terminal and run:
  ```bash
  brew install ffmpeg
  ```

---

## 📥 2. How to Download from GitHub

You can download the application files using one of the following methods:

### Option A: Using Git (Recommended)
Open your terminal or command prompt, navigate to the folder where you want to save the project, and run:
```bash
git clone https://github.com/your-username/onroku_ai.git
cd onroku_ai
```

### Option B: Downloading the ZIP Archive
1. Visit the repository page on GitHub.
2. Click the green **Code** button in the top-right corner.
3. Click **Download ZIP**.
4. Extract the downloaded ZIP file to a folder on your computer.
5. Open your terminal and navigate inside that folder:
   ```bash
   cd onroku_ai-main
   ```

---

## 🛠️ 3. How to Install on your PC

Follow these steps to set up the software environment:

### Step 1: Install Frontend Packages
In the root directory of the project, run:
```bash
npm install
```
This downloads and installs all React, Electron, and packaging dependencies.

### Step 2: Set Up Python Virtual Environment
Creating a virtual environment ensures Python libraries do not conflict with other system modules.

#### 🪟 Windows Setup:
1. Create a virtual environment:
   ```powershell
   python -m venv venv
   ```
2. Activate the environment:
   ```powershell
   .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

#### 🍎 macOS / Linux Setup:
1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   ```
2. Activate the environment:
   ```bash
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 4. How to Run the Application

You can launch Onroku AI in developer mode (for code changes/hot-reloads) or production mode:

### Method A: Using the Launcher Script (Cross-Platform)
Ensure your virtual environment is active, then run:
```bash
python launcher.py
```
This script automatically:
1. Boots up the FastAPI backend on `http://127.0.0.1:8000`.
2. Tests the connection until the backend is healthy.
3. Launches the Electron UI container shell.

### Method B: One-Click Windows Desktop Shortcut (Windows Only)
We provide a setup script that adds a clean shortcut icon directly to your Windows desktop.
1. Open a PowerShell console in the project root folder.
2. Run the shortcut creator script:
   ```powershell
   ./create_shortcut.ps1
   ```
3. Look at your Windows Desktop for **Onroku AI**. Double-click it to start the application silently (terminal command windows will be hidden in the background).

### Method C: Running Production Mode Manually (Windows)
Double-click or run:
```bash
start_prod.bat
```

### Method D: Running Manual Development Mode (Separate Terminals)
If you prefer to run services manually for debugging:
*   **Terminal 1 (Backend)**:
    ```bash
    cd app/backend
    python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
    ```
*   **Terminal 2 (Frontend React)**:
    ```bash
    npm run dev
    ```
    *(Accessible in a standard browser at `http://localhost:3000`)*

---

## 🔒 5. Optional: Setting up Offline Capabilities
If you want to run Onroku AI 100% offline (without any internet access during operation):
1. **Hugging Face Token**: If using speaker diarization (Pyannote), save your Hugging Face user access token inside a file named `hf_token.txt` in the root folder of the project.
2. **Download Models**: Run the application once while connected to the internet and upload a small audio sample. This prompts the engines to fetch and cache the required Whisper models (`app/models/whisper/`) and Pyannote models (`app/models/pyannote/`) locally. Once downloaded, you can disconnect from the internet.
