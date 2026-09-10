# src/gui.py

import customtkinter
from tkinter import filedialog, messagebox
import threading
import queue
import os
import sys
import copy
import tkinter as tk
import winreg
from PIL import Image
try:
    import pystray
except ImportError:
    pystray = None
from .organizer import _format_size, build_preview, generate_report, has_history, load_settings, resource_path, save_settings, start_monitoring, undo_last_run


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self.widget.bind("<Enter>", self._show)
        self.widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.window or not self.text:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        label = tk.Label(
            self.window,
            text=self.text,
            bg="#1F1F1F",
            fg="#F5F5F5",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=("Segoe UI", 10),
        )
        label.pack()
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.window.wm_geometry(f"+{x}+{y}")

    def _hide(self, event=None):
        if self.window:
            self.window.destroy()
            self.window = None

customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("blue")

THEME_PALETTES = {
    "FLCL": {
        "accent": "#FF3399",
        "accent_soft": "#C42A7A",
        "panel": "#171A1F",
        "surface": "#212834",
        "border": "#394555",
        "text": "#EAF2FF",
        "muted": "#AEB9C7",
        "success": "#6FE4A4",
        "warning": "#F7D76A",
        "error": "#FF6B6B",
        "window": "#0F1318",
    },
    "Neutral": {
        "accent": "#74C0FC",
        "accent_soft": "#4C9AE6",
        "panel": "#181C20",
        "surface": "#20262C",
        "border": "#343C44",
        "text": "#E8EEF7",
        "muted": "#A9B4C0",
        "success": "#7AD7A6",
        "warning": "#E8C859",
        "error": "#FF8A80",
        "window": "#101418",
    },
}

