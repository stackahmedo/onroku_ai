# 🚀 How to Start Onroku AI V5.5

Welcome! This guide outlines how to start **Onroku AI V5.5** on your Windows system, both as an end-user (using the silent desktop shortcut) and as a developer.

---

## 📋 1. Prerequisites

Before starting, make sure your computer has the following tools installed:
* **Node.js**: Version 16.x or newer (recommended for the React frontend).
* **Python**: Version 3.10.x (recommended for the Whisper/FastAPI backend).
* **NVIDIA CUDA Toolkit & cuDNN** *(Optional)*: Highly recommended if you have an NVIDIA GPU to accelerate transcription.

---

## ⚡ 2. The Easy Way: One-Click Desktop Shortcut

To make launching Onroku AI seamless, we have provided a PowerShell script that installs a silent bypass launcher on your Desktop.

### Setup the Shortcut:
1. Open a PowerShell terminal in the project root directory.
2. Run the following command:
   ```powershell
   ./create_shortcut.ps1
   ```
3. A beautiful shortcut icon named **Onroku AI** will appear on your Desktop.

### How to Run:
* Simply double-click the **Onroku AI** shortcut icon on your Desktop.
* It will launch both the FastAPI background server and the Electron application silently without displaying annoying terminal command windows.

---

## 🛠️ 3. Starting the Production Environment

To run the fully optimized production environment manually without the desktop shortcut, use our launcher scripts.

### Step 1: Run the Production Launcher
In your file explorer or terminal, run:
```bash
start_prod.bat
```
This batch script will:
1. Boot the backend FastAPI service on `http://127.0.0.1:8000`.
2. Wait for the server to report healthy.
3. Launch the compiled Electron application frame pointing to the fast local assets.

---

## 💻 4. Starting the Development Environment

If you are modifying the source code and want to see your changes applied instantly via hot-reload, start the app in development mode.

### Step 1: Install Dependencies
Run these commands in the project root:
```bash
# Install frontend react dependencies
npm install
```

### Step 2: Start the Python Backend
1. Open a terminal and navigate to the project directory.
2. Start the FastAPI server:
   ```bash
   python launcher.py
   ```
   *(Or activate your virtual environment `.venv` and run `uvicorn app.backend.main:app --reload`)*

### Step 3: Start the React Frontend
Open a separate terminal and run:
```bash
npm run dev
```
This will open the application inside your local web browser at `http://localhost:3000` with full React developer hot-reloading active.

---

## 🔄 5. UI Controls Guide

Once the application is running, you can use these custom window utility controls located in the top-right header:
* 🔄 **Refresh (Refresh Page)**: Instantly reloads the local web frame to apply stylesheet updates or recover from lost connections.
* — **Minimize**: Minimizes the window to your Windows taskbar.
* ⬜ **Maximize / Restore**: Expands the window to fullscreen or restores it to windowed mode.
* ✕ **Close**: Safely shuts down the application frame and terminates background processes.
