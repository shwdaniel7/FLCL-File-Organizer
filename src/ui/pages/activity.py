# src/ui/pages/activity.py
"""Live status, run counters and the color-coded activity log."""

import customtkinter

from .. import anim, theme
from ..anim import lerp, lerp_color
from ..widgets import StatCard, StatusDot, card, make_button


def log_kind(message):
    """Classify an organizer log line for coloring."""
    if message.startswith(("File moved:", "Restored:")):
        return "moved"
    if message.startswith("ERROR"):
        return "error"
    if "SKIPPED" in message or message.startswith("Nothing to undo"):
        return "warn"
    if message.startswith(("FOLDER", "Real-time", "Initial scan complete", "Undo complete", "Monitoring")):
        return "accent"
    return "info"


class ActivityPage(customtkinter.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._progress_shown = 0.0
        p = theme.current
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        status = card(self)
        status.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        status.grid_columnconfigure(1, weight=1)
        self.dot = StatusDot(status, bg=p["panel"], size=26)
        self.dot.grid(row=0, column=0, rowspan=2, padx=(20, 14), pady=18)
        self.state_label = customtkinter.CTkLabel(status, text="", font=theme.font("title"), anchor="w")
        self.state_label.grid(row=0, column=1, sticky="sw", pady=(16, 0))
        self.hint_label = customtkinter.CTkLabel(status, text="", font=theme.font("body"), text_color=p["muted"], anchor="w")
        self.hint_label.grid(row=1, column=1, sticky="nw", pady=(0, 14))
        self.progress_label = customtkinter.CTkLabel(status, text="", font=theme.font("label"), text_color=p["muted"], anchor="e")
        self.progress_label.grid(row=0, column=2, rowspan=2, sticky="e", padx=20)
        self.progress = customtkinter.CTkProgressBar(status, height=8, corner_radius=4)
        self.progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 18))
        self.progress.set(0)

        counters = customtkinter.CTkFrame(self, fg_color="transparent")
        counters.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.counters = {}
        for index, (key, label, color) in enumerate([("moved", "Files moved", p["success"]), ("skipped", "Skipped", p["warning"]), ("errors", "Errors", p["error"])]):
            counters.grid_columnconfigure(index, weight=1, uniform="counters")
            stat = StatCard(counters, label, color)
            stat.grid(row=0, column=index, sticky="nsew", padx=(0, 10) if index < 2 else 0)
            self.counters[key] = stat

        log_card = card(self)
        log_card.grid(row=2, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        customtkinter.CTkLabel(log_card, text="ACTIVITY LOG", font=theme.font("label"), text_color=p["muted"], anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=(14, 6))
        make_button(log_card, "CLEAR", app.clear_log, variant="ghost", width=90, height=30, tooltip="Clear the activity log.").grid(row=0, column=1, padx=14, pady=(12, 6))
        self.log_box = customtkinter.CTkTextbox(log_card, font=theme.font("mono"), wrap="word", fg_color=p["panel"], text_color=p["text"], activate_scrollbars=True)
        self.log_box.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        for tag, color in (("time", lerp_color(p["muted"], p["panel"], 0.35)), ("info", p["muted"]), ("moved", p["success"]), ("error", p["error"]), ("warn", p["warning"]), ("accent", p["accent"])):
            self.log_box.tag_config(tag, foreground=color)
        self.log_box.configure(state="disabled")
        for entry in app.log_lines:
            self.append(entry, scroll=False)
        self.log_box.see("end")

        self.render_state()
        self.render_counts(animate=False)

    def append(self, entry, scroll=True):
        stamp, kind, message = entry
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{stamp}  ", "time")
        self.log_box.insert("end", f"{message}\n", kind)
        if scroll:
            self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def render_state(self):
        app = self.app
        color, pulsing = app.state_color()
        self.dot.set(color, pulsing)
        self.state_label.configure(text=app.state.upper(), text_color=color)
        self.hint_label.configure(text=app.hint)
        self.progress.configure(progress_color=color)
        done, total = app.progress
        if app.state == "Scanning" and total:
            self.progress_label.configure(text=f"{done} / {total}")
            target = done / total
        elif app.state in ("Monitoring", "Paused"):
            self.progress_label.configure(text="")
            target = 1.0
        else:
            self.progress_label.configure(text="")
            target = 0.0
        start = self._progress_shown

        def step(t):
            self._progress_shown = lerp(start, target, t)
            self.progress.set(self._progress_shown)

        anim.animator.animate((self, "progress"), theme.MOTION["base"], step)

    def render_counts(self, animate=True):
        self.counters["moved"].set(self.app.moved_count, animate)
        self.counters["skipped"].set(self.app.skipped_count, animate)
        self.counters["errors"].set(self.app.error_count, animate)
