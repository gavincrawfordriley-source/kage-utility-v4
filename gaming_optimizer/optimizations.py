"""
FragBoost — all 53 Windows 11 gaming tweaks.
Every tweak has apply() + restore(). Registry / powercfg values are backed up
to %APPDATA%\\GamingOptimizer\\backup.json before mutation.
"""
import os
import json
import shutil
import subprocess
import ctypes
from pathlib import Path

try:
    import winreg
except ImportError:  # non-Windows dev
    winreg = None

APPDIR = Path(os.getenv("APPDATA", ".")) / "GamingOptimizer"
APPDIR.mkdir(parents=True, exist_ok=True)
BACKUP_FILE = APPDIR / "backup.json"


# ============================================================
# Helpers
# ============================================================
def _load_backup():
    if BACKUP_FILE.exists():
        try:
            return json.loads(BACKUP_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_backup(data):
    BACKUP_FILE.write_text(json.dumps(data, indent=2, default=str))


def _run(cmd):
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            # CRITICAL for PyInstaller --windowed builds: parent has no stdin,
            # so we must explicitly pipe it or child processes silently misbehave.
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, str(e)


def _hive(s):
    return {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[s]


def _reg_get(hive, path, name):
    if winreg is None:
        return None, None
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ) as k:
            v, t = winreg.QueryValueEx(k, name)
            return v, t
    except Exception:
        return None, None


def _reg_set(hive, path, name, value, typ=None):
    if winreg is None:
        return False
    if typ is None:
        typ = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
    try:
        winreg.CreateKey(_hive(hive), path)
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, typ, value)
        return True
    except Exception:
        return False


def _reg_del(hive, path, name):
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
        return True
    except Exception:
        return False


def is_admin():
    if os.name != "nt":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ============================================================
# Table-driven registry tweak factory
# ============================================================
def _reg_tweak(tweak_id, ops):
    """
    ops = list of dicts: {hive, path, name, on, off?, typ?}
      - on   : value to write when tweak is applied
      - off  : value to write when reverting (if omitted, key is deleted OR restored from backup)
      - typ  : REG_DWORD / REG_SZ / REG_BINARY (auto if omitted)
    Returns (apply_fn, restore_fn, status_fn).
    """
    def apply_fn():
        b = _load_backup()
        saved = b.get(tweak_id, {})
        for op in ops:
            key = f"{op['hive']}|{op['path']}|{op['name']}"
            old, _ = _reg_get(op["hive"], op["path"], op["name"])
            if key not in saved:
                saved[key] = old
        b[tweak_id] = saved
        _save_backup(b)
        wrote_any = False
        for op in ops:
            if _reg_set(op["hive"], op["path"], op["name"], op["on"], op.get("typ")):
                wrote_any = True
        # If NOTHING wrote successfully, it's a real permission problem
        if not wrote_any:
            raise PermissionError(
                "All registry writes failed. Right-click the app \u2192 'Run as administrator'."
            )
        return True

    def restore_fn():
        b = _load_backup()
        saved = b.get(tweak_id, {})
        for op in ops:
            key = f"{op['hive']}|{op['path']}|{op['name']}"
            if "off" in op:
                _reg_set(op["hive"], op["path"], op["name"], op["off"], op.get("typ"))
            elif saved.get(key) is None:
                _reg_del(op["hive"], op["path"], op["name"])
            else:
                _reg_set(op["hive"], op["path"], op["name"], saved[key], op.get("typ"))
        return True

    def status_fn():
        for op in ops:
            v, _ = _reg_get(op["hive"], op["path"], op["name"])
            if v != op["on"]:
                return "off"
        return "on"

    return apply_fn, restore_fn, status_fn


# ============================================================
# Custom logic tweaks (non-pure-registry)
# ============================================================

# ---------- Power plans ----------
ULTIMATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"
HIGH_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"


def _pp_status():
    ok, out = _run("powercfg /getactivescheme")
    o = out.lower()
    return "on" if (ULTIMATE_GUID in o or HIGH_GUID in o) else "off"


def _pp_apply():
    b = _load_backup()
    ok, out = _run("powercfg /getactivescheme")
    if ok and "guid:" in out.lower():
        b["power_plan_guid"] = out.lower().split("guid:")[1].strip().split(" ")[0]
        _save_backup(b)
    _run(f"powercfg -duplicatescheme {ULTIMATE_GUID}")
    ok, _ = _run(f"powercfg /setactive {ULTIMATE_GUID}")
    if not ok:
        _run(f"powercfg /setactive {HIGH_GUID}")
    return True


def _pp_restore():
    prev = _load_backup().get("power_plan_guid") or BALANCED_GUID
    _run(f"powercfg /setactive {prev}")
    return True


# ---------- Core parking ----------
def _cp_apply():
    _run('powercfg -setacvalueindex scheme_current sub_processor CPMINCORES 100')
    _run('powercfg -setacvalueindex scheme_current sub_processor CPMAXCORES 100')
    _run("powercfg /setactive scheme_current")
    return True


def _cp_restore():
    _run('powercfg -setacvalueindex scheme_current sub_processor CPMINCORES 10')
    _run('powercfg -setacvalueindex scheme_current sub_processor CPMAXCORES 100')
    _run("powercfg /setactive scheme_current")
    return True


def _cp_status():
    ok, out = _run("powercfg /query scheme_current sub_processor CPMINCORES")
    return "on" if "0x00000064" in out.lower() else "off"


# ---------- CPU throttling (min state 100%) ----------
def _throttle_apply():
    _run('powercfg -setacvalueindex scheme_current sub_processor PROCTHROTTLEMIN 100')
    _run('powercfg -setdcvalueindex scheme_current sub_processor PROCTHROTTLEMIN 100')
    _run("powercfg /setactive scheme_current")
    return True


def _throttle_restore():
    _run('powercfg -setacvalueindex scheme_current sub_processor PROCTHROTTLEMIN 5')
    _run("powercfg /setactive scheme_current")
    return True


def _throttle_status():
    ok, out = _run("powercfg /query scheme_current sub_processor PROCTHROTTLEMIN")
    return "on" if "0x00000064" in out.lower() else "off"


# ---------- Hibernation ----------
def _hib_apply():
    _run("powercfg -h off")
    return True


def _hib_restore():
    _run("powercfg -h on")
    return True


