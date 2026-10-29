# src/gui.py

import collections
import copy
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter
from PIL import Image, ImageDraw

from .organizer import _format_size, build_preview, generate_report, has_history, load_settings, resource_path, save_settings, start_monitoring, undo_last_run
from .report_export import render_report_html, write_report_csv
from .ui import anim, theme
from .ui.anim import lerp, lerp_color, linear
from .ui.autostart import set_autostart
from .ui.pages import PAGES
from .ui.pages.activity import log_kind
from .ui.tray import TrayIcon
from .ui.widgets import SidebarNav, StatusDot, ToastManager, Tooltip, button_colors, confirm, icon_button, make_button, scaling, set_hover_colors, wave

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

# state -> (palette color, status light pulses)
STATE_STYLE = {
    "Idle": ("muted", False),
    "Scanning": ("warning", True),
    "Monitoring": ("success", True),
    "Paused": ("warning", False),
    "Stopping": ("muted", True),
    "Undoing": ("accent_alt", True),
    "Error": ("error", False),
}
SIDEBAR_WIDTH = {False: 236, True: 76}
NARROW_WIDTH = 1060
SHORT_HEIGHT = 700
GIF_BOX = (190, 240)
GLOW_PULSES = 3


def _short_path(path, limit=84):
    return path if len(path) <= limit else f"{path[:limit // 2 - 1]}…{path[-(limit // 2):]}"


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FLCL File Organizer")
        self.root.geometry("1200x780")
        self.root.minsize(940, 620)

        self.settings = load_settings()
        preferences = self.settings["preferences"]
        self.directory_path = tk.StringVar(master=root)
        self.recursive_var = tk.BooleanVar(master=root, value=preferences.get("recursive", False))
        self.notify_var = tk.BooleanVar(master=root, value=preferences.get("notify", True))
        self.autostart_var = tk.BooleanVar(master=root, value=preferences.get("autostart", False))
        self.tray_var = tk.BooleanVar(master=root, value=preferences.get("minimize_to_tray", False))
        self.reduce_motion_var = tk.BooleanVar(master=root, value=preferences.get("reduce_motion", False))
        self.theme_name = preferences.get("theme") if preferences.get("theme") in theme.PALETTES else theme.DEFAULT_THEME
        self.sidebar_collapsed = bool(preferences.get("sidebar_collapsed", False))

        # Preview state lives here, not in widgets, so the UI can be rebuilt (theme switch) at any time.
        self.preview_plan = []
        self.preview_error = None
        self._excluded_sources = set()
        self.search_text = ""
        self.category_filter = None
        self.rules_draft = None

        self.monitor_thread = None
        self.undo_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.log_queue = queue.Queue()
        self.running = False
        self.stopping = False
        self.phase = None
        self.state = "Idle"
        self.hint = "Select a folder to begin."
        self.progress = [0, 0]
        self.moved_count = self.error_count = self.skipped_count = 0
        self.log_lines = collections.deque(maxlen=1500)
        self.undo_available = has_history()

        self.page = "organize"
        self.pages = {}
        self.page_frames = {}
        self.gif_frames = []
        self.gif_duration = 100
        self.gif_index = 0
        self.gif_label = None
        self._narrow = False
        self._short = False
        self._sidebar_width = SIDEBAR_WIDTH[self.sidebar_collapsed]
        self._shutting_down = False
        self._tick_job = None
        self._gif_job = None
        self._drop_ready = False

        self.animator = anim.install(root)
        self.system_reduce_motion = anim.system_reduce_motion()
        self.animator.reduce_motion = self.reduce_motion_var.get() or self.system_reduce_motion
        theme.load_fonts(root)
        theme.apply(self.theme_name)
        self.root.configure(fg_color=theme.current["window"])
        self._setup_window_icon()
        self._load_gif_frames()
        self.toasts = ToastManager(root)
        self.tray = TrayIcon(root, self._shutdown)

        self._build_ui()
        self._bind_shortcuts()
        self._enable_drop()
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.log("Ready. Select a folder to begin.")
        self._tick()
        self._animate_gif()
        self.root.attributes("-alpha", 0.0)
        self.animator.animate("window", theme.MOTION["slow"], lambda t: self.root.attributes("-alpha", t), delay_ms=60)

        last_folder = preferences.get("last_folder", "")
        if os.path.isdir(last_folder):
            self._load_folder(last_folder, cascade=True)
            if preferences.get("autostart"):
                self.root.after(800, lambda: self.start_action(ask=False))

    # --- assets ----------------------------------------------------------

    def _setup_window_icon(self):
        try:
            self.root.iconbitmap(resource_path("assets/icon.ico"))
        except tk.TclError as error:
            print(f"Warning: Could not load window icon: {error}")

    def _load_gif_frames(self):
        try:
            with Image.open(resource_path("assets/haruko.gif")) as gif:
                ratio = min(GIF_BOX[0] / gif.width, GIF_BOX[1] / gif.height)
                size = (round(gif.width * ratio), round(gif.height * ratio))
                self.gif_duration = gif.info.get("duration", 100) or 100
                corners = Image.new("L", gif.size, 0)
                ImageDraw.Draw(corners).rounded_rectangle((0, 0, gif.width - 1, gif.height - 1), radius=round(theme.RADIUS["lg"] / ratio), fill=255)
                for index in range(gif.n_frames):
                    gif.seek(index)
                    frame = gif.convert("RGBA")
                    frame.putalpha(corners)
                    self.gif_frames.append(customtkinter.CTkImage(light_image=frame, dark_image=frame, size=size))
        except OSError:
            print("Warning: 'assets/haruko.gif' could not be loaded.")

    # --- layout ----------------------------------------------------------

    def _build_ui(self):
        p = theme.current
        self.shell = customtkinter.CTkFrame(self.root, fg_color=p["window"], corner_radius=0)
        self.shell.pack(fill="both", expand=True)
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)
        self.pages = {}
        self.page_frames = {}
        self._build_sidebar(self.shell)

        content = customtkinter.CTkFrame(self.shell, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", padx=26, pady=(20, 22))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        header = customtkinter.CTkFrame(content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        self.title_label = customtkinter.CTkLabel(header, text="", font=theme.font("display"), text_color=p["text"], anchor="w")
        self.title_label.grid(row=0, column=0, sticky="sw")
        self.subtitle_label = customtkinter.CTkLabel(header, text="", font=theme.font("body"), text_color=p["muted"], anchor="w")
        self.subtitle_label.grid(row=1, column=0, sticky="nw")
        icon_button(header, "theme", self.cycle_theme, tooltip="Switch theme", bg=p["window"], size=40).grid(row=0, column=1, rowspan=2, sticky="e")

        self.folder_bar = customtkinter.CTkFrame(content, fg_color=p["panel"], border_color=p["border"], border_width=1, corner_radius=theme.RADIUS["lg"])
        self.folder_bar.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.folder_bar.grid_columnconfigure(1, weight=1)
        customtkinter.CTkLabel(self.folder_bar, text=theme.ICONS["folder"], font=theme.font("icon_lg"), text_color=p["accent"]).grid(row=0, column=0, padx=(18, 12), pady=12)
        self.path_label = customtkinter.CTkLabel(self.folder_bar, text="", font=theme.font("body"), anchor="w")
        self.path_label.grid(row=0, column=1, sticky="ew")
        self.path_tip = Tooltip(self.path_label, "")
        self.browse_button = make_button(self.folder_bar, "BROWSE", self.select_folder, variant="ghost", width=116, height=36, tooltip="Choose the folder to organize (Ctrl+O).")
        self.browse_button.grid(row=0, column=2, padx=12, pady=10)

        self.page_host = customtkinter.CTkFrame(content, fg_color="transparent")
        self.page_host.grid(row=2, column=0, sticky="nsew")

        actions = customtkinter.CTkFrame(content, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        actions.grid_columnconfigure(0, weight=1)
        self.start_button = make_button(actions, "START ORGANIZING", self.start_action, height=50, border_width=2, border_color=p["accent"], tooltip="Move the checked files, then keep watching for new ones (Ctrl+R).")
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.pause_button = make_button(actions, "PAUSE", self.pause_action, variant="ghost", width=118, height=50, tooltip="Pause or resume detection of new files.")
        self.pause_button.grid(row=0, column=1, padx=(0, 10))
        self.stop_button = make_button(actions, "STOP", self.stop_action, variant="ghost", width=118, height=50, tooltip="Stop monitoring (Ctrl+S).")
        self.stop_button.grid(row=0, column=2, padx=(0, 10))
        self.undo_button = make_button(actions, "UNDO", self.undo_action, variant="ghost", width=118, height=50, tooltip="Restore the files moved in the most recent run.")
        self.undo_button.grid(row=0, column=3)

        for toast in self.toasts.toasts:
            toast["frame"].lift()
        self._register_drop()
        self._render_folder()
        self.show_page(self.page, animate=False)
        self._apply_sidebar(animate=False)
        self._render_state()
        self._sync_controls()

    def _build_sidebar(self, shell):
        p = theme.current
        self.sidebar = customtkinter.CTkFrame(shell, fg_color=p["panel"], corner_radius=0, width=self._sidebar_width)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.pack_propagate(False)

        brand = customtkinter.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(20, 22))
        icon_button(brand, "menu", self.toggle_sidebar, tooltip="Collapse or expand the sidebar.", bg=p["panel"], size=40).pack(side="left")
        self.brand_text = customtkinter.CTkFrame(brand, fg_color="transparent")
        customtkinter.CTkLabel(self.brand_text, text="FLCL", font=theme.font("title"), text_color=p["accent"], anchor="w", height=20).pack(fill="x")
        customtkinter.CTkLabel(self.brand_text, text="FILE ORGANIZER", font=theme.font("label"), text_color=p["muted"], anchor="w", height=14).pack(fill="x")

        items = [(key, icon, label, f"{title} (Ctrl+{index + 1})") for index, (key, icon, label, title, _sub, _cls) in enumerate(PAGES)]
        self.nav = SidebarNav(self.sidebar, items, self.show_page, bg=p["panel"])
        self.nav.pack(fill="x")

        self.status_pill = customtkinter.CTkFrame(self.sidebar, fg_color=p["surface"], corner_radius=theme.RADIUS["pill"], height=38)
        self.status_pill.pack(side="bottom", fill="x", padx=16, pady=(8, 18))
        self.side_dot = StatusDot(self.status_pill, bg=p["surface"], size=16)
        self.side_dot.pack(side="left", padx=(14, 8), pady=10)
        self.side_state = customtkinter.CTkLabel(self.status_pill, text="", font=theme.font("label"), anchor="w")
        self.gif_label = customtkinter.CTkLabel(self.sidebar, text="")

    def _collapsed(self):
        return self.sidebar_collapsed or self._narrow

    def _apply_sidebar(self, animate=True):
        collapsed = self._collapsed()
        target = SIDEBAR_WIDTH[collapsed]
        start = self._sidebar_width

        def labels():
            self.nav.set_collapsed(collapsed)
            if collapsed:
                self.brand_text.pack_forget()
                self.side_state.pack_forget()
            else:
                self.brand_text.pack(side="left", padx=(12, 0))
                self.side_state.pack(side="left", fill="x", expand=True)
            self._show_gif()

        def step(t):
            self._sidebar_width = lerp(start, target, t)
            self.sidebar.configure(width=round(self._sidebar_width))

        if collapsed:
            labels()
        self.animator.animate("sidebar", theme.MOTION["base"] if animate else 0, step, on_done=None if collapsed else labels)

    def _show_gif(self):
        if self.gif_frames and not self._collapsed() and not self._short:
            if not self.gif_label.winfo_manager():
                self.gif_label.pack(side="bottom", pady=(0, 4))
        else:
            self.gif_label.pack_forget()

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        self._save_preferences()
        self._apply_sidebar()

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        factor = scaling(self.root)
        narrow = event.width / factor < NARROW_WIDTH
        short = event.height / factor < SHORT_HEIGHT
        if short != self._short:
            self._short = short
            self._show_gif()
        if narrow != self._narrow:
            self._narrow = narrow
            self._apply_sidebar()

    def show_page(self, key, animate=True):
        p = theme.current
        entry = next(page for page in PAGES if page[0] == key)
        if key not in self.pages:
            holder = customtkinter.CTkFrame(self.page_host, fg_color="transparent")
            self.pages[key] = entry[5](holder, self)
            self.pages[key].pack(fill="both", expand=True)
            self.page_frames[key] = holder
        for other_key, holder in self.page_frames.items():
            if other_key != key:
                holder.place_forget()
        holder = self.page_frames[key]
        changed = key != self.page
        holder.place(relx=0, rely=0, relwidth=1, relheight=1, x=0)
        if animate and changed:
            self.animator.animate((self, "page"), theme.MOTION["base"] + 60, lambda t: holder.place(x=lerp(40, 0, t)))
            self.animator.animate((self, "title"), theme.MOTION["slow"], lambda t: self.title_label.configure(text_color=lerp_color(p["window"], p["text"], t)))
        self.page = key
        self.nav.select(key, animate)
        self.title_label.configure(text=entry[3].upper())
        self.subtitle_label.configure(text=entry[4])
        if hasattr(self.pages[key], "on_show"):
            self.pages[key].on_show()

    def cycle_theme(self):
        names = list(theme.PALETTES)
        self.set_theme(names[(names.index(self.theme_name) + 1) % len(names)])

    def set_theme(self, name):
        if name == self.theme_name or name not in theme.PALETTES:
            return
        self.theme_name = name
        self._save_preferences()

        def rebuild():
            theme.apply(name)
            self.root.configure(fg_color=theme.current["window"])
            self.shell.destroy()
            self._build_ui()

        if self.animator.reduce_motion:
            rebuild()
            return

        def swap():
            rebuild()
            self.animator.animate("window", theme.MOTION["slow"], lambda t: self.root.attributes("-alpha", t))

        self.animator.animate("window", theme.MOTION["fast"], lambda t: self.root.attributes("-alpha", 1 - t), on_done=swap)

    # --- rendering -------------------------------------------------------

    def state_color(self):
        key, pulsing = STATE_STYLE[self.state]
        return theme.current[key], pulsing

    def _set_state(self, state, hint):
        self.state = state
        self.hint = hint
        self._render_state()
        self._sync_controls()

    def _render_state(self):
        color, pulsing = self.state_color()
        self.side_dot.set(color, pulsing)
        self.side_state.configure(text=self.state.upper(), text_color=color)
        if "activity" in self.pages:
            self.pages["activity"].render_state()

    def _render_folder(self):
        p = theme.current
        directory = self.directory_path.get()
        if directory:
            self.path_label.configure(text=_short_path(directory), text_color=p["text"])
        else:
            self.path_label.configure(text="No folder selected. Drop one anywhere in this window.", text_color=p["muted"])
        self.path_tip.text = directory

    def _set_enabled(self, button, enabled, variant):
        button.configure(state="normal" if enabled else "disabled")
        base, hover, _text = button_colors(variant)
        if variant == "primary" and not enabled:
            base = hover = theme.current["surface"]
        set_hover_colors(button, base, hover)

    def _sync_controls(self):
        folder = os.path.isdir(self.directory_path.get())
        busy = self.running or self.undo_thread is not None
        self._set_enabled(self.browse_button, not busy, "ghost")
        self._set_enabled(self.start_button, folder and not busy, "primary")
        self._set_enabled(self.pause_button, self.running and not self.stopping and self.phase == "monitor", "ghost")
        self.pause_button.configure(text="RESUME" if self.pause_event.is_set() else "PAUSE")
        self._set_enabled(self.stop_button, self.running and not self.stopping, "ghost")
        self.stop_button.configure(text="STOPPING…" if self.stopping else "STOP")
        self._set_enabled(self.undo_button, self.undo_available and not busy, "ghost")
        self._update_start_glow()

    def _update_start_glow(self):
        p = theme.current
        button = self.start_button
        glow = str(button.cget("state")) == "normal" and bool(self.selected_move_items())
        if glow:
            def paint(t):
                # shortcut: recolors CTkButton's private border items; configure(border_color) redraws the whole
                # button each frame. Revisit if a CustomTkinter upgrade renames these internals.
                color = lerp_color(p["accent"], p["highlight"], wave(t * GLOW_PULSES % 1))
                button._border_color = color
                button._canvas.itemconfig("border_parts", outline=color, fill=color)

            # A few pulses invite a click, then it rests: endless motion distracts and costs idle CPU.
            self.animator.animate((self, "glow"), 1800 * GLOW_PULSES, paint, easing=linear)
        else:
            self.animator.cancel((self, "glow"))
            button.configure(border_color=p["accent"] if str(button.cget("state")) == "normal" else p["surface"])

    # --- preview ---------------------------------------------------------

    def move_items(self):
        return [item for item in self.preview_plan if item["status"] == "move"]

    def is_excluded(self, item):
        return os.path.normcase(item["source_path"]) in self._excluded_sources

    def selected_move_items(self):
        return [item for item in self.move_items() if not self.is_excluded(item)]

    def visible_preview_items(self):
        query = self.search_text.lower()
        return [
            item for item in self.move_items()
            if (not query or query in item["filename"].lower())
            and (self.category_filter is None or item["destination_folder"] == self.category_filter)
        ]

    def set_included(self, items, included):
        for item in items:
            path = os.path.normcase(item["source_path"])
            if included:
                self._excluded_sources.discard(path)
            else:
                self._excluded_sources.add(path)
        self._update_start_glow()

    def select_folder(self):
        if self.running or self.undo_thread is not None:
            return
        directory = filedialog.askdirectory(parent=self.root, initialdir=self.directory_path.get() or None)
        if directory:
            self._load_folder(directory, cascade=True)
            self.log(f"FOLDER SELECTED: {directory}")
            self.show_page("organize")

    def refresh_preview(self):
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            self.toasts.show("Select a valid folder before refreshing the preview.", "warning")
            return
        self._load_folder(directory, cascade=True, quiet=True)
        self.toasts.show(f"Preview refreshed: {len(self.selected_move_items())} file(s) to organize.", "info", 2400)

    def _load_folder(self, directory, cascade=False, quiet=False):
        self.directory_path.set(directory)
        try:
            self.preview_plan = build_preview(directory, self.settings["rules"], self.settings["filters"], self.recursive_var.get())
            self.preview_error = None
        except (OSError, ValueError) as error:
            self.preview_plan = []
            self.preview_error = str(error)
            self._set_state("Error", "Preview failed. Check folder permissions or choose another location.")
            self.toasts.show("The selected folder could not be read.", "error")
        if self.preview_error is None:
            known = {os.path.normcase(item["source_path"]) for item in self.move_items()}
            self._excluded_sources &= known
            if not quiet and not self.running:
                self._set_state("Idle", "Ready to organize this folder.")
        if not quiet:
            self._save_preferences()
        self._render_folder()
        if "organize" in self.pages:
            self.pages["organize"].render(cascade=cascade)
        self._sync_controls()

    def _reload_preview(self):
        if os.path.isdir(self.directory_path.get()):
            self._load_folder(self.directory_path.get(), quiet=True)

    # --- log & worker messages --------------------------------------------

    def log(self, message):
        entry = (time.strftime("%H:%M:%S"), log_kind(message), message)
        self.log_lines.append(entry)
        if "activity" in self.pages:
            self.pages["activity"].append(entry)

    def clear_log(self):
        self.log_lines.clear()
        if "activity" in self.pages:
            self.pages["activity"].clear()

    def _queue_log(self, message):
        """Queue worker messages so Tkinter is only updated on the UI thread."""
        self.log_queue.put(message)

    def _tick(self):
        if self._shutting_down:
            return
        handled = 0
        try:
            while handled < 200:
                self._handle_message(self.log_queue.get_nowait())
                handled += 1
        except queue.Empty:
            pass
        self._check_threads()
        busy = handled or self.running or self.undo_thread is not None
        self._tick_job = self.root.after(30 if busy else 250, self._tick)

    def _handle_message(self, message):
        self.log(message)
        scanning = self.state == "Scanning"
        if message.startswith("File moved:"):
            self.moved_count += 1
            if scanning:
                self.progress[0] += 1
            elif self.phase == "monitor":
                name = re.search(r"'([^']*)'", message)
                self.toasts.show(f"Organized {name.group(1) if name else 'a new file'}", "success", 2600)
                if self.notify_var.get():
                    self._notify("File organized", message)
        elif message.startswith("ERROR"):
            self.error_count += 1
            if scanning and message.startswith("ERROR organizing"):
                self.progress[0] += 1
            self.toasts.show(message, "error")
        elif "SKIPPED" in message and "excluded in the preview" not in message:
            self.skipped_count += 1
            if scanning:
                self.progress[0] += 1
        elif message.startswith(("Initial scan complete", "No files to organize")):
            self.progress[0] = self.progress[1]
            self.toasts.show(f"Initial scan done: {self.moved_count} file(s) organized.", "success")
            if self.notify_var.get() and self.moved_count:
                self._notify("Initial scan complete", f"{self.moved_count} file(s) organized.")
            self._reload_preview()
        elif message.startswith("Real-time monitoring started"):
            self.phase = "monitor"
            self._set_state("Monitoring", "Watching for new files. They move as soon as they finish copying.")
        elif message.startswith("Undo complete"):
            self.toasts.show(message, "success")
        self.progress[0] = min(self.progress[0], self.progress[1])
        if "activity" in self.pages:
            self.pages["activity"].render_counts()
            if scanning:
                self.pages["activity"].render_state()

    def _check_threads(self):
        if self.running and not self.monitor_thread.is_alive():
            self.running = False
            self.phase = None
            self.pause_event.clear()
            if self.stopping:
                self._set_state("Idle", "Monitoring stopped. Ready for the next run.")
                self.toasts.show("Monitoring stopped.", "info", 2400)
            else:
                self._set_state("Error", "Monitoring ended unexpectedly. Check the activity log and the folder.")
                self.toasts.show("Monitoring stopped unexpectedly.", "error")
            self.stopping = False
            self.undo_available = has_history()
            self._reload_preview()
            self._sync_controls()
        if self.undo_thread is not None and not self.undo_thread.is_alive():
            self.undo_thread = None
            self.undo_available = has_history()
            self._set_state("Idle", "Undo finished. Review the log for anything skipped.")
            self._reload_preview()

    def _notify(self, title, message):
        try:
            from winotify import Notification
            Notification(app_id="FLCL File Organizer", title=title, msg=message, icon=resource_path("assets/icon.png")).show()
        except (ImportError, OSError):
            pass

    # --- actions ---------------------------------------------------------

    def start_action(self, ask=True):
        if self.running or self.undo_thread is not None:
            return
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            self.toasts.show("Select an existing folder before starting.", "error")
            return
        selected = self.selected_move_items()
        if ask:
            if selected:
                total_size = sum(item["size"] for item in selected)
                categories = {item["destination_folder"] for item in selected}
                lines = [f"Move {len(selected)} file(s) ({_format_size(total_size)}) into {len(categories)} category folder(s), then keep watching for new files?"]
                no_rule = sum(1 for item in selected if not item["has_rule"])
                conflicts = sum(1 for item in selected if item["conflict"])
                if no_rule:
                    lines.append(f"• {no_rule} file(s) have no matching rule and will go to 'Others'.")
                if conflicts:
                    lines.append(f"• {conflicts} file(s) will be renamed to avoid overwriting.")
                if self.recursive_var.get():
                    lines.append("• Subfolders are included.")
                title, button = "Confirm organization", "ORGANIZE"
            else:
                lines = ["Nothing in the preview is selected to move. Start watching this folder for new files?"]
                title, button = "Start monitoring", "MONITOR"
            if not confirm(self.root, title, "\n".join(lines), button, icon="play"):
                return

        self.moved_count = self.error_count = self.skipped_count = 0
        self.progress = [0, len(selected)]
        self.running = True
        self.stopping = False
        self.phase = "scan"
        self.stop_event.clear()
        self.pause_event.clear()
        self.monitor_thread = threading.Thread(
            target=start_monitoring,
            args=(directory, self.stop_event, self._queue_log, self.pause_event, self.recursive_var.get()),
            kwargs={"excluded_paths": set(self._excluded_sources)},
            daemon=True,
        )
        self.monitor_thread.start()
        self._set_state("Scanning", "Organizing existing files. Large or busy files are checked for stability first.")
        if "activity" in self.pages:
            self.pages["activity"].render_counts(animate=False)
        self.show_page("activity")

    def pause_action(self):
        if not self.running or self.phase != "monitor":
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self._set_state("Monitoring", "Monitoring resumed.")
            self._queue_log("Monitoring resumed.")
        else:
            self.pause_event.set()
            self._set_state("Paused", "New files are queued until you resume.")
            self._queue_log("Monitoring paused.")

    def stop_action(self):
        if not self.running or self.stopping:
            return
        self.stopping = True
        self.stop_event.set()
        self.pause_event.clear()  # a paused event handler would otherwise block the observer from stopping
        self._set_state("Stopping", "Finishing the current file and shutting down the watcher.")

    def undo_action(self):
        if self.running:
            self.toasts.show("Stop monitoring before undoing the last run.", "warning")
            return
        if self.undo_thread is not None:
            return
        history = self.build_report()["recent_history"]
        count = history[0]["count"] if history else 0
        if not confirm(self.root, "Undo last run", f"Move {count} file(s) from the latest run back to where they were? Files that were moved or replaced since then are skipped.", "UNDO", icon="undo"):
            return
        self.undo_thread = threading.Thread(target=undo_last_run, args=(self._queue_log,), daemon=True)
        self.undo_thread.start()
        self._set_state("Undoing", "Restoring the previous organization run.")
        self.show_page("activity")

    def on_preference_changed(self, key):
        if key == "reduce_motion":
            self.animator.reduce_motion = self.reduce_motion_var.get() or self.system_reduce_motion
            self._render_state()
            self._update_start_glow()
        elif key == "recursive" and os.path.isdir(self.directory_path.get()):
            self._load_folder(self.directory_path.get(), cascade=True, quiet=True)
        self._save_preferences()

    def _save_preferences(self):
        self.settings["preferences"].update({
            "recursive": self.recursive_var.get(),
            "notify": self.notify_var.get(),
            "autostart": self.autostart_var.get(),
            "minimize_to_tray": self.tray_var.get(),
            "last_folder": self.directory_path.get(),
            "theme": self.theme_name,
            "reduce_motion": self.reduce_motion_var.get(),
            "sidebar_collapsed": self.sidebar_collapsed,
        })
        try:
            save_settings(self.settings)
        except OSError as error:
            self.toasts.show(f"Preferences could not be saved: {error}", "error")
        set_autostart(self.autostart_var.get())

    def save_rules(self, draft):
        before = len(self.selected_move_items())
        self.settings["rules"] = copy.deepcopy(draft["rules"])
        self.settings["filters"] = copy.deepcopy(draft["filters"])
        try:
            save_settings(self.settings)
        except OSError as error:
            self.toasts.show(f"Rules could not be saved: {error}", "error")
            return
        self.rules_draft = None
        message = "Rules saved."
        if os.path.isdir(self.directory_path.get()):
            self._load_folder(self.directory_path.get(), quiet=True)
            message = f"Rules saved. {len(self.selected_move_items())} file(s) will move (was {before})."
        if self.running:
            message += " Restart monitoring to apply them."
        self.toasts.show(message, "success")

    def build_report(self):
        return generate_report(self.directory_path.get())

    def export_report(self, kind, report):
        if report is None:
            return
        labels = {"csv": ("CSV files", "*.csv"), "html": ("HTML files", "*.html")}
        path = filedialog.asksaveasfilename(parent=self.root, title=f"Export report as {kind.upper()}", defaultextension=f".{kind}", filetypes=[labels[kind]], initialfile=f"flcl-report.{kind}")
        if not path:
            return
        try:
            if kind == "csv":
                write_report_csv(path, report)
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(render_report_html(report, theme.current))
        except OSError as error:
            self.toasts.show(f"Could not save the report: {error}", "error")
            return
        self.toasts.show(f"Report saved to {path}", "success")

    # --- input -----------------------------------------------------------

    def _bind_shortcuts(self):
        bindings = {
            "<Control-o>": self.select_folder,
            "<F5>": self.refresh_preview,
            "<Control-p>": self.refresh_preview,
            "<Control-r>": self.start_action,
            "<Control-s>": self.stop_action,
            "<Control-f>": self._focus_search,
        }
        for sequence, action in bindings.items():
            self.root.bind(sequence, lambda _e, a=action: a())
        for index, page in enumerate(PAGES):
            self.root.bind(f"<Control-Key-{index + 1}>", lambda _e, k=page[0]: self.show_page(k))

    def _focus_search(self):
        self.show_page("organize")
        self.pages["organize"].focus_search()

    def _enable_drop(self):
        if TkinterDnD is None:
            return
        try:
            TkinterDnD._require(self.root)
        except (RuntimeError, tk.TclError):
            return
        self._drop_ready = True
        self._register_drop()

    def _register_drop(self):
        # The shell covers the whole window; tkinterdnd2 adds its methods to widgets but not to an existing root.
        if not self._drop_ready:
            return
        self.shell.drop_target_register(DND_FILES)
        self.shell.dnd_bind("<<DropEnter>>", self._on_drag_enter)
        self.shell.dnd_bind("<<DropLeave>>", self._on_drag_leave)
        self.shell.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drag_enter(self, event):
        p = theme.current
        self.animator.animate((self, "drop"), theme.MOTION["base"], lambda t: self.folder_bar.configure(border_color=lerp_color(p["border"], p["accent"], t)))
        return event.action

    def _on_drag_leave(self, event=None):
        self.animator.cancel((self, "drop"))
        self.folder_bar.configure(border_color=theme.current["border"])
        return event.action if event else None

    def _on_drop(self, event):
        self._on_drag_leave()
        if self.running or self.undo_thread is not None:
            self.toasts.show("Stop monitoring before switching folders.", "warning")
            return event.action
        folder = next((path for path in self.root.tk.splitlist(event.data) if os.path.isdir(path)), None)
        if folder is None:
            self.toasts.show("Drop a folder, not a file.", "warning")
            return event.action
        self._load_folder(folder, cascade=True)
        self.log(f"FOLDER SELECTED: {folder}")
        self.show_page("organize")
        return event.action

    # --- lifecycle -------------------------------------------------------

    def _animate_gif(self):
        if self._shutting_down or not self.gif_frames:
            return
        if self.gif_label.winfo_ismapped():
            self.gif_label.configure(image=self.gif_frames[self.gif_index])
        if self.state not in ("Paused", "Error") and not self.animator.reduce_motion:
            self.gif_index = (self.gif_index + 1) % len(self.gif_frames)
        speed = 0.55 if self.state in ("Scanning", "Undoing") else 1.0
        self._gif_job = self.root.after(max(20, int(self.gif_duration * speed)), self._animate_gif)

    def _close_window(self):
        if self.tray_var.get() and self.tray.available:
            self.tray.hide_window()
            return
        self._shutdown()

    def _shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_event.set()
            self.pause_event.clear()
        self.animator.cancel_all()
        for job in (self._tick_job, self._gif_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self.tray.stop()
        try:
            self.root.quit()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
