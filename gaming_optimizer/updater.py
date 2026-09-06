"""
Kage Utility auto-updater.

Two-tier update strategy:
  1. Fetch latest GitHub *release* — if the maintainer uploaded a KageUtility.exe
     asset, we download and swap it seamlessly (best experience).
  2. Fallback: fetch the tip commit of the `main` branch — download the source ZIP
     so the user can rebuild.

Config: change REPO_OWNER / REPO_NAME to match the GitHub repo.
"""
import json
import os
import sys
import shutil
import tempfile
import threading
import urllib.request
from pathlib import Path
from packaging.version import Version, InvalidVersion

APP_VERSION = "1.5"

REPO_OWNER = "gavincrawfordriley-source"
REPO_NAME = "Kage-utilityv3.2"
RELEASES_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
COMMITS_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
SOURCE_ZIP_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"

TIMEOUT = 8  # seconds


# ---------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------
def _api_get(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KageUtility"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception:
        return None


def _fetch_latest_release():
    """Returns {version, url, exe_asset_url, notes} or None."""
    data = _api_get(RELEASES_URL)
    if not data:
        return None
    tag = (data.get("tag_name") or "").lstrip("vV").strip()
    if not tag:
        return None
    exe_url = None
    for asset in data.get("assets", []):
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe") and "kageutility" in name:
            exe_url = asset.get("browser_download_url")
            break
    return {
        "version": tag,
        "url": data.get("html_url", ""),
        "exe_asset_url": exe_url,
        "notes": (data.get("body") or "").strip()[:600],
    }


def _fetch_latest_commit():
    """Returns short SHA of tip commit on main, or None."""
    data = _api_get(COMMITS_URL)
    if not data:
        return None
    sha = data.get("sha", "")
    if not sha:
        return None
    msg = (data.get("commit", {}).get("message") or "").splitlines()[0][:120]
    return {"sha": sha[:7], "message": msg, "full_sha": sha}


def _is_newer(remote: str, local: str) -> bool:
    try:
        return Version(remote) > Version(local)
    except InvalidVersion:
        return remote != local


# ---------------------------------------------------------------
# Async version check (used at startup)
# ---------------------------------------------------------------
def check_async(callback):
    """Call callback(info) if newer release exists. Silent on failure."""
    def worker():
        info = _fetch_latest_release()
        if info and _is_newer(info["version"], APP_VERSION):
            callback(info)
    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------
def _download(url: str, dest: str, progress_cb=None) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KageUtility"})
        with urllib.request.urlopen(req, timeout=30) as r:
            total = int(r.headers.get("Content-Length", "0") or 0)
            done = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb and total:
                        progress_cb(done / total)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------
# One-click install (Windows only, works only when running as a bundled exe)
# ---------------------------------------------------------------
def install_new_exe(remote_url: str, progress_cb=None) -> tuple[bool, str]:
    """
    Downloads the new KageUtility.exe next to the current one, writes a helper
    .bat that swaps and relaunches on process exit, then requests app close.

    Returns (started, message). If started=True, caller should App.quit().
    """
    if not getattr(sys, "frozen", False):
        return False, ("Auto-install only works from the compiled KageUtility.exe. "
                       "Rebuild manually from source.")

    if os.name != "nt":
        return False, "Auto-install is Windows-only."

    current_exe = Path(sys.executable).resolve()
    install_dir = current_exe.parent
    new_exe = install_dir / "KageUtility.new.exe"
    swap_bat = install_dir / "kage_swap.bat"

    if not _download(remote_url, str(new_exe), progress_cb):
        return False, "Download failed."

    # Batch script: wait for current process to release the exe, then swap.
    bat = f"""@echo off
setlocal
REM Wait for the currently-running KageUtility to close
:wait
timeout /t 1 /nobreak >nul
tasklist /FI "IMAGENAME eq {current_exe.name}" 2>nul | find /I "{current_exe.name}" >nul
if not errorlevel 1 goto wait
REM Swap
del /F /Q "{current_exe}"
ren "{new_exe}" "{current_exe.name}"
REM Relaunch
start "" "{current_exe}"
REM Clean up self
del /F /Q "%~f0"
"""
    try:
        swap_bat.write_text(bat, encoding="utf-8")
    except Exception as e:
        return False, f"Couldn't write swap script: {e}"

    # Launch the swap script detached — it will wait for us to exit
    try:
        import subprocess
        subprocess.Popen(
            ["cmd.exe", "/C", str(swap_bat)],
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        )
    except Exception as e:
        return False, f"Couldn't launch swap script: {e}"

    return True, "Downloaded. The app will restart with the new version in a moment."


# ---------------------------------------------------------------
# Source-zip fallback: extract to a folder, open Explorer
# ---------------------------------------------------------------
def download_source_zip(progress_cb=None) -> tuple[bool, str]:
    """
    Grabs the main-branch ZIP, extracts to %APPDATA%\\KageUtility\\updates\\<sha>\\
    and opens Explorer there so the user can run build.bat.
    Returns (ok, path_or_error).
    """
    tmp_zip = os.path.join(tempfile.gettempdir(), "kage_source_main.zip")
    if not _download(SOURCE_ZIP_URL, tmp_zip, progress_cb):
        return False, "Download failed."
    try:
        import zipfile
        base = Path(os.getenv("APPDATA", tempfile.gettempdir())) / "KageUtility" / "updates"
        base.mkdir(parents=True, exist_ok=True)
        # Wipe old extracted folders to keep this tidy
        with zipfile.ZipFile(tmp_zip) as z:
            top = z.namelist()[0].split("/")[0] if z.namelist() else "kage-utility-main"
            z.extractall(base)
        target = base / top
        # Open Explorer so user can find build.bat
        try:
            os.startfile(str(target))
        except Exception:
            pass
        return True, str(target)
    except Exception as e:
        return False, f"Extract failed: {e}"