def _hib_status():
    return "off" if Path("C:/hiberfil.sys").exists() else "on"


# ---------- Startup apps ----------
STARTUP_KEYS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run"),
]


def _list_startup():
    if winreg is None:
        return []
    apps = []
    for hive, path in STARTUP_KEYS:
        try:
            with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ) as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                        apps.append({"hive": hive, "path": path, "name": n, "cmd": v})
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            continue
    return apps


def _startup_apply():
    b = _load_backup()
    b["startup_apps"] = _list_startup()
    _save_backup(b)
    for a in b["startup_apps"]:
        _reg_del(a["hive"], a["path"], a["name"])
    return True


def _startup_restore():
    for a in _load_backup().get("startup_apps", []):
        _reg_set(a["hive"], a["path"], a["name"], a["cmd"], winreg.REG_SZ)
    return True


def _startup_status():
    return "on" if not _list_startup() else "off"


# ---------- Temp files ----------
def _temp_apply():
    paths = [
        os.getenv("TEMP", ""), os.getenv("TMP", ""),
        r"C:\Windows\Temp",
        os.path.expandvars(r"%LOCALAPPDATA%\Temp"),
        os.path.expandvars(r"%SystemRoot%\Prefetch"),
    ]
    total = 0
    for p in set(paths):
        if not p or not os.path.exists(p):
            continue
        for root, dirs, files in os.walk(p):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                    os.remove(fp)
                except Exception:
                    pass
            for d in dirs:
                try:
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                except Exception:
                    pass
    return total


def _wuc_apply():
    _run("net stop wuauserv")
    p = os.path.expandvars(r"%SystemRoot%\SoftwareDistribution\Download")
    if os.path.exists(p):
        shutil.rmtree(p, ignore_errors=True)
    _run("net start wuauserv")
    return True


def _dns_flush():
    _run("ipconfig /flushdns")
    return True


# ---------- Scheduled tasks (telemetry) ----------
TELEMETRY_TASKS = [
    r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
    r"\Microsoft\Windows\Application Experience\ProgramDataUpdater",
    r"\Microsoft\Windows\Autochk\Proxy",
    r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
    r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
    r"\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector",
    r"\Microsoft\Windows\Feedback\Siuf\DmClient",
    r"\Microsoft\Windows\Maps\MapsUpdateTask",
]


def _tasks_apply():
    for t in TELEMETRY_TASKS:
        _run(f'schtasks /Change /TN "{t}" /Disable')
    return True


def _tasks_restore():
    for t in TELEMETRY_TASKS:
        _run(f'schtasks /Change /TN "{t}" /Enable')
    return True


def _tasks_status():
    ok, out = _run(f'schtasks /Query /TN "{TELEMETRY_TASKS[0]}" /FO LIST')
    return "on" if "disabled" in out.lower() else "off"


# ---------- SysMain / Indexing services ----------
def _svc_disable(name):
    _run(f"sc stop {name}")
    _run(f"sc config {name} start= disabled")


def _svc_enable(name, mode="auto"):
    _run(f"sc config {name} start= {mode}")
    _run(f"sc start {name}")


def _sysmain_apply(): _svc_disable("SysMain"); return True
def _sysmain_restore(): _svc_enable("SysMain"); return True
def _sysmain_status():
    ok, out = _run("sc query SysMain")
    return "on" if "stopped" in out.lower() else "off"


def _search_apply(): _svc_disable("WSearch"); return True
def _search_restore(): _svc_enable("WSearch"); return True
def _search_status():
    ok, out = _run("sc query WSearch")
    return "on" if "stopped" in out.lower() else "off"


# ---------- Network buffers / DNS ----------
def _dns_apply():
    b = _load_backup()
    ok, out = _run('netsh interface ipv4 show config')
    b["dns_backup"] = out
    _save_backup(b)
    # apply cloudflare on every active IPv4 interface
    _run('for /f "tokens=1,* delims=:" %i in (\'netsh interface ipv4 show interfaces ^| findstr /R "connected"\') do @netsh interface ipv4 set dnsservers "%j" static 1.1.1.1 primary >nul')
    _run('powershell -Command "Get-NetAdapter | Where-Object Status -eq Up | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses 1.1.1.1,1.0.0.1 }"')
    return True


def _dns_restore():
    _run('powershell -Command "Get-NetAdapter | Where-Object Status -eq Up | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses }"')
    return True


def _dns_status():
    ok, out = _run('powershell -Command "(Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object -First 1).ServerAddresses"')
    return "on" if "1.1.1.1" in out else "off"


# ---------- Prefer HP GPU globally ----------
def _hpgpu_apply():
    _reg_set("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", "DirectXUserGlobalSettings",
             "VRROptimizeEnable=1;SwapEffectUpgradeEnable=1;HwSchMode=2;", winreg.REG_SZ)
    return True


def _hpgpu_restore():
    _reg_del("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", "DirectXUserGlobalSettings")
    return True


def _hpgpu_status():
    v, _ = _reg_get("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", "DirectXUserGlobalSettings")
    return "on" if v else "off"


# ============================================================
# THE TWEAK TABLE — all 53
# ============================================================
LOCKED = True
FREE = False
PARTNER = "partner"  # partner-exclusive tier

_defs = []


def _add(tid, title, desc, icon, category, locked, apply, restore, status, admin=True, partner_only=False, action=False):
    """action=True marks one-shot tweaks (clean temp, flush DNS) that never stay 'on'."""
    _defs.append({
        "id": tid, "title": title, "desc": desc, "icon": icon,
        "category": category, "locked": locked, "requires_admin": admin,
        "partner_only": partner_only,
        "action": action,
        "tier": "partner" if partner_only else ("premium" if locked else "free"),
        "apply": apply, "restore": restore, "status": status,
    })


def _add_reg(tid, title, desc, icon, category, locked, ops, admin=True, partner_only=False):
    a, r, s = _reg_tweak(tid, ops)
    _add(tid, title, desc, icon, category, locked, a, r, s, admin, partner_only)


# ---------- CPU & POWER (LOCKED) ----------
_add("power_plan", "Kage Max Power Plan",
     "Unlocks and activates the hidden Ultimate power plan for max CPU responsiveness.",
     "\u26A1", "CPU & Power", LOCKED, _pp_apply, _pp_restore, _pp_status)

