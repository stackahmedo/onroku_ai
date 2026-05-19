# Onroku AI Auto-Update Roadmap 🚀

This guide explains how to implement internet-based automatic updates for **Onroku AI V5.5** in the future. 

Because Onroku AI consists of an **Electron frontend** and a **Python backend**, you have two highly effective options to achieve seamless background updates when you upload a new version to the internet.

---

## 📋 Option 1: Packaged Installer Auto-Update (Recommended)
This uses **Electron's native Auto-Updater** combined with **GitHub Releases** (free, secure, and fast). When you publish a new version on GitHub, the installed app automatically downloads the update in the background and prompts the user to restart.

### 🛠️ What You Need to Setup
1. **GitHub Repository**:
   * Create a public or private GitHub repository for your project (e.g., `https://github.com/your-username/onroku-ai`).
2. **Configure `package.json`**:
   * Ensure your repository link is listed in your `package.json` configurations:
     ```json
     "repository": {
       "type": "git",
       "url": "git+https://github.com/your-username/onroku-ai.git"
     }
     ```
3. **Install `electron-updater`**:
   * Add the library to your Electron app:
     ```bash
     npm install electron-updater --save
     ```
4. **Enable Auto-Updater in `app/frontend/main.js`**:
   * Add the following listener to your Electron startup file:
     ```javascript
     const { autoUpdater } = require("electron-updater");

     app.on("ready", () => {
       // Check for updates every time the app boots
       autoUpdater.checkForUpdatesAndNotify();
     });

     // Optional: Show interactive progress toast to the user
     autoUpdater.on("update-downloaded", () => {
       dialog.showMessageBox({
         type: "info",
         title: "Update Ready",
         message: "A new version of Onroku AI has been downloaded. Restart the app to apply?",
         buttons: ["Restart", "Later"]
       }).then((result) => {
         if (result.response === 0) {
           autoUpdater.quitAndInstall();
         }
       });
     });
     ```
5. **How to Publish an Update**:
   * Build the standalone installer by running:
     ```bash
     npm run dist
     ```
   * Create a new **Release** on your GitHub repository page and upload the compiled `.exe` installer.
   * Installed apps on all users' PCs will automatically detect the new release, download the patch in the background, and prompt them to update!

---

## 📦 Option 2: Portable ZIP Hot-Patching (Best for Portable/ZIP Versions)
If you prefer to keep the app portable (running straight from the ZIP without installing), you can implement a **Hot-Patching script** inside your launcher.py launcher.

### ⚙️ How It Works
* **1. Request Version Info**: The app pings your server to read a small online version metadata file.
* **2. Compare Version**: If the online version is newer, the app prompts the user to download.
* **3. Stream Download**: The app downloads the updated zip containing new frontend and backend files.
* **4. Hot Extract**: Extracts and overwrites existing directories **while leaving user databases completely untouched!**
* **5. Hot Reboot**: Restarts the launcher process instantly.

### 🛠️ What You Need to Setup
1. **Host a Version File**:
   * Host a simple `version.json` file online (e.g. on GitHub Gist, GitHub Pages, or your own server):
     ```json
     {
       "version": "5.6.0",
       "zip_url": "https://github.com/your-username/onroku-ai/releases/download/v5.6.0/Onroku_AI_V5.6.zip"
     }
     ```
2. **Add a Startup Check in Python**:
   * Add a lightweight update check at the very beginning of your `launcher.py` script:
     ```python
     import urllib.request
     import json
     import zipfile
     import shutil

     CURRENT_VERSION = "5.5.0"
     UPDATE_URL = "https://your-website.com/version.json"

     def check_for_updates():
         try:
             # Fetch latest version info
             with urllib.request.urlopen(UPDATE_URL, timeout=5) as response:
                 data = json.loads(response.read().decode())
                 latest_version = data.get("version")
                 download_url = data.get("zip_url")
                 
                 if latest_version and latest_version > CURRENT_VERSION:
                     print(f"[Updater] A new version V{latest_version} is available! Downloading...")
                     
                     # 1. Download updated ZIP
                     zip_path = "update.zip"
                     urllib.request.urlretrieve(download_url, zip_path)
                     
                     # 2. Extract and patch local directory (excluding databases or logs)
                     with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                         for file_info in zip_ref.infolist():
                             # Safety: Do not overwrite database files or user logs
                             if "app.db" not in file_info.filename and "logs" not in file_info.filename:
                                 zip_ref.extract(file_info, ".")
                     
                     # 3. Clean up
                     os.remove(zip_path)
                     print("[Updater] Update complete! Restarting...")
                     return True
         except Exception as e:
             print(f"[Updater] Update check skipped: {e}")
         return False
     ```

---

### 🛡️ Best Practices for Database Safety
Whichever method you choose, make sure your auto-updater **never deletes or overwrites the SQLite database file** stored at:
📂 app/database/app.db

This guarantees that when your users update to a new version, all of their previous transcription history and speech recordings remain **100% safe and intact**!
