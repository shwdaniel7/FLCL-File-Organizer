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
from .organizer import build_preview, generate_report, has_history, load_settings, load_settings_from_file, save_settings, start_monitoring, undo_last_run

def resource_path(relative_path):
    """Return a path to a bundled resource in source and PyInstaller modes."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("blue")

COLOR_PINK = "#FF3399"
COLOR_YELLOW = "#F6E500"
COLOR_WIDGET_BG = "#2B2B2B"
COLOR_BORDER = "#565B5E"
COLOR_TEXT_WHITE = "#DCE4EE"

class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FLCL - File Logical Classifier Launcher")
        self.root.geometry("1120x720")
        self.root.minsize(960, 640)
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
        self.pause_event = threading.Event()
        self.undo_thread = None
        self.tray_icon = None
        self.gif_frames = []
        self.gif_duration = 100
        self.gif_label = None

        # --- Setup Window and Assets ---
        self._setup_window_icon()
        self._load_font()
        self._load_gif_frames()

        # --- Layout Configuration ---
        self.root.grid_columnconfigure(0, weight=1, minsize=380)
        self.root.grid_columnconfigure(1, weight=2, minsize=520)
        self.root.grid_rowconfigure(0, weight=1)

        # --- Left Frame (GIF) ---
        left_frame = customtkinter.CTkFrame(self.root, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.gif_label = customtkinter.CTkLabel(left_frame, text="")
        self.gif_label.pack(expand=True)

        # --- Right Frame (Controls) ---
        right_frame = customtkinter.CTkFrame(self.root, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        right_frame.grid_columnconfigure(0, weight=3)
        right_frame.grid_columnconfigure(1, weight=1, minsize=140)
        right_frame.grid_rowconfigure(2, weight=3)
        right_frame.grid_rowconfigure(3, weight=1)
        right_frame.grid_rowconfigure(3, minsize=56)

        # --- Widgets ---
        folder_label = customtkinter.CTkLabel(right_frame, text="FOLDER TO ORGANIZE:", font=self.main_font, text_color=COLOR_TEXT_WHITE)
        folder_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        folder_entry = customtkinter.CTkEntry(right_frame, textvariable=self.directory_path, state='readonly', font=self.main_font, height=42, fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER)
        folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        self.select_button = customtkinter.CTkButton(right_frame, text="Select...", command=self.select_folder, font=self.main_font, height=42)
        self.select_button.grid(row=1, column=1, sticky="ew")

        self.preview_box = customtkinter.CTkTextbox(right_frame, state='disabled', font=self.log_font, wrap="word", fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER, text_color=COLOR_TEXT_WHITE)
        self.preview_box.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(20, 10))

        self.log_box = customtkinter.CTkTextbox(right_frame, state='disabled', font=self.log_font, wrap="word", fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER, text_color=COLOR_YELLOW)
        self.log_box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 12))

        self.start_button = customtkinter.CTkButton(right_frame, text="START SWING", command=self.start_action, state='disabled', font=self.main_font, height=48, fg_color=COLOR_PINK, hover_color="#C42A7A")
        self.start_button.grid(row=4, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))

        self.stop_button = customtkinter.CTkButton(right_frame, text="STOP", command=self.stop_action, state='disabled', font=self.main_font, height=48)
        self.stop_button.grid(row=4, column=1, sticky="ew", pady=(0, 8))

        self.pause_button = customtkinter.CTkButton(right_frame, text="PAUSE", command=self.pause_action, state='disabled', font=self.main_font, height=42)
        self.pause_button.grid(row=5, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.undo_button = customtkinter.CTkButton(right_frame, text="UNDO LAST RUN", command=self.undo_action, state='disabled', font=self.main_font, height=42)
        self.undo_button.grid(row=5, column=1, sticky="ew", pady=(4, 0))
        self.settings_button = customtkinter.CTkButton(right_frame, text="EDIT RULES & FILTERS", command=self.open_settings, font=self.main_font, height=42)
        self.settings_button.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.report_button = customtkinter.CTkButton(right_frame, text="REPORTS", command=self.open_reports, font=self.main_font, height=42)
        self.report_button.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        options = customtkinter.CTkFrame(right_frame, fg_color="transparent")
        options.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        customtkinter.CTkCheckBox(options, text="Include subfolders", variable=self.recursive_var).pack(side="left", padx=(0, 8))
        customtkinter.CTkCheckBox(options, text="Notifications", variable=self.notify_var, command=self._save_preferences).pack(side="left", padx=(0, 8))
        customtkinter.CTkCheckBox(options, text="Start with Windows", variable=self.autostart_var, command=self._save_preferences).pack(side="left")
        customtkinter.CTkCheckBox(options, text="Minimize to tray", variable=self.tray_var, command=self._save_preferences).pack(side="left", padx=(8, 0))
        
        # --- Initial State ---
        if self.gif_frames:
            self._animate_gif(0)
        self.root.after(100, self._process_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self.log("WELCOME, SPACE-HEAD! SELECT A FOLDER TO GET STARTED.")
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
        if not self.gif_frames: return
        frame = self.gif_frames[frame_index]
        self.gif_label.configure(image=frame)
        next_frame_index = (frame_index + 1) % len(self.gif_frames)
        self.root.after(self.gif_duration, self._animate_gif, next_frame_index)

    def log(self, message):
        self.log_box.configure(state='normal')
        self.log_box.insert("end", f"> {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state='disabled')

    def _queue_log(self, message):
        """Queue worker messages so Tkinter is only updated on the UI thread."""
        self.log_queue.put(message)

    def _process_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log(message)
                if self.notify_var.get() and message.startswith("File moved:"):
                    self._notify("File organized", message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_log_queue)

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
            self._save_preferences()
        except (OSError, ValueError) as error:
            self.preview_plan = []
            self._set_preview(f"Unable to preview folder:\n{error}")
            self.start_button.configure(state='disabled')
            messagebox.showerror("PREVIEW ERROR", str(error))

    def _set_preview(self, content):
        if not hasattr(self, "preview_box"):
            return
        self.preview_box.configure(state='normal')
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("end", content)
        self.preview_box.configure(state='disabled')

    def _show_preview(self, directory):
        move_items = [item for item in self.preview_plan if item["status"] == "move"]
        ignored = [item for item in self.preview_plan if item["status"] == "ignored"]
        no_rule = [item for item in move_items if not item["has_rule"]]
        conflicts = [item for item in move_items if item["conflict"]]
        lines = [f"PREVIEW: {len(self.preview_plan)} file(s) found", f"Files to organize: {len(move_items)}", f"Without matching rule: {len(no_rule)}", f"Name conflicts: {len(conflicts)}", f"Ignored: {len(ignored)}", "", "DESTINATION PLAN:"]
        for item in move_items:
            relative = os.path.relpath(item["destination_path"], directory)
            flags = []
            if not item["has_rule"]: flags.append("NO RULE")
            if item["conflict"]: flags.append("RENAME")
            lines.append(f"{item['filename']} -> {relative}" + (f" [{', '.join(flags)}]" if flags else ""))
        self._set_preview("\n".join(lines))

    def _save_preferences(self):
        self.settings["preferences"].update({"recursive": self.recursive_var.get(), "notify": self.notify_var.get(), "autostart": self.autostart_var.get(), "minimize_to_tray": self.tray_var.get(), "last_folder": self.directory_path.get()})
        save_settings(self.settings)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
                if self.autostart_var.get():
                    command = f'"{sys.executable}" "{os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))}"'
                    winreg.SetValueEx(key, "FLCLFileOrganizer", 0, winreg.REG_SZ, command)
                else:
                    try: winreg.DeleteValue(key, "FLCLFileOrganizer")
                    except FileNotFoundError: pass
        except OSError: pass

    def pause_action(self):
        if not self.monitor_thread or not self.monitor_thread.is_alive(): return
        self.pause_event.clear() if self.pause_event.is_set() else self.pause_event.set()
        self.pause_button.configure(text="PAUSE" if not self.pause_event.is_set() else "RESUME")
        self._queue_log("Monitoring resumed." if not self.pause_event.is_set() else "Monitoring paused.")

    def undo_action(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            messagebox.showwarning("MONITORING ACTIVE", "Stop monitoring before undoing the last run.")
            return
        self.undo_button.configure(state="disabled")
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
        customtkinter.CTkButton(dialog, text="SAVE & CLOSE", command=lambda: self._save_settings_dialog(dialog, working, rules_box, filters_box, hidden), fg_color=COLOR_PINK, hover_color="#C42A7A").pack(padx=12, pady=12, fill="x")

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
        dialog.geometry("720x540")
        dialog.transient(self.root)
        dialog.grab_set()

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

        text_box = customtkinter.CTkTextbox(dialog, height=28, wrap="word", fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER, text_color=COLOR_TEXT_WHITE)
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
        if self.monitor_thread and self.monitor_thread.is_alive(): self.stop_event.set()
        if self.tray_icon: self.tray_icon.stop()
        self.root.destroy()

    def start_action(self):
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            messagebox.showerror("ATOMIC ERROR", "The selected directory is not valid, baka!")
            return
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        if self.recursive_var.get() and not messagebox.askyesno("INCLUDE SUBFOLDERS", "Organize files inside all subfolders?"):
            return

        self.start_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.pause_button.configure(state='normal', text='PAUSE')

        self.stop_event.clear()
        self.pause_event.clear()
        self.monitor_thread = threading.Thread(target=start_monitoring, args=(directory, self.stop_event, self._queue_log, self.pause_event, self.recursive_var.get()), daemon=True)
        self.monitor_thread.start()

    def stop_action(self):
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self._finish_stop()
            return

        self.stop_event.set()
        self.start_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.stop_button.configure(state='disabled', text='STOPPING...')
        self.pause_button.configure(state='disabled')
        self.root.after(100, self._wait_for_monitoring_stop)

    def _wait_for_monitoring_stop(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.root.after(100, self._wait_for_monitoring_stop)
            return
        self._finish_stop()

    def _finish_stop(self):
        self.start_button.configure(state='normal')
        self.select_button.configure(state='normal')
        self.stop_button.configure(state='disabled', text='STOP')
        self.pause_button.configure(state='disabled', text='PAUSE')
        self.undo_button.configure(state='normal' if has_history() else 'disabled')