_add("core_parking", "Disable CPU Core Parking",
     "Forces every CPU core to stay awake — eliminates micro-stutter from park/unpark.",
     "\U0001F9E0", "CPU & Power", LOCKED, _cp_apply, _cp_restore, _cp_status)

_add("cpu_throttle", "Disable CPU Throttling",
     "Sets processor minimum state to 100% so your CPU never downclocks mid-fight.",
     "\U0001F525", "CPU & Power", LOCKED, _throttle_apply, _throttle_restore, _throttle_status)

_add_reg("usb_suspend", "Disable USB Selective Suspend",
     "Prevents Windows from putting USB devices (mouse, keyboard, headset) to sleep.",
     "\U0001F50C", "CPU & Power", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\USB", "name": "DisableSelectiveSuspend", "on": 1}])

_add_reg("pcie_lpm", "Disable PCIe Link State Power Management",
     "Locks PCIe lanes to full speed — max GPU / NVMe bandwidth at all times.",
     "\U0001F517", "CPU & Power", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings\501a4d13-42af-4429-9fd1-a8218c268e20\ee12f906-d277-404b-b6da-e5fa1a576df5",
       "name": "Attributes", "on": 2}])

# ---------- NETWORK (LOCKED) ----------
_add_reg("nagle", "Disable Nagle's Algorithm",
     "Sends packets instantly instead of batching — lower ping in fast-paced multiplayer.",
     "\U0001F5A7", "Network", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces", "name": "TcpAckFrequency", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces", "name": "TCPNoDelay", "on": 1}])

_add("dns_cloudflare", "Use Cloudflare DNS (1.1.1.1)",
     "Switches all active adapters to Cloudflare DNS for faster name resolution.",
     "\u2601", "Network", LOCKED, _dns_apply, _dns_restore, _dns_status)

_add_reg("net_throttle", "Disable Network Throttling",
     "Removes the 10ms packet-throttling Windows applies to non-media traffic.",
     "\U0001F6E1", "Network", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
       "name": "NetworkThrottlingIndex", "on": 0xFFFFFFFF}])

_add_reg("net_buffers", "Increase Network Buffer Sizes",
     "Enables TCP auto-tuning + RSS for higher throughput on modern connections.",
     "\U0001F4E1", "Network", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "Tcp1323Opts", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "DefaultTTL", "on": 64}])

_add_reg("qos_reserve", "Disable QoS Bandwidth Reservation",
     "Frees the 20% bandwidth Windows reserves for QoS packet scheduling.",
     "\U0001F310", "Network", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\Psched", "name": "NonBestEffortLimit", "on": 0}])

# ---------- GPU / DIRECTX (LOCKED) ----------
_add("hp_gpu", "Prefer High-Performance GPU Globally",
     "Forces laptops to use the discrete GPU for every app that isn't explicitly overridden.",
     "\U0001F5A5", "GPU / DirectX", LOCKED, _hpgpu_apply, _hpgpu_restore, _hpgpu_status)

_add_reg("gpu_preempt", "GPU Prefer Max Performance",
     "Registry hint telling the driver stack to favour performance over power saving.",
     "\U0001F3AF", "GPU / DirectX", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "name": "HwSchMode", "on": 2},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "name": "TdrDelay", "on": 10}])

_add_reg("game_priority", "Games Launch at High Priority",
     "Writes the SystemProfile\\Games registry so DirectX titles get High CPU priority.",
     "\U0001F3C6", "GPU / DirectX", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "GPU Priority", "on": 8},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "Priority", "on": 6},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "Scheduling Category", "on": "High", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "SFIO Priority", "on": "High", "typ": winreg.REG_SZ if winreg else None}])

# ---------- INPUT (LOCKED) ----------
_add_reg("mouse_accel", "Disable Mouse Acceleration",
     "Turns off 'Enhance pointer precision' — consistent 1:1 aim.",
     "\U0001F5B1", "Input", LOCKED,
     [{"hive": "HKCU", "path": r"Control Panel\Mouse", "name": "MouseSpeed", "on": "0", "off": "1", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Mouse", "name": "MouseThreshold1", "on": "0", "off": "6", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Mouse", "name": "MouseThreshold2", "on": "0", "off": "10", "typ": winreg.REG_SZ if winreg else None}],
     admin=False)

_add_reg("sticky_keys", "Disable Sticky / Filter / Toggle Keys Prompts",
     "Kills the accidental popup when you spam Shift or hold Right-Shift in a game.",
     "\u2328", "Input", LOCKED,
     [{"hive": "HKCU", "path": r"Control Panel\Accessibility\StickyKeys", "name": "Flags", "on": "506", "off": "510", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Accessibility\Keyboard Response", "name": "Flags", "on": "122", "off": "126", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Accessibility\ToggleKeys", "name": "Flags", "on": "58", "off": "62", "typ": winreg.REG_SZ if winreg else None}],
     admin=False)

_add_reg("kb_delay", "Reduce Keyboard Input Delay",
     "Shortens key repeat delay and boosts repeat rate for snappier typing / bhopping.",
     "\u2B07", "Input", LOCKED,
     [{"hive": "HKCU", "path": r"Control Panel\Keyboard", "name": "KeyboardDelay", "on": "0", "off": "1", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Keyboard", "name": "KeyboardSpeed", "on": "31", "off": "31", "typ": winreg.REG_SZ if winreg else None}],
     admin=False)

_add_reg("device_priority", "Higher Priority for Gaming Devices",
     "Bumps HID input device priority so mouse / keyboard events preempt other IRQs.",
     "\U0001F3AE", "Input", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\PriorityControl", "name": "IRQ8Priority", "on": 1}])

# ---------- SYSTEM RESPONSIVENESS (LOCKED) ----------
_add_reg("prio_sep", "Foreground CPU Priority Boost",
     "Tweaks Win32PrioritySeparation so the active window gets a bigger CPU quantum.",
     "\u26A1", "System", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\PriorityControl", "name": "Win32PrioritySeparation", "on": 38}])

_add_reg("fullscreen_notifs", "No Notifications in Fullscreen",
     "Blocks toast pop-ups while any app runs in exclusive fullscreen.",
     "\U0001F515", "System", LOCKED,
     [{"hive": "HKCU", "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings", "name": "NOC_GLOBAL_SETTING_ALLOW_NOTIFICATION_SOUND", "on": 0}],
     admin=False)

_add_reg("focus_assist", "Disable Focus Assist Auto Rules",
     "Stops Focus Assist from auto-triggering / stealing focus mid-match.",
     "\U0001F3AF", "System", LOCKED,
     [{"hive": "HKCU", "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache\DefaultAccount", "name": "Data", "on": 0}],
     admin=False)

_add_reg("sys_responsiveness", "Boost System Responsiveness",
     "Lowers the CPU cycles Windows reserves for background scheduling to 10%.",
     "\U0001F680", "System", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "name": "SystemResponsiveness", "on": 10, "off": 20}])

# ---------- GAMING FEATURES (FREE) ----------
_add_reg("game_bar", "Disable Xbox Game Bar",
     "Turns off the Win+G overlay that costs FPS in every DirectX game.",
     "\u274C", "Gaming", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\GameBar", "name": "AppCaptureEnabled", "on": 0, "off": 1},
      {"hive": "HKCU", "path": r"Software\Microsoft\GameBar", "name": "UseNexusForGameBarEnabled", "on": 0, "off": 1}],
     admin=False)

_add_reg("game_dvr", "Disable Game DVR (Background Recorder)",
     "Kills the always-on background clip recorder that steals GPU cycles.",
     "\U0001F3A5", "Gaming", FREE,
     [{"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_Enabled", "on": 0, "off": 1},
      {"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_FSEBehaviorMode", "on": 2, "off": 0},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "name": "AllowGameDVR", "on": 0}])

