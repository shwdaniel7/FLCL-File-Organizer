# src/ui/widgets.py
"""Reusable animated widgets built on CustomTkinter and the shared animator."""

import math
import tkinter as tk

import customtkinter

from . import anim, theme
from .anim import ease_out_back, ease_out_cubic, lerp, lerp_color, linear
from ..organizer import resource_path


def scaling(widget):
    return customtkinter.ScalingTracker.get_widget_scaling(widget)


def _raw_bind(widget, sequence, callback):
    # Bind on the Tk frame itself: Enter/Leave then ignore moves between the CTk canvas and its child labels.
    tk.Misc.bind(widget, sequence, callback, "+")


def hover_fade(widget, base, hover, prop="fg_color"):
    """Fade ``prop`` between ``base`` and ``hover`` on pointer enter/leave."""
    widget._hover = {"base": base, "hover": hover, "color": base, "inside": False, "prop": prop}

    def go(inside):
        state = widget._hover
        state["inside"] = inside
        try:
            disabled = str(widget.cget("state")) == "disabled"
        except ValueError:
            disabled = False
        target = state["hover"] if inside and not disabled else state["base"]
        start = state["color"]

        def step(t):
            state["color"] = lerp_color(start, target, t)
            widget.configure(**{state["prop"]: state["color"]})

        anim.animator.animate((widget, "hover"), theme.MOTION["fast"], step)

    _raw_bind(widget, "<Enter>", lambda _e: go(True))
    _raw_bind(widget, "<Leave>", lambda _e: go(False))


def set_hover_colors(widget, base, hover):
    """Change a hover_fade widget's resting/hover colors and apply them immediately."""
    state = widget._hover
    state["base"], state["hover"] = base, hover
    state["color"] = hover if state["inside"] else base
    anim.animator.cancel((widget, "hover"))
    widget.configure(**{state["prop"]: state["color"]})


def button_colors(variant, bg=None):
    p = theme.current
    return {
        "primary": (p["accent"], p["accent_soft"], p["on_accent"]),
        "ghost": (p["surface"], p["raised"], p["text"]),
        "danger": (p["surface"], p["raised"], p["error"]),
        "subtle": (bg or p["panel"], p["raised"], p["muted"]),
    }[variant]


def make_button(parent, text, command, variant="primary", tooltip=None, font_role="button", bg=None, **kwargs):
    p = theme.current
    base, hover, text_color = button_colors(variant, bg)
    kwargs.setdefault("height", 40)
    if variant in ("ghost", "danger"):
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", p["border"])
    button = customtkinter.CTkButton(
        parent, text=text, command=command, font=theme.font(font_role), fg_color=base,
        hover=False, text_color=text_color, text_color_disabled=p["muted"], **kwargs,
    )
    hover_fade(button, base, hover)
    if tooltip:
        Tooltip(button, tooltip)
    return button


def icon_button(parent, icon, command, tooltip=None, bg=None, size=34, color=None):
    button = make_button(
        parent, theme.ICONS[icon], command, variant="subtle", tooltip=tooltip, font_role="icon",
        bg=bg, width=size, height=size, corner_radius=theme.RADIUS["sm"],
    )
    if color:
        button.configure(text_color=color)
    return button


def card(parent, **kwargs):
    p = theme.current
    kwargs.setdefault("fg_color", p["panel"])
    kwargs.setdefault("border_color", p["border"])
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("corner_radius", theme.RADIUS["lg"])
    return customtkinter.CTkFrame(parent, **kwargs)


class Tooltip:
    DELAY_MS = 450

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self._job = None
        _raw_bind(widget, "<Enter>", self._schedule)
        _raw_bind(widget, "<Leave>", self._hide)
        _raw_bind(widget, "<ButtonPress>", self._hide)

    def _schedule(self, _event=None):
        self._cancel()
        self._job = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _show(self):
        self._job = None
        if self.window or not self.text:
            return
        p = theme.current
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        self.window.wm_attributes("-alpha", 0.0)
        border = tk.Frame(self.window, bg=p["border"], padx=1, pady=1)
        border.pack()
        tk.Label(border, text=self.text, bg=p["raised"], fg=p["text"], padx=10, pady=5, font=("Segoe UI", 10), justify="left", wraplength=360).pack()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window.wm_geometry(f"+{x}+{y}")
        window = self.window
        anim.animator.animate((self, "fade"), theme.MOTION["fast"], lambda t: window.wm_attributes("-alpha", 0.97 * t))

    def _hide(self, _event=None):
        self._cancel()
        anim.animator.cancel((self, "fade"))
        if self.window:
            self.window.destroy()
            self.window = None


