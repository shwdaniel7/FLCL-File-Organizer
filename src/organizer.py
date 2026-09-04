# src/organizer.py

import os
import json
import time
import shutil
import sys
from datetime import datetime, timezone
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def resource_path(relative_path):
    """Return a path to a bundled resource in source and PyInstaller modes."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def history_path():
    """Return the persistent per-user path for organization history."""
    data_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.flcl-file-organizer")
    return os.path.join(data_dir, "FLCL-File-Organizer", "history.json")

def _load_history():
    try:
        with open(history_path(), "r", encoding="utf-8") as history_file:
            history = json.load(history_file)
            return history if isinstance(history, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []

def _save_history(history):
    file_path = history_path()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as history_file:
        json.dump(history, history_file, indent=2)

def _record_run(moves):
    if not moves:
        return
    history = _load_history()
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "moves": moves,
    })
    _save_history(history)

def _append_to_last_run(move):
    history = _load_history()
    if not history:
        _record_run([move])
        return
    history[-1].setdefault("moves", []).append(move)
    _save_history(history)

def has_history():
    return bool(_load_history())

def undo_last_run(log_callback):
    """Restore the files from the latest recorded organization run."""
    history = _load_history()
    if not history:
        log_callback("Nothing to undo.")
        return False

    last_run = history[-1]
    remaining_moves = []
    restored_count = 0
    for move in reversed(last_run.get("moves", [])):
        original_path = move["original"]
        destination_path = move["destination"]
        if not os.path.exists(destination_path):
            log_callback(f"UNDO SKIPPED: file not found '{destination_path}'")
            continue
        if os.path.exists(original_path):
            remaining_moves.append(move)
            log_callback(f"UNDO SKIPPED: original path already exists '{original_path}'")
            continue
        try:
            os.makedirs(os.path.dirname(original_path), exist_ok=True)
            shutil.move(destination_path, original_path)
            restored_count += 1
            log_callback(f"Restored: '{os.path.basename(original_path)}'")
        except OSError as error:
            remaining_moves.append(move)
            log_callback(f"ERROR undoing '{os.path.basename(destination_path)}': {error}")

    if remaining_moves:
        last_run["moves"] = list(reversed(remaining_moves))
    else:
        history.pop()
    _save_history(history)
    log_callback(f"Undo complete: {restored_count} file(s) restored.")
    return restored_count > 0

def _get_file_extension(filename, rules):
    """Find the longest configured suffix, including compound extensions."""
    lowered_filename = filename.lower()
    configured_extensions = {
        extension.lower()
        for extensions in rules.values()
        for extension in extensions
    }
    matching_extensions = [
        extension for extension in configured_extensions
        if lowered_filename.endswith(extension)
    ]
    if matching_extensions:
        return max(matching_extensions, key=len)
    return os.path.splitext(filename)[1].lower()

def _wait_for_stable_file(file_path, checks=3, interval=0.5, timeout=30):
    """Wait until a file keeps the same size across consecutive checks."""
    deadline = time.monotonic() + timeout
    previous_size = None
    stable_checks = 0

    while time.monotonic() < deadline:
        try:
            current_size = os.path.getsize(file_path)
        except OSError:
            return False

        if current_size == previous_size:
            stable_checks += 1
            if stable_checks >= checks:
                return True
        else:
            previous_size = current_size
            stable_checks = 0
        time.sleep(interval)

    return False

def _unique_destination_path(destination_path):
    """Return a non-conflicting path using the `name (n).ext` convention."""
    if not os.path.exists(destination_path):
        return destination_path

    directory = os.path.dirname(destination_path)
    filename = os.path.basename(destination_path)
    stem, extension = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{stem} ({counter}){extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

def load_rules():
    """Load organization rules from the application resources."""
    config_path = resource_path("config.json")
    with open(config_path, "r", encoding="utf-8") as config_file:
        return json.load(config_file)

def _classify_file(filename, rules):
    extension = _get_file_extension(filename, rules)
    if not extension:
        return None, extension, False

    for folder, extensions in rules.items():
        normalized_extensions = {item.lower() for item in extensions}
        if extension in normalized_extensions:
            return folder, extension, True
    return "Others", extension, False

def build_preview(monitored_dir, rules=None):
    """Build a move plan without changing any files on disk."""
    rules = rules or load_rules()
    preview = []

    for item_name in sorted(os.listdir(monitored_dir), key=str.lower):
        source_path = os.path.join(monitored_dir, item_name)
        if not os.path.isfile(source_path):
            continue
        if item_name.startswith('.') or item_name.startswith('~'):
            continue

        destination_folder, extension, has_rule = _classify_file(item_name, rules)
        if not destination_folder:
            preview.append({
                "filename": item_name,
                "status": "ignored",
                "reason": "No extension",
            })
            continue

        destination_dir = os.path.join(monitored_dir, destination_folder)
        destination_path = _unique_destination_path(os.path.join(destination_dir, item_name))
        preview.append({
            "filename": item_name,
            "extension": extension,
            "destination_folder": destination_folder,
            "destination_path": destination_path,
            "has_rule": has_rule,
            "conflict": destination_path != os.path.join(destination_dir, item_name),
            "status": "move",
        })

    return preview

def _process_and_move_file(file_path, monitored_dir, rules, log_callback):
    """
    Core logic to organize a single file based on the rules from config.json.
    """
    try:
        if not os.path.exists(file_path):
            return

        filename = os.path.basename(file_path)
        destination_folder_name, extension, _ = _classify_file(filename, rules)

        if not destination_folder_name or filename.startswith('.') or filename.startswith('~'):
            return

        destination_path = os.path.join(monitored_dir, destination_folder_name)
        
        if os.path.dirname(file_path) == destination_path:
            return

        if not os.path.exists(destination_path):
            os.makedirs(destination_path)
            log_callback(f"Folder created: {destination_folder_name}")
        
        final_destination_path = _unique_destination_path(os.path.join(destination_path, filename))
        
        shutil.move(file_path, final_destination_path)
        log_callback(f"File moved: '{filename}' -> '{os.path.basename(final_destination_path)}' in '{destination_folder_name}'")
        return {
            "original": file_path,
            "destination": final_destination_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log_callback(f"ERROR organizing {os.path.basename(file_path)}: {e}")
    return None

class OrganizerEventHandler(FileSystemEventHandler):
    """
    Handles file system events detected by Watchdog.
    """
    def __init__(self, monitored_dir, rules, log_callback):
        self.monitored_dir = monitored_dir
        self.rules = rules
        self.log = log_callback

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        self.log(f"New file detected: {filename}")
        if _wait_for_stable_file(event.src_path):
            move = _process_and_move_file(event.src_path, self.monitored_dir, self.rules, self.log)
            if move:
                _append_to_last_run(move)
        else:
            self.log(f"ERROR: Timed out waiting for '{filename}' to finish copying")

def run_initial_scan(monitored_dir, rules, log_callback):
    """
    Scans the monitored folder and organizes all existing files.
    """
    log_callback("Starting initial folder scan...")
    found_files = 0
    moves = []
    for item_name in os.listdir(monitored_dir):
        full_path = os.path.join(monitored_dir, item_name)
        if os.path.isfile(full_path):
            found_files += 1
            move = _process_and_move_file(full_path, monitored_dir, rules, log_callback)
            if move:
                moves.append(move)
    
    if found_files > 0:
        log_callback("Initial scan complete.")
    else:
        log_callback("No files to organize in the folder.")
    return moves

def start_monitoring(directory, stop_event, log_callback):
    """
    Main function for the monitoring thread. Runs the initial scan, then starts the observer.
    """
    rules = load_rules()
    
    moves = run_initial_scan(directory, rules, log_callback)
    _record_run(moves)

    event_handler = OrganizerEventHandler(directory, rules, log_callback)
    observer = Observer()
    observer.schedule(event_handler, directory, recursive=False)
    observer.start()
    log_callback(f"Real-time monitoring started. Waiting for new files...")

    try:
        while not stop_event.is_set():
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
        log_callback("Monitoring stopped.")