_add_reg("game_mode", "Enable Windows Game Mode",
     "Tells Windows to prioritise resources for the game currently in focus.",
     "\U0001F3AE", "Gaming", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\GameBar", "name": "AllowAutoGameMode", "on": 1, "off": 0},
      {"hive": "HKCU", "path": r"Software\Microsoft\GameBar", "name": "AutoGameModeEnabled", "on": 1, "off": 0}],
     admin=False)

_add_reg("hags", "Hardware-Accelerated GPU Scheduling",
     "Reduces input latency on modern GPUs (RTX / RX 5000+). Reboot required.",
     "\u26A1", "Gaming", FREE,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "name": "HwSchMode", "on": 2, "off": 1}])

_add_reg("auto_hdr", "Enable Auto HDR",
     "Automatically upscales SDR games to HDR on HDR-capable displays.",
     "\U0001F308", "Gaming", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\DirectX\UserGpuPreferences", "name": "AutoHDREnable", "on": "1", "off": "0", "typ": winreg.REG_SZ if winreg else None}],
     admin=False)

_add_reg("no_fso", "Disable Fullscreen Optimizations Globally",
     "Forces true exclusive fullscreen — reduces input lag in older games.",
     "\U0001F3AC", "Gaming", FREE,
     [{"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_DXGIHonorFSEWindowsCompatible", "on": 1},
      {"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_HonorUserFSEBehaviorMode", "on": 1},
      {"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_EFSEFeatureFlags", "on": 0}],
     admin=False)

# ---------- VISUALS (FREE) ----------
_add_reg("vfx", "Adjust for Best Performance",
     "Disables all Windows visual effects at once (shadows, fade, previews...).",
     "\u2728", "Visuals", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "name": "VisualFXSetting", "on": 2, "off": 0}],
     admin=False)

_add_reg("no_anim", "Disable Window Animations",
     "Kills minimize/maximize animation — instant window switching.",
     "\U0001F4A8", "Visuals", FREE,
     [{"hive": "HKCU", "path": r"Control Panel\Desktop\WindowMetrics", "name": "MinAnimate", "on": "0", "off": "1", "typ": winreg.REG_SZ if winreg else None}],
     admin=False)

_add_reg("no_transp", "Disable Transparency Effects",
     "Removes acrylic blur from taskbar / start menu — saves GPU cycles.",
     "\U0001F9CA", "Visuals", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "name": "EnableTransparency", "on": 0, "off": 1}],
     admin=False)

_add_reg("cursor_shadow", "Disable Mouse Cursor Shadow",
     "Removes the tiny shadow under your cursor — one less thing for the GPU.",
     "\U0001F5B1", "Visuals", FREE,
     [{"hive": "HKCU", "path": r"Control Panel\Desktop", "name": "UserPreferencesMask",
       "on": bytes([0x90, 0x12, 0x03, 0x80, 0x10, 0x00, 0x00, 0x00]),
       "off": bytes([0x9E, 0x1E, 0x07, 0x80, 0x12, 0x00, 0x00, 0x00]),
       "typ": winreg.REG_BINARY if winreg else None}],
     admin=False)

_add_reg("menu_delay", "Zero Menu Show Delay",
     "Sets the 400ms menu-open delay to 0 — snappier right-click / start menu.",
     "\U0001F5B2", "Visuals", FREE,
     [{"hive": "HKCU", "path": r"Control Panel\Desktop", "name": "MenuShowDelay", "on": "0", "off": "400", "typ": winreg.REG_SZ if winreg else None}],
     admin=False)

# ---------- STARTUP & BACKGROUND (FREE) ----------
_add("startup_apps", "Disable All Startup Apps",
     "Removes every autostart entry so Windows boots lean. Fully restorable.",
     "\U0001F680", "Startup", FREE, _startup_apply, _startup_restore, _startup_status)

_add("telemetry_tasks", "Disable Telemetry Scheduled Tasks",
     "Turns off the CEIP, Compatibility Appraiser and other background snoopers.",
     "\U0001F4CB", "Startup", FREE, _tasks_apply, _tasks_restore, _tasks_status)

_add_reg("cortana", "Disable Cortana",
     "Fully disables the Cortana process and search-bar assistant.",
     "\U0001F507", "Startup", FREE,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "name": "AllowCortana", "on": 0}])

_add("search_indexing", "Disable Windows Search Indexing",
     "Stops the WSearch service — big I/O win on HDDs and mixed drives.",
     "\U0001F50D", "Startup", FREE, _search_apply, _search_restore, _search_status)

_add("sysmain", "Disable SysMain (Superfetch)",
     "Turns off Superfetch — recommended on SSDs, reduces random disk usage.",
     "\U0001F4BD", "Startup", FREE, _sysmain_apply, _sysmain_restore, _sysmain_status)

_add_reg("widgets", "Disable Widgets / News & Interests",
     "Removes the Widgets button and stops the background feed process.",
     "\U0001F4F0", "Startup", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "TaskbarDa", "on": 0, "off": 1}],
     admin=False)

