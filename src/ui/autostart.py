# src/ui/autostart.py
"""Register or remove the app from the current user's Windows startup programs."""

import os
import sys
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "FLCLFileOrganizer"


def launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"))
    return f'"{sys.executable}" "{app_path}"'


def set_autostart(enabled):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass
