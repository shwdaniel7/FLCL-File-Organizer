# src/organizer.py

import os
import json
import time
import shutil
import sys
import fnmatch
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

def user_config_path():
    data_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.flcl-file-organizer")
    return os.path.join(data_dir, "FLCL-File-Organizer", "config.json")

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
    run_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "moves": [],
        "errors": [],
    }
    for move in moves:
        if not isinstance(move, dict):
            continue
        if "error" in move:
            run_record["errors"].append(move["error"])
        else:
            run_record["moves"].append(move)
    if not run_record["moves"] and not run_record["errors"]:
        return
    history.append(run_record)
    _save_history(history)

def _append_to_last_run(move):
    history = _load_history()
    if not history:
        _record_run([move])
        return
    if not isinstance(move, dict):
        _save_history(history)
        return
    if "error" in move:
        history[-1].setdefault("errors", []).append(move["error"])
    else:
        history[-1].setdefault("moves", []).append(move)
    _save_history(history)

def has_history():
    return bool(_load_history())


def _format_size(size_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def generate_report(monitored_dir, history=None):
    """Return a summary of organized files, category usage, errors and recent operations."""
    entries = history if history is not None else _load_history()
    organized_files = 0
    category_counts = {}
    category_sizes = {}
    errors = []
    recent_history = []

    for run in entries:
        if not isinstance(run, dict):
            continue
        run_errors = run.get("errors", [])
        if isinstance(run_errors, list):
            errors.extend(str(item) for item in run_errors)

        moves = run.get("moves", [])
        if isinstance(moves, list):
            recent_history.append({
                "timestamp": run.get("timestamp"),
                "files": [
                    os.path.basename(move.get("destination", "")) for move in moves if isinstance(move, dict)
                ][:5],
                "count": len(moves),
            })

        for move in moves:
            if not isinstance(move, dict):
                continue
            destination = move.get("destination")
            if destination:
                organized_files += 1
            category = move.get("category")
            if not category and destination:
                try:
                    relative = os.path.relpath(destination, monitored_dir)
                    parent_dir = os.path.dirname(relative)
                    category = os.path.basename(parent_dir) if parent_dir not in ("", ".") else "Root"
                except (TypeError, ValueError):
                    category = "Root"
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
                size = os.path.getsize(destination) if destination and os.path.exists(destination) else 0
                category_sizes[category] = category_sizes.get(category, 0) + size

    errors = list(dict.fromkeys(errors))
    popular_categories = [
        {"name": name, "count": count}
        for name, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    space_by_category = [
        {"name": name, "size_bytes": size, "size_human": _format_size(size)}
        for name, size in sorted(category_sizes.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "organized_files": organized_files,
        "popular_categories": popular_categories,
        "errors": errors,
        "space_by_category": space_by_category,
        "recent_history": recent_history[-10:][::-1],
    }

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

def _default_settings():
    return {
        "rules": {},
        "preferences": {
            "recursive": False,
            "notify": True,
            "autostart": False,
            "minimize_to_tray": False,
            "last_folder": "",
        },
        "filters": {
            "ignored_folders": [],
            "ignore_hidden": True,
            "min_size_kb": 0,
            "ignored_extensions": [],
            "ignored_patterns": [],
        },
    }

def _normalize_settings(raw_settings):
    settings = _default_settings()
    if "rules" in raw_settings:
        settings["rules"] = raw_settings.get("rules", {})
        settings["filters"].update(raw_settings.get("filters", {}))
        settings["preferences"].update(raw_settings.get("preferences", {}))
    else:
        settings["rules"] = raw_settings
    return settings

def load_settings():
    """Load user settings, falling back to the bundled legacy config."""
    config_file = user_config_path()
    if not os.path.isfile(config_file):
        config_file = resource_path("config.json")
    return load_settings_from_file(config_file)

def load_settings_from_file(config_file):
    with open(config_file, "r", encoding="utf-8") as config_handle:
        settings = json.load(config_handle)
    if not isinstance(settings, dict):
        raise ValueError("Configuration must be a JSON object.")
    return _normalize_settings(settings)

def save_settings(settings, destination=None):
    config_file = destination or user_config_path()
    parent_directory = os.path.dirname(config_file)
    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as config_handle:
        json.dump(_normalize_settings(settings), config_handle, indent=2)

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
    return load_settings()["rules"]

def _classify_file(filename, rules):
    extension = _get_file_extension(filename, rules)
    if not extension:
        return None, extension, False

    for folder, extensions in rules.items():
        normalized_extensions = {item.lower() for item in extensions}
        if extension in normalized_extensions:
            return folder, extension, True
    return "Others", extension, False

def _filter_reason(filename, file_path, filters):
    if filters.get("ignore_hidden", True) and filename.startswith('.'):
        return "Hidden file"
    ignored_extensions = {item.lower() for item in filters.get("ignored_extensions", [])}
    lowered_filename = filename.lower()
    if any(lowered_filename.endswith(extension) for extension in ignored_extensions):
        return "Ignored extension"
    if any(fnmatch.fnmatch(filename, pattern) for pattern in filters.get("ignored_patterns", [])):
        return "Ignored pattern"
    min_size_kb = float(filters.get("min_size_kb", 0) or 0)
    if min_size_kb > 0 and os.path.getsize(file_path) < min_size_kb * 1024:
        return "Below minimum size"
    return None

def _iter_files(monitored_dir, rules, filters, recursive):
    ignored_folders = {os.path.normcase(item) for item in filters.get("ignored_folders", [])}
    if not recursive:
        for item_name in os.listdir(monitored_dir):
            source_path = os.path.join(monitored_dir, item_name)
            if os.path.isfile(source_path):
                yield item_name, source_path
        return

    for current_dir, folder_names, file_names in os.walk(monitored_dir):
        folder_names[:] = [
            folder for folder in folder_names
            if os.path.normcase(folder) not in ignored_folders
            and not (current_dir == monitored_dir and folder in rules)
        ]
        for item_name in file_names:
            yield item_name, os.path.join(current_dir, item_name)

def build_preview(monitored_dir, rules=None, filters=None, recursive=False):
    """Build a move plan without changing any files on disk."""
    if rules is None:
        settings = load_settings()
        rules = settings["rules"]
        filters = settings["filters"]
    filters = filters or _default_settings()["filters"]
    preview = []

    files = sorted(_iter_files(monitored_dir, rules, filters, recursive), key=lambda item: item[0].lower())
    for item_name, source_path in files:
        if item_name.startswith('~'):
            continue
        reason = _filter_reason(item_name, source_path, filters)
        if reason:
            preview.append({"filename": item_name, "status": "ignored", "reason": reason})
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

def _process_and_move_file(file_path, monitored_dir, rules, log_callback, filters=None):
    """
    Core logic to organize a single file based on the rules from config.json.
    """
    try:
        if not os.path.exists(file_path):
            return

        filename = os.path.basename(file_path)
        reason = _filter_reason(filename, file_path, filters or _default_settings()["filters"])
        if reason:
            return None
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
            "category": destination_folder_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        error_message = f"ERROR organizing {os.path.basename(file_path)}: {e}"
        log_callback(error_message)
        return {
            "original": file_path,
            "destination": file_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error_message,
        }

class OrganizerEventHandler(FileSystemEventHandler):
    """
    Handles file system events detected by Watchdog.
    """
    def __init__(self, monitored_dir, rules, log_callback, filters=None, pause_event=None):
        self.monitored_dir = monitored_dir
        self.rules = rules
        self.log = log_callback
        self.filters = filters or _default_settings()["filters"]
        self.pause_event = pause_event

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        self.log(f"New file detected: {filename}")
        while self.pause_event and self.pause_event.is_set():
            time.sleep(0.2)
        if _wait_for_stable_file(event.src_path):
            move = _process_and_move_file(event.src_path, self.monitored_dir, self.rules, self.log, self.filters)
            if move:
                _append_to_last_run(move)
        else:
            error_message = f"ERROR: Timed out waiting for '{filename}' to finish copying"
            self.log(error_message)
            _append_to_last_run({
                "original": event.src_path,
                "destination": event.src_path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": error_message,
            })

def run_initial_scan(monitored_dir, rules, log_callback, filters=None, recursive=False):
    """
    Scans the monitored folder and organizes all existing files.
    """
    log_callback("Starting initial folder scan...")
    found_files = 0
    moves = []
    for item_name, full_path in _iter_files(monitored_dir, rules, filters or _default_settings()["filters"], recursive):
        found_files += 1
        move = _process_and_move_file(full_path, monitored_dir, rules, log_callback, filters)
        if move:
            moves.append(move)
    
    if found_files > 0:
        log_callback("Initial scan complete.")
    else:
        log_callback("No files to organize in the folder.")
    return moves

def start_monitoring(directory, stop_event, log_callback, pause_event=None, recursive=False, notify_callback=None):
    """
    Main function for the monitoring thread. Runs the initial scan, then starts the observer.
    """
    settings = load_settings()
    rules = settings["rules"]
    filters = settings["filters"]
    
    moves = run_initial_scan(directory, rules, log_callback, filters, recursive)
    _record_run(moves)

    event_handler = OrganizerEventHandler(directory, rules, log_callback, filters, pause_event)
    observer = Observer()
    observer.schedule(event_handler, directory, recursive=recursive)
    observer.start()
    log_callback(f"Real-time monitoring started. Waiting for new files...")

    try:
        while not stop_event.is_set():
            if pause_event and pause_event.is_set():
                time.sleep(0.2)
                continue
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
        log_callback("Monitoring stopped.")