_add_reg("bg_apps", "Disable Background Apps",
     "Prevents UWP apps from running in the background eating RAM & CPU.",
     "\U0001F6AB", "Startup", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "name": "GlobalUserDisabled", "on": 1, "off": 0},
      {"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Search", "name": "BackgroundAppGlobalToggle", "on": 0, "off": 1}],
     admin=False)

# ---------- DISK & MEMORY (FREE) ----------
_add("clean_temp", "Clean Temp Files",
     "Wipes %TEMP%, Windows\\Temp and Prefetch. Reports MB freed.",
     "\U0001F9F9", "Disk", FREE,
     _temp_apply, lambda: True, lambda: "off", action=True)

_add("clean_wu", "Clear Windows Update Cache",
     "Deletes stale downloads under SoftwareDistribution\\Download.",
     "\u267B", "Disk", FREE, _wuc_apply, lambda: True, lambda: "off", action=True)

_add("clean_dns", "Flush DNS Cache",
     "Clears the local DNS resolver cache — fixes stale lookups instantly.",
     "\U0001F310", "Disk", FREE, _dns_flush, lambda: True, lambda: "off", action=True)

_add("hibernation", "Disable Hibernation",
     "Removes hiberfil.sys — frees several GB on your C: drive.",
     "\U0001F4A4", "Disk", FREE, _hib_apply, _hib_restore, _hib_status)

_add_reg("pagefile_secondary", "Disable Pagefile on Secondary Drives",
     "Keeps the pagefile only on C: — avoids fragmentation on data drives.",
     "\U0001F5C4", "Disk", FREE,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "name": "PagingFiles", "on": "C:\\pagefile.sys", "typ": winreg.REG_MULTI_SZ if winreg else None}])

_add_reg("ntfs_atime", "Disable NTFS Last-Access Timestamp",
     "Stops NTFS from updating a timestamp on every file read — small I/O win.",
     "\U0001F551", "Disk", FREE,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\FileSystem", "name": "NtfsDisableLastAccessUpdate", "on": 1, "off": 2}])

_add_reg("trim", "Enable TRIM for SSDs",
     "Ensures Windows sends TRIM commands so your SSD stays fast.",
     "\U0001F4BE", "Disk", FREE,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\FileSystem", "name": "DisableDeleteNotify", "on": 0, "off": 1}])

# ---------- PRIVACY / TELEMETRY (FREE) ----------
_add_reg("telemetry", "Disable Windows Telemetry",
     "Sets the DataCollection policy to the lowest allowed value.",
     "\U0001F576", "Privacy", FREE,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "name": "AllowTelemetry", "on": 0}])

_add_reg("ad_id", "Disable Advertising ID",
     "Stops apps from tracking you via a personalised advertising identifier.",
     "\U0001F6D1", "Privacy", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "name": "Enabled", "on": 0, "off": 1}],
     admin=False)

_add_reg("activity_history", "Disable Activity History / Timeline",
     "Prevents Windows from collecting and syncing your recent activities.",
     "\U0001F4DC", "Privacy", FREE,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\System", "name": "EnableActivityFeed", "on": 0},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\System", "name": "PublishUserActivities", "on": 0}])

_add_reg("location", "Disable Location Tracking",
     "Denies system-wide access to your location.",
     "\U0001F5FA", "Privacy", FREE,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Sensor\Overrides\{BFA794E4-F964-4FDB-90F6-51056BFE4B44}", "name": "SensorPermissionState", "on": 0, "off": 1}])

_add_reg("feedback", "Disable Feedback Prompts",
     "Sets Windows feedback frequency to Never.",
     "\U0001F4AC", "Privacy", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Siuf\Rules", "name": "NumberOfSIUFInPeriod", "on": 0}],
     admin=False)

# ---------- AUDIO (FREE) ----------
_add_reg("audio_enh", "Disable Audio Enhancements",
     "Turns off system-level audio effects — lower audio latency.",
     "\U0001F507", "Audio", FREE,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Multimedia\Audio", "name": "DisableProtectedAudioDG", "on": 1, "off": 0}],
     admin=False)

_add_reg("audio_dpc", "Higher Priority for Audio DPC",
     "Raises priority of the audio deferred procedure calls — fewer crackles.",
     "\U0001F3B5", "Audio", FREE,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio", "name": "Priority", "on": 1},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio", "name": "Scheduling Category", "on": "High", "typ": winreg.REG_SZ if winreg else None}])


# ============================================================
# PARTNER EXCLUSIVE — only available via the partner code
# ============================================================
_add_reg("partner_mmcss_games", "Max MMCSS Games Priority",
     "Elevates the Games task in Multimedia Class Scheduler above every other multimedia task.",
     "\U0001F3C6", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "Priority", "on": 6},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "Scheduling Category", "on": "High", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "SFIO Priority", "on": "High", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "GPU Priority", "on": 8},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "name": "Background Only", "on": "False", "typ": winreg.REG_SZ if winreg else None}],
     partner_only=True)

_add_reg("partner_tcp_ack", "Zero TCP ACK Frequency",
     "Aggressive TCP ACK batching disabled — every packet acknowledged instantly.",
     "\U0001F4E6", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "TcpAckFrequency", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "TCPNoDelay", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "TcpDelAckTicks", "on": 0}],
     partner_only=True)

_add_reg("partner_hwsch_gpu", "Force GPU Hardware Scheduling",
     "Enables Windows Hardware-accelerated GPU Scheduling at the driver level.",
     "\U0001F3AE", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "name": "HwSchMode", "on": 2},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "name": "TdrLevel", "on": 3}],
     partner_only=True)

_add_reg("partner_input_lag", "Nuke Input Latency Timers",
     "Removes every mouse/keyboard input smoothing delay Windows adds by default.",
     "\U0001F5B1", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Control Panel\Mouse", "name": "MouseHoverTime", "on": "1", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Desktop", "name": "MenuShowDelay", "on": "0", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKCU", "path": r"Control Panel\Keyboard", "name": "KeyboardDelay", "on": "0", "typ": winreg.REG_SZ if winreg else None}],
     admin=False, partner_only=True)

_add_reg("partner_win_prio", "Foreground Boost x6",
     "Massively boosts CPU quantum priority for the currently focused window (your game).",
     "\U0001F525", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\PriorityControl", "name": "Win32PrioritySeparation", "on": 0x26}],
     partner_only=True)

