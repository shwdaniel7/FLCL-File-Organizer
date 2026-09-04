# src/gui.py

import customtkinter
from tkinter import filedialog, messagebox
import threading
import queue
import os
import sys
from PIL import Image
from .organizer import build_preview, has_history, start_monitoring, undo_last_run

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
        self.root.geometry("900x550")
        self.root.resizable(False, False)

        # --- Instance variables ---
        self.directory_path = customtkinter.StringVar()
        self.monitor_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.preview_plan = []
        self.undo_thread = None
        self.gif_frames = []
        self.gif_duration = 100
        self.gif_label = None

        # --- Setup Window and Assets ---
        self._setup_window_icon()
        self._load_font()
        self._load_gif_frames()

        # --- Layout Configuration ---
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_rowconfigure(0, weight=1)

        # --- Left Frame (GIF) ---
        left_frame = customtkinter.CTkFrame(self.root, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.gif_label = customtkinter.CTkLabel(left_frame, text="")
        self.gif_label.pack(expand=True)

        # --- Right Frame (Controls) ---
        right_frame = customtkinter.CTkFrame(self.root, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        right_frame.grid_rowconfigure(2, weight=3)
        right_frame.grid_rowconfigure(3, weight=1)

        # --- Widgets ---
        folder_label = customtkinter.CTkLabel(right_frame, text="FOLDER TO ORGANIZE:", font=self.main_font, text_color=COLOR_TEXT_WHITE)
        folder_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        folder_entry = customtkinter.CTkEntry(right_frame, textvariable=self.directory_path, state='readonly', font=self.main_font, width=300, fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER)
        folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        self.select_button = customtkinter.CTkButton(right_frame, text="Select...", command=self.select_folder, font=self.main_font)
        self.select_button.grid(row=1, column=1, sticky="ew")

        self.preview_box = customtkinter.CTkTextbox(right_frame, state='disabled', font=self.log_font, wrap="word", fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER, text_color=COLOR_TEXT_WHITE)
        self.preview_box.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(20, 10))

        self.log_box = customtkinter.CTkTextbox(right_frame, state='disabled', font=self.log_font, wrap="word", fg_color=COLOR_WIDGET_BG, border_color=COLOR_BORDER, text_color=COLOR_YELLOW)
        self.log_box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 10))

        self.start_button = customtkinter.CTkButton(right_frame, text="ORGANIZE", command=self.start_action, state='disabled', font=self.main_font, fg_color=COLOR_PINK, hover_color="#C42A7A")
        self.start_button.grid(row=4, column=0, sticky="ew", padx=(0, 10))

        self.stop_button = customtkinter.CTkButton(right_frame, text="STOP", command=self.stop_action, state='disabled', font=self.main_font)
        self.stop_button.grid(row=4, column=1, sticky="ew")

        self.undo_button = customtkinter.CTkButton(right_frame, text="UNDO LAST RUN", command=self.undo_action, state='disabled', font=self.main_font)
        self.undo_button.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        # --- Initial State ---
        if self.gif_frames:
            self._animate_gif(0)
        self.root.after(100, self._process_log_queue)
        self.log("WELCOME, SPACE-HEAD! SELECT A FOLDER TO GET STARTED.")

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
                self.log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_log_queue)

    def select_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self.directory_path.set(directory)
            try:
                self.preview_plan = build_preview(directory)
            except (OSError, ValueError) as error:
                self.preview_plan = []
                self._set_preview(f"Unable to preview folder:\n{error}")
                self.start_button.configure(state='disabled')
                messagebox.showerror("PREVIEW ERROR", f"Could not scan the selected folder.\n{error}")
                return

            self._show_preview(directory)
            self.start_button.configure(state='normal')
            self.log(f"FOLDER SELECTED: {directory}")

    def _set_preview(self, content):
        self.preview_box.configure(state='normal')
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("end", content)
        self.preview_box.configure(state='disabled')

    def _show_preview(self, directory):
        move_items = [item for item in self.preview_plan if item["status"] == "move"]
        no_rule_items = [item for item in move_items if not item["has_rule"]]
        conflict_items = [item for item in move_items if item["conflict"]]
        ignored_items = [item for item in self.preview_plan if item["status"] == "ignored"]

        lines = [
            f"PREVIEW: {len(self.preview_plan)} file(s) found",
            f"Files to organize: {len(move_items)}",
            f"Without matching rule: {len(no_rule_items)}",
            f"Name conflicts: {len(conflict_items)}",
            f"Ignored (no extension): {len(ignored_items)}",
            "",
            "DESTINATION PLAN:",
        ]
        for item in move_items:
            relative_destination = os.path.relpath(item["destination_path"], directory)
            flags = []
            if not item["has_rule"]:
                flags.append("NO RULE")
            if item["conflict"]:
                flags.append("RENAME")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"{item['filename']} -> {relative_destination}{suffix}")

        self._set_preview("\n".join(lines))

    def start_action(self):
        directory = self.directory_path.get()
        if not os.path.isdir(directory):
            messagebox.showerror("ATOMIC ERROR", "The selected directory is not valid, baka!")
            return
        if self.monitor_thread and self.monitor_thread.is_alive():
            return

        self.start_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.stop_button.configure(state='normal')

        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=start_monitoring, args=(directory, self.stop_event, self._queue_log), daemon=True)
        self.monitor_thread.start()

    def stop_action(self):
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self._finish_stop()
            return

        self.stop_event.set()
        self.start_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.stop_button.configure(state='disabled', text='STOPPING...')
        self.root.after(100, self._wait_for_monitoring_stop)

    def _wait_for_monitoring_stop(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.root.after(100, self._wait_for_monitoring_stop)
            return
        self._finish_stop()

    def _finish_stop(self):
        self.start_button.configure(state='normal')
        self.undo_button.configure(state='normal' if has_history() else 'disabled')
        self.select_button.configure(state='normal')
        self.stop_button.configure(state='disabled', text='STOP')

    def undo_action(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            messagebox.showwarning("MONITORING ACTIVE", "Stop monitoring before undoing the last run.")
            return
        if self.undo_thread and self.undo_thread.is_alive():
            return
        self.undo_button.configure(state='disabled')
        self.undo_thread = threading.Thread(target=undo_last_run, args=(self._queue_log,), daemon=True)
        self.undo_thread.start()
        self.root.after(100, self._finish_undo)

    def _finish_undo(self):
        if self.undo_thread and self.undo_thread.is_alive():
            self.root.after(100, self._finish_undo)
            return
        self.undo_button.configure(state='normal' if has_history() else 'disabled')
        directory = self.directory_path.get()
        if os.path.isdir(directory):
            try:
                self.preview_plan = build_preview(directory)
                self._show_preview(directory)
            except OSError:
                pass