class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("File Organizer")
        self.root.geometry("1120x720")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)

        # --- Instance variables ---
        self.directory_path = customtkinter.StringVar()
        self.monitor_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.settings = load_settings()
        preferences = self.settings["preferences"]
        self.recursive_var = tk.BooleanVar(value=preferences.get("recursive", False))
        self.notify_var = tk.BooleanVar(value=preferences.get("notify", True))
        self.autostart_var = tk.BooleanVar(value=preferences.get("autostart", False))
        self.tray_var = tk.BooleanVar(value=preferences.get("minimize_to_tray", False))
        self.theme_var = tk.StringVar(value=preferences.get("theme", "FLCL"))
        self.p = THEME_PALETTES.get(self.theme_var.get(), THEME_PALETTES["FLCL"])
        self.preview_plan = []
        self.preview_rows = []
        self._excluded_sources = set()
        self.current_directory = ""
        self._preview_last_width = 0
        self._resize_job = None
        self._measure_fontobj = None
        self._shutting_down = False
        self.moved_count = 0
        self.error_count = 0
        self.pause_event = threading.Event()
        self.undo_thread = None
        self.tray_icon = None
        self.gif_frames = []
        self.gif_duration = 100
        self.gif_label = None
        self.current_state = "Stopped"

        # --- Setup Window and Assets ---
        self._setup_window_icon()
        self._load_font()
        self._load_gif_frames()

        # --- Layout Configuration ---
        self.root.grid_columnconfigure(0, weight=1, minsize=200)
        self.root.grid_columnconfigure(1, weight=2, minsize=480)
        self.root.grid_rowconfigure(0, weight=1)

        # --- Left Frame (GIF) ---
        left_frame = customtkinter.CTkFrame(self.root, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.gif_label = customtkinter.CTkLabel(left_frame, text="")
        self.gif_label.pack(expand=True)

        # --- Right Frame (Controls) ---
        right_frame = customtkinter.CTkFrame(self.root, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(2, weight=1)

        # --- Widgets ---
        folder_label = customtkinter.CTkLabel(right_frame, text="Folder to organize", font=self.main_font, text_color=self.p["text"])
        folder_label.grid(row=0, column=0, sticky="w", pady=(0, 5))

        folder_entry = customtkinter.CTkEntry(right_frame, textvariable=self.directory_path, state='readonly', font=self.main_font, height=42, fg_color=self.p["surface"], border_color=self.p["border"])
        folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 112))

        self.select_button = customtkinter.CTkButton(right_frame, text="Browse", command=self.select_folder, font=self.main_font, width=102, height=42)
        self.select_button.place(relx=1, rely=0, anchor="ne", y=28)
        Tooltip(self.select_button, "Choose the folder to organize.")

        self.view_tabs = customtkinter.CTkTabview(right_frame, fg_color="transparent")
        self.view_tabs.grid(row=2, column=0, sticky="nsew", pady=(14, 12))
        self.view_tabs.add("Organize")
        self.view_tabs.add("Activity")
        self.view_tabs.add("Settings")
        organize_view = self.view_tabs.tab("Organize")
        activity_view = self.view_tabs.tab("Activity")
        settings_view = self.view_tabs.tab("Settings")
        organize_view.grid_columnconfigure(0, weight=1)
        organize_view.grid_rowconfigure(2, weight=1)
        activity_view.grid_columnconfigure(0, weight=1)
        activity_view.grid_rowconfigure(2, weight=1)
        settings_view.grid_columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._rebuild_preview_rows())
        self.preview_toolbar = customtkinter.CTkFrame(organize_view, fg_color="transparent")
        self.preview_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.preview_toolbar.grid_columnconfigure(0, weight=1)
        self.search_entry = customtkinter.CTkEntry(self.preview_toolbar, textvariable=self.search_var, font=self.log_font, placeholder_text="Search files in preview...", fg_color=self.p["surface"], border_color=self.p["border"])
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.preview_button = customtkinter.CTkButton(self.preview_toolbar, text="Refresh preview", command=self.refresh_preview, font=self.main_font, height=34, fg_color=self.p["panel"], hover_color=self.p["surface"], text_color=self.p["text"])
        self.preview_button.grid(row=0, column=1)
        Tooltip(self.preview_button, "Refresh the move preview for the selected folder (F5).")

        self.summary_frame = customtkinter.CTkFrame(organize_view, fg_color="transparent")
        self.summary_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.summary_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.summary_cards = []
        for index, label in enumerate(["To organize", "No rule", "Conflicts", "Ignored", "Total size"]):
            card = customtkinter.CTkFrame(self.summary_frame, corner_radius=12, fg_color=self.p["surface"], border_color=self.p["border"], border_width=1)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 8) if index < 4 else (0, 0))
            customtkinter.CTkLabel(card, text=label, font=self.log_font, text_color=self.p["text"], anchor="w").pack(anchor="w", padx=12, pady=(10, 0))
            value = customtkinter.CTkLabel(card, text="0", font=self.main_font, text_color=self.p["accent"], anchor="w")
            value.pack(anchor="w", padx=12, pady=(2, 10))
            self.summary_cards.append(value)

        self.preview_list = customtkinter.CTkScrollableFrame(organize_view, fg_color=self.p["surface"], border_color=self.p["border"], border_width=1, corner_radius=10)
        self.preview_list.grid(row=2, column=0, sticky="nsew")
        self.preview_list.bind("<Configure>", lambda event: self._on_preview_resize(event))

        status_frame = customtkinter.CTkFrame(activity_view, fg_color=self.p["surface"], corner_radius=10)
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_columnconfigure(1, weight=2)
        self.status_label = customtkinter.CTkLabel(status_frame, text="Status: Stopped", font=self.main_font, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(10, 2))
        self.progress_bar = customtkinter.CTkProgressBar(status_frame, width=220, height=10, mode="indeterminate")
        self.progress_bar.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 2))
        self.status_hint = customtkinter.CTkLabel(status_frame, text="Ready for the next scan.", font=self.log_font, anchor="w")
        self.status_hint.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))
        self._set_state("Stopped")

        counter_frame = customtkinter.CTkFrame(activity_view, fg_color="transparent")
        counter_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        counter_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.moved_label = customtkinter.CTkLabel(counter_frame, text="Files moved: 0", font=self.main_font, text_color=self.p["success"], anchor="w")
        self.moved_label.grid(row=0, column=0, sticky="w")
        self.error_label = customtkinter.CTkLabel(counter_frame, text="Errors: 0", font=self.main_font, text_color=self.p["error"], anchor="w")
        self.error_label.grid(row=0, column=1, sticky="w")
        clear_log_button = customtkinter.CTkButton(counter_frame, text="Clear log", command=self._clear_log, font=self.log_font, width=100, height=28, fg_color=self.p["panel"], hover_color=self.p["surface"], text_color=self.p["text"])
        clear_log_button.grid(row=0, column=2, sticky="e")
        Tooltip(clear_log_button, "Clear the activity log.")

        self.log_box = customtkinter.CTkTextbox(activity_view, state='disabled', font=self.log_font, wrap="word", fg_color=self.p["surface"], border_color=self.p["border"], text_color=self.p["warning"])
        self.log_box.grid(row=2, column=0, sticky="nsew")

        action_bar = customtkinter.CTkFrame(right_frame, fg_color="transparent")
        action_bar.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        action_bar.grid_columnconfigure(0, weight=3)
        action_bar.grid_columnconfigure(1, weight=1, minsize=102)

        self.start_button = customtkinter.CTkButton(action_bar, text="Start", command=self.start_action, state='disabled', font=self.main_font, height=46, fg_color=self.p["accent"], hover_color=self.p["accent_soft"])
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        Tooltip(self.start_button, "Start organizing files in the selected folder.")

        self.stop_button = customtkinter.CTkButton(action_bar, text="Stop", command=self.stop_action, state='disabled', font=self.main_font, height=46)
        self.stop_button.grid(row=0, column=1, sticky="ew")
        Tooltip(self.stop_button, "Stop the current monitoring task.")

        self.pause_button = customtkinter.CTkButton(settings_view, text="Pause monitoring", command=self.pause_action, state='disabled', font=self.main_font, height=40)
        self.pause_button.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        Tooltip(self.pause_button, "Pause or resume detection while the app is active.")

        self.undo_button = customtkinter.CTkButton(settings_view, text="Undo last run", command=self.undo_action, state='disabled', font=self.main_font, height=40)
        self.undo_button.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        Tooltip(self.undo_button, "Restore the files moved in the most recent run.")

        self.settings_button = customtkinter.CTkButton(settings_view, text="Edit rules & filters", command=self.open_settings, font=self.main_font, height=40)
        self.settings_button.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        Tooltip(self.settings_button, "Edit category rules and ignore patterns.")

        self.report_button = customtkinter.CTkButton(settings_view, text="Open reports", command=self.open_reports, font=self.main_font, height=40)
        self.report_button.grid(row=3, column=0, sticky="ew", pady=(0, 18))
        Tooltip(self.report_button, "Open a summary of the latest organization activity.")

        options_label = customtkinter.CTkLabel(settings_view, text="Preferences", font=self.main_font, anchor="w")
        options_label.grid(row=4, column=0, sticky="w", pady=(0, 8))
        customtkinter.CTkCheckBox(settings_view, text="Include subfolders", variable=self.recursive_var, command=self._save_preferences).grid(row=5, column=0, sticky="w", pady=3)
        customtkinter.CTkCheckBox(settings_view, text="Notifications", variable=self.notify_var, command=self._save_preferences).grid(row=6, column=0, sticky="w", pady=3)
        customtkinter.CTkCheckBox(settings_view, text="Start with Windows", variable=self.autostart_var, command=self._save_preferences).grid(row=7, column=0, sticky="w", pady=3)
        customtkinter.CTkCheckBox(settings_view, text="Minimize to tray", variable=self.tray_var, command=self._save_preferences).grid(row=8, column=0, sticky="w", pady=3)

        appearance = customtkinter.CTkFrame(settings_view, fg_color="transparent")
        appearance.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        theme_label = customtkinter.CTkLabel(appearance, text="Appearance:")
        theme_label.pack(side="left", padx=(0, 8))
        self.theme_menu = customtkinter.CTkOptionMenu(appearance, values=["FLCL", "Neutral"], variable=self.theme_var, command=lambda choice: (self._apply_theme(choice), self._save_preferences()))
        self.theme_menu.pack(side="left")
        Tooltip(self.theme_menu, "Choose between the FLCL aesthetic and the dark neutral interface.")

        self._apply_theme(self.theme_var.get())

        # --- Initial State ---
        if self.gif_frames:
            self._animate_gif(0)
        self.root.after(100, self._process_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self.root.bind("<Control-o>", lambda event: self.select_folder())
        self.root.bind("<F5>", lambda event: self.refresh_preview())
        self.root.bind("<Control-p>", lambda event: self.refresh_preview())
        self.root.bind("<Control-r>", lambda event: self.start_action())
        self.root.bind("<Control-s>", lambda event: self.stop_action())
        self.log("Ready. Select a folder to begin.")
        last_folder = preferences.get("last_folder", "")
        if os.path.isdir(last_folder):
            self._load_folder(last_folder)
            if preferences.get("autostart"):
                self.root.after(500, self.start_action)

    def _setup_window_icon(self):
        """Sets the window icon. This method works reliably when running from source."""
        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception as e:
            print(f"Warning: Could not load window icon: {e}")

    def _load_font(self):
        try:
            font_path = resource_path("Daydream.ttf")
            customtkinter.FontManager.load_font(font_path)
            self.main_font = customtkinter.CTkFont(family="Daydream", size=12)
            self.log_font = customtkinter.CTkFont(family="Daydream", size=10)
        except Exception:
            self.main_font = ("Consolas", 12)
            self.log_font = ("Consolas", 10)

    def _load_gif_frames(self):
        try:
            gif_path = resource_path("haruko.gif")
            with Image.open(gif_path) as gif:
                MAX_WIDTH, MAX_HEIGHT = 350, 450
                original_width, original_height = gif.size
                ratio = original_width / original_height
                new_height = MAX_HEIGHT
                new_width = int(new_height * ratio)
                if new_width > MAX_WIDTH:
                    new_width = MAX_WIDTH
                    new_height = int(new_width / ratio)
                new_size = (new_width, new_height)
                
                self.gif_duration = gif.info.get('duration', 100)
                for i in range(gif.n_frames):
                    gif.seek(i)
                    frame_image = gif.convert("RGBA")
                    ctk_frame = customtkinter.CTkImage(light_image=frame_image, dark_image=frame_image, size=new_size)
                    self.gif_frames.append(ctk_frame)
        except FileNotFoundError:
            print("Warning: 'haruko.gif' not found.")

    def _animate_gif(self, frame_index):
        if self._shutting_down or not self.gif_frames:
            return
        frame = self.gif_frames[frame_index]
        self.gif_label.configure(image=frame)
        next_frame_index = (frame_index + 1) % len(self.gif_frames)
        self.root.after(self.gif_duration, self._animate_gif, next_frame_index)

    def log(self, message):
        self.log_box.configure(state='normal')
        self.log_box.insert("end", f"> {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state='disabled')

    def _set_state(self, state, hint=None):
        self.current_state = state
        palette = THEME_PALETTES.get(self.theme_var.get(), THEME_PALETTES["FLCL"])
        color_map = {
            "Stopped": palette["muted"],
            "Scanning": palette["warning"],
            "Monitoring": palette["success"],
            "Error": palette["error"],
        }
        self.status_label.configure(text=f"Status: {state}", text_color=color_map.get(state, palette["text"]))
        self.progress_bar.configure(progress_color=palette["accent"])
        if hint is not None:
            self.status_hint.configure(text=hint, text_color=palette["muted"])
        if state == "Scanning":
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.set(0)

    def _apply_theme(self, choice):
        self.settings["preferences"]["theme"] = choice
        self.theme_var.set(choice)
        self.p = palette = THEME_PALETTES.get(choice, THEME_PALETTES["FLCL"])

        customtkinter.set_appearance_mode("dark")
        customtkinter.set_default_color_theme("dark-blue")
        self.root.configure(bg=palette["window"])

        if hasattr(self, "start_button"):
            self.start_button.configure(fg_color=palette["accent"], hover_color=palette["accent_soft"], text_color="white")
        if hasattr(self, "stop_button"):
            self.stop_button.configure(fg_color=palette["panel"], hover_color=palette["surface"], text_color=palette["text"])
        if hasattr(self, "pause_button"):
            self.pause_button.configure(fg_color=palette["panel"], hover_color=palette["surface"], text_color=palette["text"])
        if hasattr(self, "undo_button"):
            self.undo_button.configure(fg_color=palette["panel"], hover_color=palette["surface"], text_color=palette["text"])
        if hasattr(self, "settings_button"):
            self.settings_button.configure(fg_color=palette["panel"], hover_color=palette["surface"], text_color=palette["text"])
        if hasattr(self, "report_button"):
            self.report_button.configure(fg_color=palette["panel"], hover_color=palette["surface"], text_color=palette["text"])
        if hasattr(self, "preview_button"):
            self.preview_button.configure(fg_color=palette["panel"], hover_color=palette["surface"], text_color=palette["text"])
        if hasattr(self, "preview_list"):
            self.preview_list.configure(fg_color=palette["surface"], border_color=palette["border"])
        if hasattr(self, "search_entry"):
            self.search_entry.configure(fg_color=palette["surface"], border_color=palette["border"], text_color=palette["text"])
        if hasattr(self, "moved_label"):
            self.moved_label.configure(text_color=palette["success"])
        if hasattr(self, "error_label"):
            self.error_label.configure(text_color=palette["error"])
        if hasattr(self, "log_box"):
            self.log_box.configure(fg_color=palette["surface"], border_color=palette["border"], text_color=palette["warning"])
        if hasattr(self, "status_label"):
            self._set_state(self.current_state)
        if hasattr(self, "summary_cards"):
            for card in self.summary_cards:
                card.configure(text_color=palette["accent"])
        if hasattr(self, "theme_menu"):
            self.theme_menu.configure(fg_color=palette["panel"], button_color=palette["panel"], button_hover_color=palette["surface"], text_color=palette["text"], dropdown_fg_color=palette["panel"], dropdown_hover_color=palette["surface"], dropdown_text_color=palette["text"])
        self._rebuild_preview_rows()

    def _queue_log(self, message):
        """Queue worker messages so Tkinter is only updated on the UI thread."""
        self.log_queue.put(message)

    def _process_log_queue(self):
        if self._shutting_down:
            return
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log(message)
                if message.startswith("File moved:"):
                    self.moved_count += 1
                    self.moved_label.configure(text=f"Files moved: {self.moved_count}")
                elif message.startswith("ERROR"):
                    self.error_count += 1
                    self.error_label.configure(text=f"Errors: {self.error_count}")
                if self.notify_var.get() and message.startswith("File moved:"):
                    self._notify("File organized", message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_log_queue)

    def _clear_log(self):
        self.log_box.configure(state='normal')
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state='disabled')

    def _notify(self, title, message):
        try:
            from winotify import Notification
            Notification(app_id="FLCL File Organizer", title=title, msg=message).show()
        except (ImportError, OSError): pass

    def select_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self._load_folder(directory)
            self.log(f"FOLDER SELECTED: {directory}")

    def _load_folder(self, directory):
        self.directory_path.set(directory)
        try:
            self.preview_plan = build_preview(directory, self.settings["rules"], self.settings["filters"], self.recursive_var.get())
            self._show_preview(directory)
            self.start_button.configure(state='normal')
            self._set_state("Stopped", "Ready to organize this folder.")
            self._save_preferences()
        except (OSError, ValueError) as error:
            self.preview_plan = []
            self._show_preview_error(f"Unable to preview folder:\n{error}")
            self.start_button.configure(state='disabled')
            self._set_state("Error", "Preview failed. Check folder permissions or choose another location.")
            messagebox.showerror("Preview unavailable", "The selected folder could not be read. Check that it exists and you have access to it.")

    def _show_preview_error(self, content):
        self._clear_preview_list()
        customtkinter.CTkLabel(self.preview_list, text=content, font=self.log_font, text_color=self.p["error"], anchor="w", justify="left").pack(fill="x", padx=12, pady=12)

    def _clear_preview_list(self):
        for child in self.preview_list.winfo_children():
            child.destroy()
        self.preview_rows = []

    def _selected_move_items(self):
        return [
            item for item in self.preview_plan
            if item["status"] == "move"
            and os.path.normcase(item["source_path"]) not in self._excluded_sources
        ]

    def _update_summary_cards(self):
        if not hasattr(self, "summary_cards"):
            return
        selected = self._selected_move_items()
        ignored = [item for item in self.preview_plan if item["status"] == "ignored"]
        no_rule = [item for item in selected if not item["has_rule"]]
        conflicts = [item for item in selected if item["conflict"]]
        total_size = sum(item["size"] for item in selected)
        values = [
            str(len(selected)),
            str(len(no_rule)),
            str(len(conflicts)),
            str(len(ignored)),
            _format_size(total_size) if selected else "0 B",
        ]
        for label, value in zip(self.summary_cards, values):
            label.configure(text=value)

    def _on_preview_toggle(self):
        for row in self.preview_rows:
            path = os.path.normcase(row["item"]["source_path"])
            if row["check"].get():
                self._excluded_sources.discard(path)
            else:
                self._excluded_sources.add(path)
        self._update_summary_cards()

    def refresh_preview(self):
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            messagebox.showinfo("Preview", "Select a valid folder before refreshing the preview.")
            return
        self._load_folder(directory)

    def _measure_font(self):
        if self._measure_fontobj is not None:
            return self._measure_fontobj
        try:
            import tkinter.font as tkfont
            if isinstance(self.log_font, customtkinter.CTkFont):
                self._measure_fontobj = tkfont.Font(
                    self.root, family=self.log_font.cget("family"), size=self.log_font.cget("size")
                )
            else:
                self._measure_fontobj = tkfont.Font(self.root, family="Consolas", size=10)
        except Exception:
            self._measure_fontobj = ("Consolas", 10)
        return self._measure_fontobj

    def _ellipsize(self, text, max_width):
        if not text or max_width <= 12:
            return text
        try:
            font = self._measure_font()
            available = max(12, max_width - 4)
            if font.measure(text) <= available:
                return text
            trimmed = text
            while trimmed and font.measure(trimmed + "…") > available:
                trimmed = trimmed[:-1]
            return trimmed + "…" if trimmed else "…"
        except Exception:
            return text

    def _on_preview_resize(self, event):
        if not self.preview_plan:
            return
        if abs(event.width - self._preview_last_width) < 20:
            return
        self._preview_last_width = event.width
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        self._resize_job = self.root.after(60, self._debounced_preview_rerender)

    def _debounced_preview_rerender(self):
        self._resize_job = None
        if self.current_directory and os.path.isdir(self.current_directory):
            self._show_preview(self.current_directory)

    def _show_preview(self, directory):
        self.current_directory = directory
        self._clear_preview_list()
        move_items = sorted(
            [item for item in self.preview_plan if item["status"] == "move"],
            key=lambda item: item["filename"].lower(),
        )
        query = self.search_var.get().strip().lower()
        for item in move_items:
            if query and query not in item["filename"].lower():
                continue
            self._preview_list_row(item)
        self._update_summary_cards()

    def _preview_list_row(self, item):
        row_frame = customtkinter.CTkFrame(self.preview_list, fg_color="transparent")
        row_frame.pack(fill="x", pady=2, padx=4)
        row_frame.grid_columnconfigure(1, weight=1)
        row_frame.grid_columnconfigure(3, weight=1)

        total_width = self.preview_list.winfo_width() or 760
        checkbox_w = 30
        size_w = 70
        flags_w = 86
        padx_total = 6 + 2 + 8 + 4 + 4 + 4 + 8
        dest_w = max(110, int(total_width * 0.26))
        name_w = max(80, total_width - checkbox_w - size_w - flags_w - dest_w - padx_total)

        is_excluded = os.path.normcase(item["source_path"]) in self._excluded_sources
        check_var = tk.BooleanVar(value=not is_excluded)
        check = customtkinter.CTkCheckBox(
            row_frame,
            text="",
            variable=check_var,
            command=self._on_preview_toggle,
            width=checkbox_w,
            height=24,
            checkbox_width=18,
            checkbox_height=18,
        )
        check.grid(row=0, column=0, sticky="w", padx=(6, 2))
        name_label = customtkinter.CTkLabel(
            row_frame, text=self._ellipsize(item["filename"], name_w),
            font=self.log_font, text_color=self.p["text"], anchor="w",
            width=name_w, justify="left",
        )
        name_label.grid(row=0, column=1, sticky="w", padx=(0, 8))
        Tooltip(name_label, item["filename"])
        customtkinter.CTkLabel(
            row_frame, text=_format_size(item["size"]), font=self.log_font,
            text_color=self.p["muted"], width=size_w, anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=4)
        dest_text = f"→ {os.path.relpath(item['destination_path'], self.current_directory)}"
        dest_label = customtkinter.CTkLabel(
            row_frame, text=self._ellipsize(dest_text, dest_w),
            font=self.log_font, text_color=self.p["muted"],
            width=dest_w, anchor="w", justify="left",
        )
        dest_label.grid(row=0, column=3, sticky="w", padx=(4, 4))
        Tooltip(dest_label, dest_text)
        flags = []
        if not item["has_rule"]:
            flags.append(("NO RULE", self.p["warning"]))
        if item["conflict"]:
            flags.append(("RENAME", self.p["error"]))
        if flags:
            flag_text = " ".join(name for name, _ in flags)
            customtkinter.CTkLabel(
                row_frame, text=flag_text, font=self.log_font,
                text_color=flags[0][1], width=flags_w, anchor="w",
            ).grid(row=0, column=4, sticky="e", padx=(4, 8))
        self.preview_rows.append({"check": check_var, "item": item, "name_label": name_label})

    def _rebuild_preview_rows(self):
        if not self.preview_plan:
            return
        if self.current_directory and os.path.isdir(self.current_directory):
            self._show_preview(self.current_directory)

    def _save_preferences(self):
        self.settings["preferences"].update({
            "recursive": self.recursive_var.get(),
            "notify": self.notify_var.get(),
            "autostart": self.autostart_var.get(),
            "minimize_to_tray": self.tray_var.get(),
            "last_folder": self.directory_path.get(),
            "theme": self.theme_var.get(),
        })
        save_settings(self.settings)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
                if self.autostart_var.get():
                    if getattr(sys, "frozen", False):
                        command = f'"{sys.executable}"'
                    else:
                        command = f'"{sys.executable}" "{os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))}"'
                    winreg.SetValueEx(key, "FLCLFileOrganizer", 0, winreg.REG_SZ, command)
                else:
                    try: winreg.DeleteValue(key, "FLCLFileOrganizer")
                    except FileNotFoundError: pass
        except OSError: pass

    def pause_action(self):
        if not self.monitor_thread or not self.monitor_thread.is_alive(): return
        self.pause_event.clear() if self.pause_event.is_set() else self.pause_event.set()
        self.pause_button.configure(text="Pause" if not self.pause_event.is_set() else "Resume")
        self._set_state("Monitoring", "Monitoring resumed." if not self.pause_event.is_set() else "Monitoring paused.")
        self._queue_log("Monitoring resumed." if not self.pause_event.is_set() else "Monitoring paused.")

    def undo_action(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            messagebox.showwarning("Monitoring active", "Stop monitoring before undoing the last run.")
            return
        self.undo_button.configure(state="disabled")
        self._set_state("Stopped", "Restoring the previous organization run.")
        self.undo_thread = threading.Thread(target=undo_last_run, args=(self._queue_log,), daemon=True)
        self.undo_thread.start()
        self.root.after(100, self._finish_undo)

    def _finish_undo(self):
        if self.undo_thread.is_alive(): self.root.after(100, self._finish_undo); return
        self.undo_button.configure(state="normal" if has_history() else "disabled")

    def open_settings(self):
        dialog = customtkinter.CTkToplevel(self.root)
        dialog.title("Rules and Filters")
        dialog.geometry("680x540")
        dialog.transient(self.root)
        dialog.grab_set()
        working = copy.deepcopy(self.settings)
        customtkinter.CTkLabel(dialog, text="Rules: category = destination folder").pack(padx=12, pady=(12, 4), anchor="w")
        rules_box = customtkinter.CTkTextbox(dialog, height=130)
        rules_box.pack(fill="x", padx=12)
        rules_box.insert("1.0", "\n".join(f"{name}: {', '.join(values)}" for name, values in working["rules"].items()))
        customtkinter.CTkLabel(dialog, text="Ignored extensions, patterns and folders (comma separated)").pack(padx=12, pady=(12, 4), anchor="w")
        filters_box = customtkinter.CTkTextbox(dialog, height=90)
        filters_box.pack(fill="x", padx=12)
        filters = working["filters"]
        filters_box.insert("1.0", f"extensions: {', '.join(filters.get('ignored_extensions', []))}\npatterns: {', '.join(filters.get('ignored_patterns', []))}\nfolders: {', '.join(filters.get('ignored_folders', []))}")
        hidden = tk.BooleanVar(value=filters.get("ignore_hidden", True))
        customtkinter.CTkCheckBox(dialog, text="Ignore hidden files", variable=hidden).pack(padx=12, pady=8, anchor="w")
        customtkinter.CTkButton(dialog, text="SAVE & CLOSE", command=lambda: self._save_settings_dialog(dialog, working, rules_box, filters_box, hidden), fg_color=self.p["accent"], hover_color=self.p["accent_soft"]).pack(padx=12, pady=12, fill="x")

    def _save_settings_dialog(self, dialog, settings, rules_box, filters_box, hidden):
        rules = {}
        for line in rules_box.get("1.0", "end").splitlines():
            if ":" in line:
                name, values = line.split(":", 1); rules[name.strip()] = [item.strip().lower() for item in values.split(",") if item.strip()]
        settings["rules"] = rules
        values = dict(line.split(":", 1) for line in filters_box.get("1.0", "end").splitlines() if ":" in line)
        settings["filters"] = {"ignore_hidden": hidden.get(), "min_size_kb": settings["filters"].get("min_size_kb", 0), "ignored_extensions": [item.strip() for item in values.get("extensions", "").split(",") if item.strip()], "ignored_patterns": [item.strip() for item in values.get("patterns", "").split(",") if item.strip()], "ignored_folders": [item.strip() for item in values.get("folders", "").split(",") if item.strip()]}
        save_settings(settings); self.settings = settings; dialog.destroy()
        if os.path.isdir(self.directory_path.get()): self._load_folder(self.directory_path.get())

    def open_reports(self):
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            messagebox.showinfo("REPORTS", "Select a valid folder before opening the report.")
            return

        report = generate_report(directory)
        dialog = customtkinter.CTkToplevel(self.root)
        dialog.title("Organization Report")
        dialog.geometry("820x620")
        dialog.transient(self.root)
        dialog.grab_set()

        export_bar = customtkinter.CTkFrame(dialog, fg_color="transparent")
        export_bar.pack(fill="x", padx=12, pady=(12, 0))
        export_bar.grid_columnconfigure(0, weight=1)
        customtkinter.CTkLabel(export_bar, text="Organization Report", font=self.main_font, anchor="w").grid(row=0, column=0, sticky="w")
        csv_button = customtkinter.CTkButton(export_bar, text="Export CSV", command=lambda: self._export_report_csv(dialog, report), font=self.log_font, width=100, height=30, fg_color=self.p["panel"], hover_color=self.p["surface"], text_color=self.p["text"])
        csv_button.grid(row=0, column=1, padx=(0, 8))
        html_button = customtkinter.CTkButton(export_bar, text="Export HTML", command=lambda: self._export_report_html(dialog, report), font=self.log_font, width=100, height=30, fg_color=self.p["panel"], hover_color=self.p["surface"], text_color=self.p["text"])
        html_button.grid(row=0, column=2)
        Tooltip(csv_button, "Save the report as a CSV file.")
        Tooltip(html_button, "Save an HTML page with the report.")

        summary = customtkinter.CTkFrame(dialog, fg_color="transparent")
        summary.pack(fill="x", padx=12, pady=(12, 8))
        metrics = [
            ("Files organized", str(report["organized_files"])),
            ("Top category", report["popular_categories"][0]["name"] if report["popular_categories"] else "None"),
            ("Errors", str(len(report["errors"]))),
        ]
        for index, (label, value) in enumerate(metrics):
            frame = customtkinter.CTkFrame(summary, corner_radius=8)
            frame.grid(row=0, column=index, sticky="ew", padx=(0, 8), ipadx=8, ipady=8)
            customtkinter.CTkLabel(frame, text=label, font=self.log_font, anchor="w").pack(fill="x", padx=10, pady=(8, 0))
            customtkinter.CTkLabel(frame, text=value, font=self.main_font).pack(fill="x", padx=10, pady=(0, 8))
        summary.grid_columnconfigure((0, 1, 2), weight=1)

        bar_frame = customtkinter.CTkFrame(dialog, fg_color="transparent")
        bar_frame.pack(fill="x", padx=12, pady=(0, 8))
        customtkinter.CTkLabel(bar_frame, text="Most used categories", font=self.log_font, anchor="w").pack(anchor="w", pady=(0, 4))
        self._render_report_bars(bar_frame, report)

        text_box = customtkinter.CTkTextbox(dialog, wrap="word", height=180, fg_color=self.p["surface"], border_color=self.p["border"], text_color=self.p["text"])
        text_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        text_box.configure(state='normal')

        lines = [
            "FILES ORGANIZED:",
            f"{report['organized_files']}",
            "",
            "MOST USED CATEGORIES:",
        ]
        if report["popular_categories"]:
            for item in report["popular_categories"][:5]:
                lines.append(f"- {item['name']}: {item['count']} file(s)")
        else:
            lines.append("- No categorised files yet")

        lines.extend(["", "ERRORS:"])
        if report["errors"]:
            for error in report["errors"][:10]:
                lines.append(f"- {error}")
        else:
            lines.append("- No recorded errors")

        lines.extend(["", "SPACE OCCUPIED BY CATEGORY:"])
        if report["space_by_category"]:
            for item in report["space_by_category"][:5]:
                lines.append(f"- {item['name']}: {item['size_human']}")
        else:
            lines.append("- No files measured yet")

        lines.extend(["", "HISTORICAL OPERATIONS:"])
        if report["recent_history"]:
            for entry in report["recent_history"][-10:]:
                timestamp = entry.get("timestamp", "unknown")
                files = ", ".join(entry.get("files", [])) or "no files"
                lines.append(f"- {timestamp}: {entry.get('count', 0)} file(s) [{files}]")
        else:
            lines.append("- No recorded operations")

        text_box.insert("1.0", "\n".join(lines))
        text_box.configure(state='disabled')

    def _render_report_bars(self, parent, report):
        canvas = tk.Canvas(parent, height=150, bg=self.p["panel"], highlightthickness=0)
        canvas.pack(fill="x")
        top = report["popular_categories"][:8]
        if not top:
            canvas.create_text(10, 10, anchor="nw", text="No categorised files yet.", fill=self.p["muted"], font=("Segoe UI", 10))
            return
        max_count = max(item["count"] for item in top) or 1
        label_width = 160
        available = canvas.winfo_width() - label_width - 60
        bar_max_width = available if available > 100 else 500
        row_height = 18
        for index, item in enumerate(top):
            y = 10 + index * row_height
            canvas.create_text(10, y + 6, anchor="w", text=item["name"], fill=self.p["text"], font=("Segoe UI", 9))
            bar_width = max(2, int((item["count"] / max_count) * bar_max_width))
            color = self.p["accent"] if index == 0 else self.p["accent_soft"]
            canvas.create_rectangle(label_width, y, label_width + bar_width, y + 12, fill=color, outline="")
            canvas.create_text(label_width + bar_width + 6, y + 6, anchor="w", text=str(item["count"]), fill=self.p["muted"], font=("Segoe UI", 9))

    def _export_report_csv(self, dialog, report):
        import csv
        path = filedialog.asksaveasfilename(parent=dialog, title="Export report as CSV", defaultextension=".csv", filetypes=[("CSV files", "*.csv")], initialfile="report.csv")
        if not path:
            return
        counts = {item["name"]: item["count"] for item in report["popular_categories"]}
        size_map = {item["name"]: item for item in report["space_by_category"]}
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["FLCL File Organizer - Report"])
            writer.writerow(["Files organized", report["organized_files"]])
            writer.writerow(["Errors", len(report["errors"])])
            writer.writerow([])
            writer.writerow(["Category", "Files", "Size (bytes)", "Size (human)"])
            for name, count in counts.items():
                size = size_map.get(name, {"size_bytes": 0, "size_human": "0 B"})
                writer.writerow([name, count, size["size_bytes"], size["size_human"]])
            writer.writerow([])
            writer.writerow(["Timestamp", "Files", "Names"])
            for entry in report["recent_history"]:
                writer.writerow([entry.get("timestamp", "unknown"), entry.get("count", 0), "; ".join(entry.get("files", []))])
        messagebox.showinfo("Export", f"Report saved to:\n{path}")

    def _export_report_html(self, dialog, report):
        path = filedialog.asksaveasfilename(parent=dialog, title="Export report as HTML", defaultextension=".html", filetypes=[("HTML files", "*.html"), ("All files", "*.*")], initialfile="report.html")
        if not path:
            return
        counts = {item["name"]: item["count"] for item in report["popular_categories"]}
        size_map = {item["name"]: item["size_human"] for item in report["space_by_category"]}
        names = sorted({*counts.keys(), *size_map.keys()})
        max_count = max(counts.values()) if counts else 1
        rows = []
        for name in names:
            width = int((counts.get(name, 0) / max_count) * 100)
            rows.append(
                f'<div class="cat"><span>{name}</span><div class="bar"><div class="fill" style="width:{width}%"></div></div>'
                f'<span class="count">{counts.get(name, 0)} file(s) · {size_map.get(name, "0 B")}</span></div>'
            )
        errors = "".join(f"<li>{error}</li>" for error in report["errors"][:20]) or "<li>No recorded errors</li>"
        history = "".join(
            f"<li>{entry.get('timestamp', 'unknown')} — {entry.get('count', 0)} file(s) [{', '.join(entry.get('files', []))}]</li>"
            for entry in report["recent_history"][:20]
        ) or "<li>No recorded operations</li>"
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FLCL File Organizer - Report</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #101418; color: #E8EEF7; margin: 24px; }}
h1 {{ color: {self.p["accent"]}; }}
.metrics {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }}
.metric {{ background: #20262C; border: 1px solid #343C44; border-radius: 8px; padding: 12px 20px; }}
.metric b {{ display: block; font-size: 20px; }}
.cat {{ display: flex; align-items: center; gap: 12px; margin: 6px 0; }}
.cat > span:first-child {{ min-width: 160px; }}
.bar {{ flex: 1; background: #20262C; border-radius: 6px; height: 14px; }}
.fill {{ height: 14px; border-radius: 6px; background: {self.p["accent"]}; }}
.count {{ min-width: 160px; color: #A9B4C0; }}
h2 {{ margin-top: 24px; color: {self.p["warning"]}; }}
ul {{ background: #181C20; padding: 12px 24px; border-radius: 8px; }}
</style>
</head>
<body>
<h1>FLCL File Organizer</h1>
<div class="metrics">
<div class="metric">Files organized<b>{report["organized_files"]}</b></div>
<div class="metric">Top category<b>{report["popular_categories"][0]["name"] if report["popular_categories"] else "None"}</b></div>
<div class="metric">Errors<b>{len(report["errors"])}</b></div>
</div>
<h2>Most used categories</h2>
{''.join(rows) or '<p>No categorised files yet</p>'}
<h2>Errors</h2>
<ul>{errors}</ul>
<h2>Recent operations</h2>
<ul>{history}</ul>
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(html)
        messagebox.showinfo("Export", f"Report saved to:\n{path}")

    def _close_window(self):
        if self.tray_var.get() and pystray:
            self.root.withdraw()
            if not self.tray_icon:
                image = Image.open(resource_path("icon.png"))
                menu = pystray.Menu(pystray.MenuItem("Restore", lambda icon, item: self.root.after(0, self.root.deiconify)), pystray.MenuItem("Exit", lambda icon, item: self.root.after(0, self._shutdown)))
                self.tray_icon = pystray.Icon("FLCL File Organizer", image, "FLCL File Organizer", menu)
                threading.Thread(target=self.tray_icon.run, daemon=True).start()
            return
        self._shutdown()

    def _shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_event.set()
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        if self.tray_icon:
            self.tray_icon.stop()
        try:
            self.root.quit()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def start_action(self):
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            messagebox.showerror("Folder not available", "Select an existing folder before starting the organizer.")
            return
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        selected = self._selected_move_items()
        if not selected:
            messagebox.showinfo("Nothing to organize", "No files are selected to move. Uncheck rows to exclude them from the organization, then refresh the preview.")
            return
        total_size = sum(item["size"] for item in selected)
        categories = sorted({item["destination_folder"] for item in selected})
        no_rule = [item for item in selected if not item["has_rule"]]
        conflicts = [item for item in selected if item["conflict"]]
        confirm_lines = [
            f"Move {len(selected)} file(s) ({_format_size(total_size)}) into {len(categories)} category folder(s)?",
        ]
        if no_rule:
            confirm_lines.append(f"Note: {len(no_rule)} file(s) have no matching rule and will go to 'Others'.")
        if conflicts:
            confirm_lines.append(f"Note: {len(conflicts)} file(s) will be renamed to avoid collisions.")
        if self.recursive_var.get():
            confirm_lines.append("Subfolders will be included.")
        if not messagebox.askyesno("Confirm organization", "\n".join(confirm_lines)):
            return

        self.moved_count = 0
        self.error_count = 0
        self.moved_label.configure(text="Files moved: 0")
        self.error_label.configure(text="Errors: 0")

        self._set_state("Scanning", "Scanning the selected folder for files to organize.")
        self.start_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.pause_button.configure(state='normal', text='Pause')

        self.stop_event.clear()
        self.pause_event.clear()
        self.monitor_thread = threading.Thread(target=start_monitoring, args=(directory, self.stop_event, self._queue_log, self.pause_event, self.recursive_var.get()), kwargs={"excluded_paths": self._excluded_sources}, daemon=True)
        self.monitor_thread.start()
        self.root.after(250, self._refresh_monitoring_state)

    def _refresh_monitoring_state(self):
        if self._shutting_down:
            return
        if self.monitor_thread and self.monitor_thread.is_alive():
            self._set_state("Monitoring", "Monitoring is active and waiting for new files.")
            self.root.after(250, self._refresh_monitoring_state)
            return
        if self.current_state == "Scanning":
            self._set_state("Error", "Monitoring could not start. Please check the folder and try again.")

    def stop_action(self):
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self._finish_stop()
            return

        self._set_state("Stopped", "Stopping the active monitoring session.")
        self.stop_event.set()
        self.start_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.stop_button.configure(state='disabled', text='Stopping...')
        self.pause_button.configure(state='disabled')
        self.root.after(100, self._wait_for_monitoring_stop)

    def _wait_for_monitoring_stop(self):
        if self._shutting_down:
            return
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.root.after(100, self._wait_for_monitoring_stop)
            return
        self._finish_stop()

    def _finish_stop(self):
        self._set_state("Stopped", "Ready for the next scan.")
        self.start_button.configure(state='normal')
        self.select_button.configure(state='normal')
        self.stop_button.configure(state='disabled', text='Stop')
        self.pause_button.configure(state='disabled', text='Pause')
        self.undo_button.configure(state='normal' if has_history() else 'disabled')