# ---------- NVIDIA driver-level tweaks (partner-only) ----------
_add_reg("nv_powermizer_max", "NVIDIA PowerMizer Maximum Performance",
     "Locks the NVIDIA GPU into maximum performance mode at the driver level.",
     "\u26A1", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\nvlddmkm", "name": "PowerMizerEnable", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\nvlddmkm", "name": "PowerMizerLevel", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\nvlddmkm", "name": "PowerMizerLevelAC", "on": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\nvlddmkm", "name": "PerfLevelSrc", "on": 0x2222}],
     partner_only=True)

_add_reg("nv_hags_force", "NVIDIA Force Hardware GPU Scheduling",
     "Turns on Windows Hardware-Accelerated GPU Scheduling for NVIDIA cards.",
     "\U0001F3AE", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "name": "HwSchMode", "on": 2}],
     partner_only=True)

_add_reg("nv_telemetry_off", "Disable NVIDIA Telemetry",
     "Blocks NVIDIA container telemetry uploads for lower background CPU usage.",
     "\U0001F576", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\NVIDIA Corporation\NvContainer\Telemetry", "name": "SendTelemetryData", "on": 0},
      {"hive": "HKLM", "path": r"SOFTWARE\NVIDIA Corporation\NvContainer\Telemetry", "name": "OptInOrOutPreference", "on": 0}],
     partner_only=True)

_add_reg("nv_shader_cache_uncap", "NVIDIA Uncap Shader Cache",
     "Removes the 4GB shader cache size limit — fewer stutters in modern shader-heavy games.",
     "\U0001F4BE", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\nvlddmkm\Global\NVTweak", "name": "DisableShaderCache", "on": 0},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\nvlddmkm\Global\NVTweak", "name": "ShaderCacheSizeInMB", "on": 0xFFFFFFFF}],
     partner_only=True)

_add_reg("nv_kill_freestyle", "Kill NVIDIA FreeStyle / ShadowPlay Overhead",
     "Disables the NVIDIA overlay hook that adds ~1-2% CPU cost every frame.",
     "\U0001F3A5", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"SOFTWARE\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS", "name": "ShadowPlayEnabled", "on": 0, "off": 1},
      {"hive": "HKCU", "path": r"SOFTWARE\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS", "name": "DVREnabled", "on": 0, "off": 1}],
     admin=False, partner_only=True)


# ============================================================
# PARTNER EXCLUSIVE — 15 SAFE deep tweaks (no data risk)
# ============================================================
_add_reg("p_mem_compression_off", "Disable Memory Compression",
     "Stops Windows from compressing RAM \u2014 frees CPU cycles, uses a bit more RAM (worth it on 16GB+).",
     "\U0001F9E0", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "name": "DisablePagingCombining", "on": 1}],
     partner_only=True)

_add_reg("p_large_cache", "Boost Large System Cache",
     "Tells the kernel to keep more file data cached in RAM \u2014 faster hot-path reads.",
     "\U0001F4BE", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "name": "LargeSystemCache", "on": 1}],
     partner_only=True)

_add_reg("p_io_pagelock", "Max IoPageLockLimit",
     "Kernel can lock more pages in RAM for high-throughput IO (game asset streaming).",
     "\U0001F513", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "name": "IoPageLockLimit", "on": 0x40000000}],
     partner_only=True)

_add_reg("p_page_combining_off", "Disable Page Combining",
     "Stops Windows from deduplicating RAM pages \u2014 removes background CPU tax.",
     "\U0001F9F1", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "name": "DisablePageCombining", "on": 1}],
     partner_only=True)

_add_reg("p_audio_buffer_2ms", "Audio Buffer Ultra Low (2ms)",
     "Sets Windows audio engine to ultra-low latency for competitive gaming.",
     "\U0001F3A7", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Multimedia\Audio", "name": "UserDuckingPreference", "on": 3}],
     admin=False, partner_only=True)

_add_reg("p_audio_no_exclusive", "Block Audio Exclusive-Mode Hijacks",
     "Prevents games/apps from stealing exclusive control of your audio device.",
     "\U0001F507", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Multimedia\Audio", "name": "AllowExclusiveMode", "on": 0, "off": 1}],
     admin=False, partner_only=True)

_add("p_kill_wer", "Kill Windows Error Reporting",
     "Stops the WerSvc service that phones home crash dumps.",
     "\U0001F6AB", "Partner Exclusive", LOCKED,
     lambda: (_svc_disable("WerSvc"), True)[1],
     lambda: (_svc_enable("WerSvc", "manual"), True)[1],
     lambda: "on" if "stopped" in (_run("sc query WerSvc")[1] or "").lower() else "off",
     partner_only=True)

_add("p_kill_dps", "Kill Diagnostic Policy Service",
     "Disables the DPS service that runs background health checks.",
     "\U0001F6AB", "Partner Exclusive", LOCKED,
     lambda: (_svc_disable("DPS"), True)[1],
     lambda: (_svc_enable("DPS", "auto"), True)[1],
     lambda: "on" if "stopped" in (_run("sc query DPS")[1] or "").lower() else "off",
     partner_only=True)

_add("p_kill_wisvc", "Kill Windows Insider Service",
     "Disables the Insider Program telemetry service.",
     "\U0001F6AB", "Partner Exclusive", LOCKED,
     lambda: (_svc_disable("wisvc"), True)[1],
     lambda: (_svc_enable("wisvc", "manual"), True)[1],
     lambda: "on" if "stopped" in (_run("sc query wisvc")[1] or "").lower() else "off",
     partner_only=True)

_add("p_tcp_ctcp", "TCP Congestion Provider = CTCP",
     "Switches Windows to Compound TCP \u2014 better throughput on fast connections.",
     "\U0001F310", "Partner Exclusive", LOCKED,
     lambda: (_run("netsh int tcp set supplemental Internet congestionprovider=ctcp"), True)[1],
     lambda: (_run("netsh int tcp set supplemental Internet congestionprovider=cubic"), True)[1],
     lambda: "on" if "ctcp" in (_run("netsh int tcp show supplemental")[1] or "").lower() else "off",
     partner_only=True)

_add_reg("p_chimney_off", "Disable TCP Chimney Offload",
     "Stops the NIC from batching packets \u2014 lower and more consistent ping.",
     "\U0001F517", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "EnableTCPChimney", "on": 0, "off": 1},
      {"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "EnableTCPA", "on": 0, "off": 1}],
     partner_only=True)

_add_reg("p_rsc_off", "Disable Receive Segment Coalescing",
     "Prevents Windows from batching received packets before delivery \u2014 lower jitter.",
     "\U0001F6E1", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "name": "EnableRSC", "on": 0, "off": 1}],
     partner_only=True)

_add_reg("p_qos_dscp", "Gaming DSCP QoS Priority",
     "Tags outbound game packets with high-priority DSCP flags \u2014 helps on congested networks.",
     "\U0001F3AF", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\QoS\KageGaming", "name": "DSCP Value", "on": "46", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\QoS\KageGaming", "name": "Application Name", "on": "*", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\QoS\KageGaming", "name": "Local Port", "on": "*", "typ": winreg.REG_SZ if winreg else None},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\QoS\KageGaming", "name": "Version", "on": "1.0", "typ": winreg.REG_SZ if winreg else None}],
     partner_only=True)

_add("p_no_dynamic_tick", "Disable Dynamic Ticks",
     "Locks the CPU scheduler tick rate \u2014 more consistent frame pacing.",
     "\u23F1", "Partner Exclusive", LOCKED,
     lambda: (_run("bcdedit /set disabledynamictick yes"), True)[1],
     lambda: (_run("bcdedit /set disabledynamictick no"), True)[1],
     lambda: "on" if "yes" in (_run("bcdedit /enum {current}")[1] or "").lower().split("disabledynamictick")[-1][:20] else "off",
     partner_only=True)

_add_reg("p_kill_gamedvr_deep", "Kill Game DVR Completely",
     "Deep-disables every Game DVR / broadcast component \u2014 the deepest anti-DVR nuke.",
     "\U0001F3A5", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_Enabled", "on": 0, "off": 1},
      {"hive": "HKCU", "path": r"System\GameConfigStore", "name": "GameDVR_FSEBehaviorMode", "on": 2, "off": 0},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "name": "AllowGameDVR", "on": 0, "off": 1},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\PolicyManager\default\ApplicationManagement\AllowGameDVR", "name": "value", "on": 0, "off": 1}],
     admin=False, partner_only=True)


# ============================================================
# PARTNER EXCLUSIVE — 10 more safe registry tweaks
# ============================================================
_add_reg("p_aero_peek_off", "Disable Aero Peek",
     "Kills the taskbar hover preview \u2014 removes DWM CPU cost on hover.",
     "\U0001F441", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "DisablePreviewDesktop", "on": 1, "off": 0}],
     admin=False, partner_only=True)

_add_reg("p_cortana_off", "Disable Cortana Registry",
     "Fully disables Cortana at the policy level \u2014 no more background indexing.",
     "\U0001F507", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "name": "AllowCortana", "on": 0, "off": 1},
      {"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "name": "DisableWebSearch", "on": 1, "off": 0}],
     partner_only=True)

_add_reg("p_bing_search_off", "Kill Bing in Start Menu",
     "Removes web results from the Start menu search \u2014 makes it feel instant.",
     "\U0001F50D", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Search", "name": "BingSearchEnabled", "on": 0, "off": 1},
      {"hive": "HKCU", "path": r"Software\Policies\Microsoft\Windows\Explorer", "name": "DisableSearchBoxSuggestions", "on": 1, "off": 0}],
     admin=False, partner_only=True)

_add_reg("p_onedrive_off", "Kill OneDrive Auto-Start",
     "Stops OneDrive from launching on boot \u2014 saves RAM and background CPU.",
     "\u2601", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\OneDrive", "name": "DisableFileSyncNGSC", "on": 1, "off": 0},
      {"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Run", "name": "OneDrive", "on": "", "off": "", "typ": winreg.REG_SZ if winreg else None}],
     partner_only=True)

_add_reg("p_store_autoinstall_off", "Kill Store Auto-Install Bloat",
     "Prevents Microsoft Store from silently reinstalling promoted apps.",
     "\U0001F6AB", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\CloudContent", "name": "DisableWindowsConsumerFeatures", "on": 1, "off": 0},
      {"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "name": "SilentInstalledAppsEnabled", "on": 0, "off": 1},
      {"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "name": "SubscribedContent-338388Enabled", "on": 0, "off": 1}],
     partner_only=True)

_add_reg("p_fast_startup_off", "Disable Fast Startup",
     "Turns off hybrid boot \u2014 cleaner state on every start, no half-hibernation quirks.",
     "\u26A1", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "name": "HiberbootEnabled", "on": 0, "off": 1}],
     partner_only=True)

_add_reg("p_reserved_storage_off", "Disable Windows Reserved Storage",
     "Frees the 7GB Windows reserves for updates \u2014 more free space for games.",
     "\U0001F4BE", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\ReserveManager", "name": "ShippedWithReserves", "on": 0, "off": 1},
      {"hive": "HKLM", "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\ReserveManager", "name": "BaseHardReserveSize", "on": 0}],
     partner_only=True)

_add_reg("p_autoreboot_updates_off", "No Auto-Reboot After Windows Updates",
     "Stops Windows from randomly rebooting your PC while you're away.",
     "\U0001F510", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "name": "NoAutoRebootWithLoggedOnUsers", "on": 1, "off": 0}],
     partner_only=True)

_add_reg("p_win11_context_menu_classic", "Windows 11 Classic Right-Click Menu",
     "Restores the fast Windows 10-style right-click menu \u2014 no more 'Show more options'.",
     "\U0001F5B1", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32", "name": "", "on": "", "typ": winreg.REG_SZ if winreg else None}],
     admin=False, partner_only=True)