class StatCard(customtkinter.CTkFrame):
    """Metric tile whose number counts up to each new value."""

    def __init__(self, master, label, color, formatter=str, tooltip=None):
        p = theme.current
        super().__init__(master, fg_color=p["panel"], border_color=p["border"], border_width=1, corner_radius=theme.RADIUS["lg"])
        self._formatter = formatter
        self._value = 0
        self._shown = 0
        header = customtkinter.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 0))
        customtkinter.CTkFrame(header, width=8, height=8, corner_radius=4, fg_color=color).pack(side="left", padx=(0, 8))
        customtkinter.CTkLabel(header, text=label.upper(), font=theme.font("label"), text_color=p["muted"], anchor="w").pack(side="left", fill="x")
        self.value_label = customtkinter.CTkLabel(self, text=formatter(0), font=theme.font("number"), text_color=color, anchor="w")
        self.value_label.pack(fill="x", padx=14, pady=(2, 12))
        if tooltip:
            Tooltip(self, tooltip)

    def set(self, value, animate=True):
        self._value = value
        start = self._shown
        if not animate or start == value:
            anim.animator.cancel((self, "count"))
            self._render(value)
            return

        def step(t):
            self._render(round(lerp(start, value, t)))

        anim.animator.animate((self, "count"), theme.MOTION["slow"], step)

    def _render(self, value):
        self._shown = value
        self.value_label.configure(text=self._formatter(value))


class StatusDot(tk.Canvas):
    """A state light; a ring ripples outward while the state is active."""

    def __init__(self, master, bg, size=16):
        self._px = round(size * scaling(master))
        super().__init__(master, width=self._px, height=self._px, bg=bg, highlightthickness=0, bd=0)
        self._bg = bg
        self._color = bg
        center = self._px / 2
        self._ring = self.create_oval(center, center, center, center, outline=bg, width=max(1, round(self._px / 10)))
        r = self._px * 0.22
        self._dot = self.create_oval(center - r, center - r, center + r, center + r, fill=bg, outline="")

    def set(self, color, pulsing):
        self._color = color
        self.itemconfigure(self._dot, fill=color)
        if pulsing:
            anim.animator.animate((self, "pulse"), theme.MOTION["pulse"], self._pulse, easing=linear, loop=True)
        else:
            anim.animator.cancel((self, "pulse"))
            self._pulse(0.0)

    def _pulse(self, t):
        center = self._px / 2
        radius = lerp(self._px * 0.22, self._px * 0.48, ease_out_cubic(t))
        self.coords(self._ring, center - radius, center - radius, center + radius, center + radius)
        self.itemconfigure(self._ring, outline=lerp_color(self._color, self._bg, t) if t > 0 else self._bg)


class ToastManager:
    """Stacked, auto-dismissing notifications that slide in from the bottom-right corner."""

    WIDTH = 330
    MARGIN = 18
    GAP = 10
    MAX = 4

    def __init__(self, root):
        self.root = root
        self.toasts = []

    def show(self, message, kind="info", duration=3800):
        p = theme.current
        color = {"info": p["accent_alt"], "success": p["success"], "warning": p["warning"], "error": p["error"]}[kind]
        frame = customtkinter.CTkFrame(self.root, fg_color=p["raised"], border_color=p["border"], border_width=1, corner_radius=theme.RADIUS["md"], width=self.WIDTH)
        customtkinter.CTkFrame(frame, width=4, height=8, corner_radius=2, fg_color=color).pack(side="left", fill="y", padx=(10, 0), pady=10)
        icon = customtkinter.CTkLabel(frame, text=theme.ICONS[kind if kind != "success" else "check"], font=theme.font("icon"), text_color=color, width=20)
        icon.pack(side="left", padx=(10, 0))
        label = customtkinter.CTkLabel(frame, text=message, font=theme.font("small"), text_color=p["text"], wraplength=self.WIDTH - 80, justify="left", anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(10, 14), pady=12)
        toast = {"frame": frame, "x": self.WIDTH + 40, "y": -self.MARGIN, "alive": True}
        for widget in (frame, icon, label):
            widget.bind("<Button-1>", lambda _e, t=toast: self.dismiss(t))
        frame.place(relx=1.0, rely=1.0, anchor="se", x=toast["x"], y=toast["y"])
        frame.lift()
        self.toasts.append(toast)
        while len(self.toasts) > self.MAX:
            self.dismiss(self.toasts[0])
        self._restack()
        start = toast["x"]

        def slide_in(t):
            toast["x"] = lerp(start, -self.MARGIN, t)
            frame.place(x=toast["x"])

        anim.animator.animate((frame, "x"), theme.MOTION["slow"], slide_in, easing=ease_out_back)
        self.root.after(duration, lambda: self.dismiss(toast))

    def dismiss(self, toast):
        if not toast["alive"]:
            return
        toast["alive"] = False
        self.toasts.remove(toast)
        frame = toast["frame"]
        start = toast["x"]

        def slide_out(t):
            frame.place(x=lerp(start, self.WIDTH + 40, t))

        anim.animator.animate((frame, "x"), theme.MOTION["base"], slide_out, on_done=frame.destroy)
        self._restack()

    def _restack(self):
        offset = self.MARGIN
        factor = scaling(self.root)
        for toast in reversed(self.toasts):
            frame = toast["frame"]
            frame.update_idletasks()
            target = -offset
            offset += frame.winfo_reqheight() / factor + self.GAP
            start = toast["y"]
            if start == target:
                continue

            def move(t, toast=toast, start=start, target=target):
                toast["y"] = lerp(start, target, t)
                toast["frame"].place(y=toast["y"])

            anim.animator.animate((frame, "y"), theme.MOTION["base"], move)
            frame.lift()


