# src/ui/tray.py
"""System tray icon used when 'Minimize to tray' is on."""

import threading

from PIL import Image

from ..organizer import resource_path

try:
    import pystray
except ImportError:
    pystray = None


class TrayIcon:
    def __init__(self, root, on_exit):
        self.root = root
        self.on_exit = on_exit
        self.icon = None

    @property
    def available(self):
        return pystray is not None

    def hide_window(self):
        """Withdraw the window into the tray; pystray callbacks hop back to the Tk thread via after()."""
        self.root.withdraw()
        if self.icon:
            return
        image = Image.open(resource_path("assets/icon.png"))
        menu = pystray.Menu(
            pystray.MenuItem("Restore", lambda icon, item: self.root.after(0, self.root.deiconify), default=True),
            pystray.MenuItem("Exit", lambda icon, item: self.root.after(0, self.on_exit)),
        )
        self.icon = pystray.Icon("FLCL File Organizer", image, "FLCL File Organizer", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        if self.icon:
            self.icon.stop()
            self.icon = None