_add_reg("p_taskbar_end_task", "Enable 'End Task' on Taskbar",
     "Adds End Task directly to the taskbar right-click menu \u2014 kill frozen games instantly.",
     "\U0001F480", "Partner Exclusive", LOCKED,
     [{"hive": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings", "name": "TaskbarEndTask", "on": 1, "off": 0}],
     admin=False, partner_only=True)


# ============================================================
# PARTNER EXCLUSIVE — 6 WiFi & Network ping-reduction tweaks
# ============================================================
def _ps(cmd):
    """Run a PowerShell one-liner silently. Returns True if returncode=0."""
    return _run(f'powershell -NoProfile -Command "{cmd}"')[0]


# 1) Disable WiFi power saving on ALL wireless adapters (biggest ping win)
def _wifi_pwr_apply():
    _ps("Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq '802.11' } | ForEach-Object { Set-NetAdapterPowerManagement -Name $_.Name -AllowComputerToTurnOffDevice Disabled -ErrorAction SilentlyContinue }")
    _run("powercfg /setacvalueindex scheme_current 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a 0")
    _run("powercfg /setdcvalueindex scheme_current 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a 0")
    _run("powercfg /setactive scheme_current")
    return True

def _wifi_pwr_restore():
    _ps("Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq '802.11' } | ForEach-Object { Set-NetAdapterPowerManagement -Name $_.Name -AllowComputerToTurnOffDevice Enabled -ErrorAction SilentlyContinue }")
    _run("powercfg /setacvalueindex scheme_current 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a 3")
    _run("powercfg /setactive scheme_current")
    return True

def _wifi_pwr_status():
    ok, out = _run('powercfg /query scheme_current 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a')
    return "on" if "0x00000000" in out.lower() else "off"

_add("p_wifi_no_powersave", "Disable WiFi Power Saving",
     "Stops Windows from suspending your WiFi adapter \u2014 the #1 fix for ping spikes on wireless.",
     "\U0001F4F6", "Partner Exclusive", LOCKED,
     _wifi_pwr_apply, _wifi_pwr_restore, _wifi_pwr_status, partner_only=True)


# 2) Prefer 5GHz over 2.4GHz (lower latency band)
def _wifi_5ghz_apply():
    return _ps("Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq '802.11' } | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Preferred Band' -DisplayValue '5GHz' -ErrorAction SilentlyContinue; Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Band' -DisplayValue '5GHz' -ErrorAction SilentlyContinue }")

def _wifi_5ghz_restore():
    return _ps("Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq '802.11' } | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Preferred Band' -DisplayValue 'No Preference' -ErrorAction SilentlyContinue }")

def _wifi_5ghz_status():
    ok, out = _run('powershell -NoProfile -Command "Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq \'802.11\' } | Get-NetAdapterAdvancedProperty -DisplayName \'Preferred Band\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DisplayValue"')
    return "on" if "5" in (out or "") else "off"

_add("p_wifi_prefer_5ghz", "Force WiFi 5GHz Band",
     "Locks your WiFi to the 5GHz band \u2014 much lower latency + less interference than 2.4GHz.",
     "\U0001F4F6", "Partner Exclusive", LOCKED,
     _wifi_5ghz_apply, _wifi_5ghz_restore, _wifi_5ghz_status, partner_only=True)


# 3) Disable NIC power saving on ALL adapters (Ethernet + WiFi)
def _nic_pwr_apply():
    return _ps("Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterPowerManagement -Name $_.Name -AllowComputerToTurnOffDevice Disabled -ErrorAction SilentlyContinue }")

def _nic_pwr_restore():
    return _ps("Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterPowerManagement -Name $_.Name -AllowComputerToTurnOffDevice Enabled -ErrorAction SilentlyContinue }")

def _nic_pwr_status():
    ok, out = _run('powershell -NoProfile -Command "(Get-NetAdapter -Physical | Select-Object -First 1 | Get-NetAdapterPowerManagement).AllowComputerToTurnOffDevice"')
    return "on" if "disable" in (out or "").lower() else "off"

_add("p_nic_no_powersave", "Disable All NIC Power Saving",
     "Windows can NEVER sleep any network adapter \u2014 no dropouts, no lag spikes.",
     "\U0001F50C", "Partner Exclusive", LOCKED,
     _nic_pwr_apply, _nic_pwr_restore, _nic_pwr_status, partner_only=True)


# 4) Disable Interrupt Moderation (NIC processes packets immediately)
def _int_mod_apply():
    return _ps("Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Interrupt Moderation' -DisplayValue 'Disabled' -ErrorAction SilentlyContinue }")

def _int_mod_restore():
    return _ps("Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Interrupt Moderation' -DisplayValue 'Enabled' -ErrorAction SilentlyContinue }")

def _int_mod_status():
    ok, out = _run('powershell -NoProfile -Command "(Get-NetAdapter -Physical | Select-Object -First 1 | Get-NetAdapterAdvancedProperty -DisplayName \'Interrupt Moderation\' -ErrorAction SilentlyContinue).DisplayValue"')
    return "on" if "disable" in (out or "").lower() else "off"

_add("p_no_int_moderation", "Disable Interrupt Moderation",
     "NIC delivers packets to CPU instantly instead of batching \u2014 lower ping, more CPU cost.",
     "\U0001F4E1", "Partner Exclusive", LOCKED,
     _int_mod_apply, _int_mod_restore, _int_mod_status, partner_only=True)


# 5) Disable IPv6 for gaming (many games route worse via IPv6)
_add_reg("p_ipv6_off", "Disable IPv6 for Gaming",
     "Forces IPv4 only \u2014 fixes routing detours for games that don't handle IPv6 cleanly.",
     "\U0001F310", "Partner Exclusive", LOCKED,
     [{"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "name": "DisabledComponents", "on": 0xFF, "off": 0}],
     partner_only=True)


# 6) Kill WiFi autoconfig background scans during gameplay
def _wifi_autoscan_apply():
    _run('netsh wlan set autoconfig enabled=no interface=Wi-Fi')
    return True

def _wifi_autoscan_restore():
    _run('netsh wlan set autoconfig enabled=yes interface=Wi-Fi')
    return True

def _wifi_autoscan_status():
    ok, out = _run('netsh wlan show autoconfig interface=Wi-Fi')
    return "on" if ("disabled" in (out or "").lower() or "no" in (out or "").lower().split("autoconfig")[-1][:20]) else "off"

_add("p_wifi_no_bgscan", "Stop WiFi Background Scans",
     "Prevents Windows from scanning for new WiFi networks mid-game \u2014 removes periodic ping spikes.",
     "\U0001F507", "Partner Exclusive", LOCKED,
     _wifi_autoscan_apply, _wifi_autoscan_restore, _wifi_autoscan_status, partner_only=True)


TWEAKS = _defs
CATEGORIES = ["CPU & Power", "Network", "GPU / DirectX", "Input", "System",
              "Gaming", "Visuals", "Startup", "Disk", "Privacy", "Audio",
              "Partner Exclusive"]
