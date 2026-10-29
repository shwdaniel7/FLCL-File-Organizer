# src/ui/pages/reports.py
"""Report page: summary metrics, animated category charts, history and exports."""

import tkinter as tk

import customtkinter

from ...organizer import _format_size
from .. import anim, theme
from ..anim import ease_out_cubic
from ..widgets import StatCard, card, make_button, scaling

CHART_ITEMS = 6


def _clamp01(value):
    return max(0.0, min(1.0, value))


def _short(text, limit):
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ReportsPage(customtkinter.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.report = None
        self._p = 0.0
        p = theme.current
        self.grid_columnconfigure((0, 1), weight=1, uniform="charts")
        self.grid_rowconfigure(2, weight=1)

        cards = customtkinter.CTkFrame(self, fg_color="transparent")
        cards.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.cards = {}
        specs = [
            ("organized", "Files organized", p["accent"], str),
            ("categories", "Categories", p["accent_alt"], str),
            ("errors", "Errors", p["error"], str),
            ("space", "Space organized", p["highlight"], _format_size),
        ]
        for index, (key, label, color, formatter) in enumerate(specs):
            cards.grid_columnconfigure(index, weight=1, uniform="report_cards")
            stat = StatCard(cards, label, color, formatter)
            stat.grid(row=0, column=index, sticky="nsew", padx=(0, 10) if index < len(specs) - 1 else 0)
            self.cards[key] = stat

        self.bars = self._chart_card(0, "TOP CATEGORIES")
        self.donut = self._chart_card(1, "SPACE BY CATEGORY")

        history = card(self)
        history.grid(row=2, column=0, columnspan=2, sticky="nsew")
        history.grid_columnconfigure(0, weight=1)
        history.grid_rowconfigure(1, weight=1)
        customtkinter.CTkLabel(history, text="RECENT OPERATIONS", font=theme.font("label"), text_color=p["muted"], anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=(14, 6))
        actions = customtkinter.CTkFrame(history, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=14, pady=(12, 6))
        make_button(actions, "CSV", lambda: app.export_report("csv", self.report), variant="ghost", width=72, height=30, tooltip="Export the report as CSV.").pack(side="left", padx=(0, 6))
        make_button(actions, "HTML", lambda: app.export_report("html", self.report), variant="ghost", width=72, height=30, tooltip="Export a styled HTML page.").pack(side="left", padx=(0, 6))
        make_button(actions, "REFRESH", self.refresh, variant="ghost", width=96, height=30).pack(side="left")
        self.history_box = customtkinter.CTkTextbox(history, font=theme.font("small"), wrap="word", fg_color=p["panel"], height=120)
        self.history_box.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        for tag, color in (("time", p["accent_alt"]), ("muted", p["muted"]), ("error", p["error"]), ("head", p["text"])):
            self.history_box.tag_config(tag, foreground=color)

    def _chart_card(self, column, title):
        p = theme.current
        frame = card(self)
        frame.grid(row=1, column=column, sticky="nsew", padx=(0, 7) if column == 0 else (7, 0), pady=(0, 14))
        customtkinter.CTkLabel(frame, text=title, font=theme.font("label"), text_color=p["muted"], anchor="w").pack(fill="x", padx=20, pady=(14, 0))
        canvas = tk.Canvas(frame, height=round(200 * scaling(self)), bg=p["panel"], highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True, padx=16, pady=(4, 14))
        canvas.bind("<Configure>", lambda _e: self._draw_charts())
        return canvas

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.report = self.app.build_report()
        report = self.report
        self.cards["organized"].set(report["organized_files"])
        self.cards["categories"].set(len(report["popular_categories"]))
        self.cards["errors"].set(len(report["errors"]))
        self.cards["space"].set(sum(item["size_bytes"] for item in report["space_by_category"]))
        self._render_history()

        def step(t):
            self._p = t
            self._draw_charts()

        anim.animator.animate((self, "charts"), 900, step, easing=lambda t: t)

    def _render_history(self):
        report = self.report
        box = self.history_box
        box.configure(state="normal")
        box.delete("1.0", "end")
        if not report["recent_history"]:
            box.insert("end", "No organization runs recorded yet. Press Start on the Organize page to create one.", "muted")
        for entry in report["recent_history"]:
            stamp = (entry.get("timestamp") or "unknown").replace("T", "  ")[:20]
            box.insert("end", f"{stamp}   ", "time")
            box.insert("end", f"{entry.get('count', 0)} file(s)", "head")
            files = ", ".join(entry.get("files", []))
            box.insert("end", f"   {files}\n" if files else "\n", "muted")
        if report["errors"]:
            box.insert("end", "\nERRORS\n", "head")
            for error in report["errors"][:10]:
                box.insert("end", f"{error}\n", "error")
        box.configure(state="disabled")

    def _draw_charts(self):
        if self.report is None:
            return
        self._draw_bars(self.bars)
        self._draw_donut(self.donut)

    def _draw_bars(self, canvas):
        p = theme.current
        s = scaling(self)
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        top = self.report["popular_categories"][:CHART_ITEMS]
        if not top:
            canvas.create_text(width / 2, height / 2, text="No categorised files yet.", fill=p["muted"], font=("Segoe UI", 10))
            return
        max_count = max(item["count"] for item in top) or 1
        label_w, count_w, bar_h = 110 * s, 48 * s, 10 * s
        row_h = min(34 * s, (height - 8 * s) / len(top))
        track_start, track_end = label_w + bar_h / 2, width - count_w - bar_h / 2
        for index, item in enumerate(top):
            y = 4 * s + row_h * index + row_h / 2
            local = ease_out_cubic(_clamp01(self._p * 1.6 - index * 0.1))
            canvas.create_text(0, y, text=_short(item["name"], 14), anchor="w", fill=p["text"], font=("Segoe UI", 10))
            canvas.create_line(track_start, y, track_end, y, width=bar_h, capstyle="round", fill=p["surface"])
            end = track_start + (track_end - track_start) * item["count"] / max_count * local
            canvas.create_line(track_start, y, max(track_start + 0.1, end), y, width=bar_h, capstyle="round", fill=theme.series_color(p, index))
            canvas.create_text(width, y, text=str(round(item["count"] * local)), anchor="e", fill=p["muted"], font=("Segoe UI Semibold", 10))

    def _draw_donut(self, canvas):
        p = theme.current
        s = scaling(self)
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        items = [item for item in self.report["space_by_category"] if item["size_bytes"] > 0]
        total = sum(item["size_bytes"] for item in items)
        if not total:
            canvas.create_text(width / 2, height / 2, text="No files measured yet.", fill=p["muted"], font=("Segoe UI", 10))
            return
        if len(items) > CHART_ITEMS:
            rest = sum(item["size_bytes"] for item in items[CHART_ITEMS - 1:])
            items = items[: CHART_ITEMS - 1] + [{"name": "Other", "size_bytes": rest, "size_human": _format_size(rest)}]
        thickness = 18 * s
        diameter = max(40 * s, min(height - 8 * s, width * 0.45))
        x0, y0 = thickness / 2 + 2 * s, (height - diameter) / 2
        box = (x0, y0, x0 + diameter, y0 + diameter)
        canvas.create_oval(*box, outline=p["surface"], width=thickness)
        sweep = ease_out_cubic(_clamp01(self._p * 1.2))
        start = 90.0
        for index, item in enumerate(items):
            extent = -360 * item["size_bytes"] / total * sweep
            gap = 2 if abs(extent) > 6 else 0
            if abs(extent) > 0.5:
                canvas.create_arc(*box, start=start - gap / 2, extent=extent + gap, style="arc", outline=theme.series_color(p, index), width=thickness)
            start += extent
        cx, cy = x0 + diameter / 2, y0 + diameter / 2
        canvas.create_text(cx, cy - 8 * s, text=_format_size(int(total * sweep)), fill=p["text"], font=theme.font("label"))
        canvas.create_text(cx, cy + 10 * s, text="total", fill=p["muted"], font=("Segoe UI", 9))
        legend_x = x0 + diameter + thickness + 14 * s
        row_h = min(26 * s, height / max(len(items), 1))
        legend_y = (height - row_h * len(items)) / 2 + row_h / 2
        for index, item in enumerate(items):
            y = legend_y + index * row_h
            fade = _clamp01(self._p * 2 - index * 0.15)
            color = anim.lerp_color(p["panel"], theme.series_color(p, index), fade)
            canvas.create_oval(legend_x, y - 4 * s, legend_x + 8 * s, y + 4 * s, fill=color, outline="")
            canvas.create_text(legend_x + 16 * s, y, text=_short(item["name"], 14), anchor="w", fill=anim.lerp_color(p["panel"], p["text"], fade), font=("Segoe UI", 10))
            canvas.create_text(width - 2 * s, y, text=item["size_human"], anchor="e", fill=anim.lerp_color(p["panel"], p["muted"], fade), font=("Segoe UI", 9))