class ChipGrid(customtkinter.CTkFrame):
    """Removable pill chips laid out in equal columns that adapt to the available width."""

    CHIP_WIDTH = 108

    def __init__(self, master, on_remove, bg, empty_text="Nothing here yet."):
        super().__init__(master, fg_color=bg, corner_radius=0)
        self._bg = bg
        self._on_remove = on_remove
        self._empty_text = empty_text
        self._chips = []
        self._columns = 0
        tk.Misc.bind(self, "<Configure>", lambda _e: self._layout(), "+")

    def set_items(self, items, color):
        p = theme.current
        for chip in self._chips:
            chip.destroy()
        self._chips = []
        self._columns = 0
        if not items:
            label = customtkinter.CTkLabel(self, text=self._empty_text, font=theme.font("small"), text_color=p["muted"])
            self._chips.append(label)
        for item in items:
            chip = customtkinter.CTkFrame(self, fg_color=p["surface"], border_color=p["border"], border_width=1, corner_radius=theme.RADIUS["pill"], height=28)
            customtkinter.CTkFrame(chip, width=6, height=6, corner_radius=3, fg_color=color).pack(side="left", padx=(10, 6))
            customtkinter.CTkLabel(chip, text=item, font=theme.font("small"), text_color=p["text"], height=24).pack(side="left")
            remove = customtkinter.CTkButton(
                chip, text=theme.ICONS["close"], font=customtkinter.CTkFont(family="Segoe MDL2 Assets", size=8),
                width=20, height=20, corner_radius=10, fg_color=p["surface"], hover=False, text_color=p["muted"],
                command=lambda value=item: self._on_remove(value),
            )
            remove.pack(side="left", padx=(4, 5), pady=3)
            hover_fade(remove, p["surface"], p["error"])
            self._chips.append(chip)
        self._layout()

    def _layout(self):
        width = self.winfo_width() / scaling(self)
        columns = max(1, int(width // (self.CHIP_WIDTH + 6))) if width > 10 else 4
        if columns == self._columns:
            return
        self._columns = columns
        for index in range(12):
            self.grid_columnconfigure(index, weight=0, uniform="" if index >= columns else "chips")
        for index, chip in enumerate(self._chips):
            chip.grid(row=index // columns, column=index % columns, sticky="w", padx=3, pady=3)


class SidebarNav(customtkinter.CTkFrame):
    """Vertical navigation with an accent bar that glides to the active item."""

    ROW_HEIGHT = 44

    def __init__(self, master, items, on_select, bg):
        super().__init__(master, fg_color=bg, corner_radius=0)
        p = theme.current
        self._bg = bg
        self._on_select = on_select
        self._rows = {}
        self._active = None
        self._indicator_y = 0
        for key, icon, label, hint in items:
            row = customtkinter.CTkFrame(self, fg_color=bg, corner_radius=theme.RADIUS["md"], height=self.ROW_HEIGHT)
            row.pack(fill="x", padx=(12, 12), pady=2)
            row.pack_propagate(False)
            icon_label = customtkinter.CTkLabel(row, text=theme.ICONS[icon], font=theme.font("icon"), text_color=p["muted"], width=24)
            icon_label.pack(side="left", padx=(14, 12))
            text_label = customtkinter.CTkLabel(row, text=label.upper(), font=theme.font("label"), text_color=p["muted"], anchor="w")
            text_label.pack(side="left", fill="x", expand=True)
            for widget in (row, icon_label, text_label):
                widget.bind("<Button-1>", lambda _e, k=key: self._on_select(k))
            hover_fade(row, bg, p["surface"])
            Tooltip(row, hint)
            self._rows[key] = {"row": row, "icon": icon_label, "text": text_label}
        self._indicator = customtkinter.CTkFrame(self, width=4, height=22, corner_radius=2, fg_color=p["accent"])
        tk.Misc.bind(self, "<Configure>", lambda _e: self._place_indicator(animate=False), "+")

    def select(self, key, animate=True):
        p = theme.current
        self._active = key
        for row_key, parts in self._rows.items():
            active = row_key == key
            set_hover_colors(parts["row"], p["raised"] if active else self._bg, p["raised"] if active else p["surface"])
            parts["icon"].configure(text_color=p["accent"] if active else p["muted"])
            parts["text"].configure(text_color=p["text"] if active else p["muted"])
        self.after_idle(lambda: self._place_indicator(animate))

    def set_collapsed(self, collapsed):
        for parts in self._rows.values():
            if collapsed:
                parts["text"].pack_forget()
            elif not parts["text"].winfo_manager():
                parts["text"].pack(side="left", fill="x", expand=True)

    def _place_indicator(self, animate):
        if self._active is None:
            return
        row = self._rows[self._active]["row"]
        if row.winfo_height() <= 1:  # not laid out yet
            self.after(30, lambda: self._place_indicator(animate))
            return
        factor = scaling(self)
        target = (row.winfo_y() + row.winfo_height() / 2) / factor - 11
        if not self._indicator.winfo_ismapped():
            self._indicator_y = target
            self._indicator.place(x=2, y=target)
            return
        start = self._indicator_y

        def step(t):
            self._indicator_y = lerp(start, target, t)
            self._indicator.place(y=self._indicator_y)

        anim.animator.animate((self, "indicator"), theme.MOTION["base"] if animate else 0, step, easing=ease_out_back)


def confirm(root, title, message, confirm_text="Confirm", icon="info"):
    """Modal yes/no dialog styled like the app. Returns True when confirmed."""
    p = theme.current
    dialog = customtkinter.CTkToplevel(root)
    dialog.withdraw()
    dialog.title(title)
    dialog.transient(root)
    dialog.resizable(False, False)
    dialog.configure(fg_color=p["window"])
    _set_icon(dialog)
    result = {"ok": False}

    body = card(dialog, fg_color=p["panel"])
    body.pack(fill="both", expand=True, padx=12, pady=12)
    header = customtkinter.CTkFrame(body, fg_color="transparent")
    header.pack(fill="x", padx=20, pady=(18, 6))
    customtkinter.CTkLabel(header, text=theme.ICONS[icon], font=theme.font("icon_lg"), text_color=p["accent"]).pack(side="left", padx=(0, 12))
    customtkinter.CTkLabel(header, text=title.upper(), font=theme.font("title"), text_color=p["text"], anchor="w").pack(side="left", fill="x")
    customtkinter.CTkLabel(body, text=message, font=theme.font("body"), text_color=p["muted"], justify="left", anchor="w", wraplength=420).pack(fill="x", padx=20, pady=(4, 18))
    buttons = customtkinter.CTkFrame(body, fg_color="transparent")
    buttons.pack(fill="x", padx=20, pady=(0, 18))

    def close(ok):
        result["ok"] = ok
        dialog.grab_release()
        dialog.destroy()

    make_button(buttons, confirm_text, lambda: close(True), width=150).pack(side="right")
    make_button(buttons, "Cancel", lambda: close(False), variant="ghost", width=110).pack(side="right", padx=(0, 10))
    dialog.bind("<Escape>", lambda _e: close(False))
    dialog.bind("<Return>", lambda _e: close(True))
    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))

    dialog.update_idletasks()
    width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
    x = root.winfo_rootx() + (root.winfo_width() - width) // 2
    y = root.winfo_rooty() + (root.winfo_height() - height) // 3
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    dialog.attributes("-alpha", 0.0)
    dialog.deiconify()
    dialog.wait_visibility()
    dialog.grab_set()
    dialog.focus_force()
    anim.animator.animate((dialog, "fade"), theme.MOTION["base"], lambda t: dialog.attributes("-alpha", t))
    root.wait_window(dialog)
    return result["ok"]


def _set_icon(window):
    try:
        window.iconbitmap(resource_path("assets/icon.ico"))
    except tk.TclError:
        pass


def wave(t):
    """0 → 1 → 0 over one loop period, for pulsing glows."""
    return (1 - math.cos(2 * math.pi * t)) / 2
