# src/organizer.py

import os
import json
import time
import shutil
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def resource_path(relative_path):
    """Return a path to a bundled resource in source and PyInstaller modes."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def _process_and_move_file(file_path, monitored_dir, rules, log_callback):
    """
    Core logic to organize a single file based on the rules from config.json.
    """
    try:
        if not os.path.exists(file_path):
            return

        filename, extension = os.path.splitext(os.path.basename(file_path))
        extension = extension.lower()

        if not extension or filename.startswith('.') or filename.startswith('~'):
            return

        destination_folder_name = "Other"
        for folder, extensions in rules.items():
            if extension in extensions:
                destination_folder_name = folder
                break
        
        destination_path = os.path.join(monitored_dir, destination_folder_name)
        
        if os.path.dirname(file_path) == destination_path:
            return

        if not os.path.exists(destination_path):
            os.makedirs(destination_path)
            log_callback(f"Folder created: {destination_folder_name}")
        
        final_destination_path = os.path.join(destination_path, os.path.basename(file_path))
        
        shutil.move(file_path, final_destination_path)
        log_callback(f"File moved: '{os.path.basename(file_path)}' -> '{destination_folder_name}'")

    except Exception as e:
        log_callback(f"ERROR organizing {os.path.basename(file_path)}: {e}")

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
        
        self.log(f"New file detected: {os.path.basename(event.src_path)}")
        time.sleep(1) # Wait to ensure the file is fully written
        _process_and_move_file(event.src_path, self.monitored_dir, self.rules, self.log)

def run_initial_scan(monitored_dir, rules, log_callback):
    """
    Scans the monitored folder and organizes all existing files.
    """
    log_callback("Starting initial folder scan...")
    found_files = 0
    for item_name in os.listdir(monitored_dir):
        full_path = os.path.join(monitored_dir, item_name)
        if os.path.isfile(full_path):
            found_files += 1
            _process_and_move_file(full_path, monitored_dir, rules, log_callback)
    
    if found_files > 0:
        log_callback("Initial scan complete.")
    else:
        log_callback("No files to organize in the folder.")

def start_monitoring(directory, stop_event, log_callback):
    """
    Main function for the monitoring thread. Runs the initial scan, then starts the observer.
    """
    config_path = resource_path("config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        rules = json.load(f)
    
    run_initial_scan(directory, rules, log_callback)

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