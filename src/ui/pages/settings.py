# src/ui/pages/settings.py
"""Preferences: behavior switches, theme picker, motion and keyboard shortcuts."""

import customtkinter

from .. import theme
from ..widgets import card, hover_fade, set_hover_colors

SHORTCUTS = [
    ("Ctrl+O", "Choose folder"),
    ("F5 / Ctrl+P", "Refresh preview"),
    ("Ctrl+R", "Start organizing"),
    ("Ctrl+S", "Stop monitoring"),
    ("Ctrl+F", "Search the preview"),
    ("Ctrl+1 … 5", "Switch page"),
    ("Space", "Toggle selected rows"),
    ("Esc", "Clear search / close dialog"),
]


class SettingsPage(customtkinter.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._theme_cards = {}
        p = theme.current
        self.grid_columnconfigure((0, 1), weight=1, uniform="settings")

        behavior = self._section(0, 0, "BEHAVIOR")
        self._switch(behavior, "Include subfolders", "Organize files inside nested folders too. The preview refreshes.", app.recursive_var, "recursive")
        self._switch(behavior, "Notifications", "Windows notifications for files organized while monitoring.", app.notify_var, "notify")
        self._switch(behavior, "Start with Windows", "Launch at sign-in and resume the last folder.", app.autostart_var, "autostart")
        self._switch(behavior, "Minimize to tray", "Closing the window keeps monitoring in the tray.", app.tray_var, "minimize_to_tray", last=True)

        appearance = self._section(0, 1, "APPEARANCE")
        picker = customtkinter.CTkFrame(appearance, fg_color="transparent")
        picker.pack(fill="x", padx=18, pady=(4, 8))
        picker.grid_columnconfigure((0, 1), weight=1, uniform="themes")
        for index, name in enumerate(theme.PALETTES):
            self._theme_card(picker, index, name)
        self._paint_theme_cards()
        motion_hint = "Windows animation effects are off, so motion is already reduced." if app.system_reduce_motion else "Turns off transitions, pulses and the animated GIF."
        self._switch(appearance, "Reduce motion", motion_hint, app.reduce_motion_var, "reduce_motion", last=True)

        shortcuts = self._section(1, 0, "KEYBOARD SHORTCUTS", columnspan=2)
        grid = customtkinter.CTkFrame(shortcuts, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(4, 16))
        grid.grid_columnconfigure((1, 3), weight=1)
        for index, (keys, action) in enumerate(SHORTCUTS):
            row, column = index // 2, (index % 2) * 2
            customtkinter.CTkLabel(grid, text=keys, font=theme.font("small"), text_color=p["accent"], fg_color=p["surface"], corner_radius=6, height=26, width=110).grid(row=row, column=column, sticky="w", pady=4, padx=(0, 12))
            customtkinter.CTkLabel(grid, text=action, font=theme.font("body"), text_color=p["text"], anchor="w").grid(row=row, column=column + 1, sticky="w", pady=4)

    def _section(self, row, column, title, columnspan=1):
        p = theme.current
        frame = card(self)
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=(0, 7) if column == 0 and columnspan == 1 else (7, 0) if columnspan == 1 else 0, pady=(0, 14))
        customtkinter.CTkLabel(frame, text=title, font=theme.font("label"), text_color=p["muted"], anchor="w").pack(fill="x", padx=18, pady=(16, 6))
        return frame

    def _switch(self, parent, title, description, variable, key, last=False):
        p = theme.current
        row = customtkinter.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(6, 16 if last else 6))
        text = customtkinter.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        customtkinter.CTkLabel(text, text=title, font=theme.font("body_bold"), text_color=p["text"], anchor="w").pack(fill="x")
        customtkinter.CTkLabel(text, text=description, font=theme.font("small"), text_color=p["muted"], anchor="w", justify="left", wraplength=320).pack(fill="x")
        customtkinter.CTkSwitch(row, text="", variable=variable, width=46, switch_width=42, switch_height=22, command=lambda: self.app.on_preference_changed(key)).pack(side="right")

    def _theme_card(self, parent, index, name):
        p = theme.current
        swatch = theme.palette(name)
        frame = customtkinter.CTkFrame(parent, fg_color=swatch["window"], border_width=2, border_color=p["border"], corner_radius=theme.RADIUS["md"], height=96)
        frame.grid(row=0, column=index, sticky="nsew", padx=(0, 6) if index == 0 else (6, 0))
        frame.pack_propagate(False)
        dots = customtkinter.CTkFrame(frame, fg_color="transparent")
        dots.pack(anchor="w", padx=14, pady=(14, 8))
        for key in ("accent", "accent_alt", "highlight", "success", "surface"):
            customtkinter.CTkFrame(dots, width=16, height=16, corner_radius=8, fg_color=swatch[key], border_width=1, border_color=swatch["border"]).pack(side="left", padx=(0, 5))
        label = customtkinter.CTkLabel(frame, text=name.upper(), font=theme.font("button"), text_color=swatch["text"], anchor="w")
        label.pack(fill="x", padx=14)
        for widget in (frame, dots, label):
            widget.bind("<Button-1>", lambda _e, n=name: self.app.set_theme(n))
        hover_fade(frame, p["border"], swatch["accent"], prop="border_color")
        self._theme_cards[name] = frame

    def _paint_theme_cards(self):
        p = theme.current
        for name, frame in self._theme_cards.items():
            active = name == self.app.theme_name
            accent = theme.palette(name)["accent"]
            set_hover_colors(frame, accent if active else p["border"], accent)
