"""
tools/pc_control.py
────────────────────
Handles all PC-level actions:
  - Opening apps / websites
  - Permission gate (always ask before acting)
  - System info (CPU, RAM, disk)
  - Screenshot for problem detection

IMPORTANT: Every sensitive action goes through request_permission() first.
"""

import os
import sys
import json
import subprocess
import webbrowser
import psutil
import pyautogui
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

# Load settings
_settings_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
with open(_settings_path, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

APPS     = SETTINGS.get("apps", {})
WEBSITES = SETTINGS.get("websites", {})
REQUIRE_PERMISSION = SETTINGS.get("require_permission", True)


# ── Permission Gate ───────────────────────────────────────────────────────────

def request_permission(action_description: str) -> bool:
    """
    Show a popup asking the user to approve/deny an action.
    Returns True if approved, False if denied.
    If REQUIRE_PERMISSION is False in settings, auto-approve.
    """
    if not REQUIRE_PERMISSION:
        return True

    # We need a hidden root window to show the dialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    result = messagebox.askyesno(
        title="⚡ REVIA — Permission Required",
        message=f"REVIA wants to:\n\n  ➤ {action_description}\n\nDo you allow this?",
        parent=root
    )
    root.destroy()
    return result


# ── App / Website Launcher ────────────────────────────────────────────────────

def open_app(app_name: str, skip_permission: bool = False) -> str:
    """Open a desktop application by name."""
    name = app_name.lower().strip()
    app_path = APPS.get(name)

    if app_path is None:
        return f"❌ App '{app_name}' not found in settings. Add it to config/settings.json."

    if not skip_permission and not request_permission(f"Open {app_name}"):
        return "🚫 Action cancelled by user."

    try:
        subprocess.Popen(app_path, shell=True)
        return f"✅ Opened {app_name}."
    except Exception as e:
        return f"❌ Failed to open {app_name}: {e}"


def open_website(site_name: str, custom_url: str = None, skip_permission: bool = False) -> str:
    """Open a website by nickname or custom URL."""
    name = site_name.lower().strip()
    url  = custom_url or WEBSITES.get(name)

    if url is None:
        # Try treating it as a raw URL
        if site_name.startswith("http"):
            url = site_name
        else:
            url = f"https://www.google.com/search?q={site_name}"

    if not skip_permission and not request_permission(f"Open {url} in your browser"):
        return "🚫 Action cancelled by user."

    webbrowser.open(url)
    return f"✅ Opened {url}."


# ── System Information ────────────────────────────────────────────────────────

def get_system_info() -> str:
    """Return a human-readable summary of PC health."""
    cpu_pct  = psutil.cpu_percent(interval=1)
    ram      = psutil.virtual_memory()
    disk     = psutil.disk_usage("/")

    lines = [
        "🖥️  System Status:",
        f"  CPU usage:    {cpu_pct}%",
        f"  RAM used:     {ram.percent}% ({ram.used // (1024**3):.1f} GB / {ram.total // (1024**3):.1f} GB)",
        f"  Disk used:    {disk.percent}% ({disk.used // (1024**3):.1f} GB / {disk.total // (1024**3):.1f} GB free: {disk.free // (1024**3):.1f} GB)",
    ]

    # Warnings
    if cpu_pct > 85:
        lines.append("  ⚠️  CPU is very high!")
    if ram.percent > 85:
        lines.append("  ⚠️  RAM is almost full!")
    if disk.percent > 90:
        lines.append("  ⚠️  Disk is almost full!")

    return "\n".join(lines)


def list_running_processes(top_n: int = 10) -> str:
    """List top N processes by CPU usage."""
    procs = []
    for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except Exception:
            pass

    procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
    lines = [f"🔄 Top {top_n} processes by CPU:"]
    for p in procs[:top_n]:
        lines.append(f"  {p['name']:30s} CPU: {p['cpu_percent']:5.1f}%  RAM: {p['memory_percent']:.1f}%")
    return "\n".join(lines)


# ── Screenshot ────────────────────────────────────────────────────────────────

def take_screenshot() -> str:
    """
    Take a screenshot and save it to config/last_screenshot.png.
    Returns the file path.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "config", "last_screenshot.png")
    img  = pyautogui.screenshot()
    img.save(path)
    return os.path.abspath(path)
