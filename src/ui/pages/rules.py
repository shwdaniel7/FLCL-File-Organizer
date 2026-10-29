# src/ui/pages/rules.py
"""Visual editor for category rules and ignore filters. Edits a draft until saved."""

import copy

import customtkinter

from ...organizer import category_name_error, normalize_extension
from .. import anim, theme
from ..anim import lerp_color
from ..widgets import ChipGrid, card, icon_button, make_button

FILTER_SECTIONS = [
    ("ignored_extensions", "IGNORED EXTENSIONS", "Add extension, e.g. .tmp"),
    ("ignored_patterns", "IGNORED NAME PATTERNS", "Add pattern, e.g. *.part or ~$*"),
    ("ignored_folders", "IGNORED FOLDERS", "Add folder name, e.g. node_modules"),
]


class RulesPage(customtkinter.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._cards = {}
        self._name_entries = {}
        p = theme.current
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = customtkinter.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        customtkinter.CTkLabel(header, text="Each file moves to the first category that lists its extension. Unmatched files go to 'Others'.", font=theme.font("body"), text_color=p["muted"], anchor="w", justify="left", wraplength=520).grid(row=0, column=0, sticky="w")
        self.unsaved = customtkinter.CTkLabel(header, text="UNSAVED", font=theme.font("label"), text_color=p["on_accent"], fg_color=p["highlight"], corner_radius=10, height=22, width=80)
        make_button(header, "NEW CATEGORY", self._new_category, variant="ghost", width=140).grid(row=0, column=2, padx=(10, 0))
        make_button(header, "DISCARD", self._discard, variant="ghost", width=100, tooltip="Throw away unsaved edits.").grid(row=0, column=3, padx=(8, 0))
        make_button(header, "SAVE RULES", self._save, width=140, tooltip="Save and refresh the preview.").grid(row=0, column=4, padx=(8, 0))

        self.scroll = customtkinter.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=p["border"])
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure((0, 1), weight=1, uniform="rules")
        self.render()

    @property
    def draft(self):
        if self.app.rules_draft is None:
            self.app.rules_draft = {"rules": copy.deepcopy(self.app.settings["rules"]), "filters": copy.deepcopy(self.app.settings["filters"])}
        return self.app.rules_draft

    def render(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        self._cards = {}
        self._name_entries = {}
        names = list(self.draft["rules"])
        for index, name in enumerate(names):
            frame = self._category_card(index, name)
            frame.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 7) if index % 2 == 0 else (7, 0), pady=(0, 14))
        self._filters_card().grid(row=(len(names) + 1) // 2, column=0, columnspan=2, sticky="nsew", pady=(0, 6))
        self._update_unsaved()

    # --- categories ------------------------------------------------------

    def _category_card(self, index, name):
        p = theme.current
        color = theme.series_color(p, index)
        frame = card(self.scroll)
        top = customtkinter.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 6))
        customtkinter.CTkFrame(top, width=12, height=12, corner_radius=6, fg_color=color).pack(side="left", padx=(4, 8))
        entry = customtkinter.CTkEntry(top, font=theme.font("body_bold"), fg_color=p["panel"], border_width=1, border_color=p["panel"], height=32)
        entry.insert(0, name)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self._rename(name, entry))
        entry.bind("<FocusOut>", lambda _e: self._rename(name, entry))
        entry.bind("<FocusIn>", lambda _e: entry.configure(border_color=p["border"]))
        count = customtkinter.CTkLabel(top, text="", font=theme.font("small"), text_color=p["muted"])
        count.pack(side="left", padx=8)
        icon_button(top, "delete", lambda: self._delete(name), tooltip=f"Remove the '{name}' category.", bg=p["panel"], size=30, color=p["error"]).pack(side="left")
        chips = ChipGrid(frame, on_remove=lambda ext: self._remove_extension(name, ext), bg=p["panel"], empty_text="No extensions yet.")
        chips.pack(fill="x", padx=12)
        add = customtkinter.CTkEntry(frame, placeholder_text="Add extension, e.g. .webp", font=theme.font("small"), height=32)
        add.pack(fill="x", padx=14, pady=(8, 14))
        add.bind("<Return>", lambda _e: self._add_extension(name, add))
        self._cards[name] = {"chips": chips, "count": count, "color": color}
        self._name_entries[name] = entry
        self._refresh_card(name)
        return frame

    def _refresh_card(self, name):
        parts = self._cards[name]
        extensions = self.draft["rules"][name]
        parts["chips"].set_items(extensions, parts["color"])
        parts["count"].configure(text=f"{len(extensions)} ext")
        self._update_unsaved()

    def _owner_of(self, extension):
        return next((name for name, items in self.draft["rules"].items() if extension in {item.lower() for item in items}), None)

    def _add_extension(self, name, entry):
        extension = normalize_extension(entry.get())
        if extension is None:
            self._reject(entry, f"'{entry.get().strip()}' is not a valid extension.")
            return
        owner = self._owner_of(extension)
        if owner:
            self._reject(entry, f"{extension} already belongs to '{owner}'.")
            return
        self.draft["rules"][name].append(extension)
        entry.delete(0, "end")
        self._refresh_card(name)

    def _remove_extension(self, name, extension):
        self.draft["rules"][name] = [item for item in self.draft["rules"][name] if item != extension]
        self._refresh_card(name)

    def _rename(self, name, entry):
        """Commit a name edit. Returns False when the new name is invalid."""
        new_name = entry.get().strip()
        if name not in self.draft["rules"] or new_name == name:
            return True
        others = [item for item in self.draft["rules"] if item != name]
        error = category_name_error(new_name, others)
        if error:
            self._reject(entry, error)
            return False
        self.app.rules_draft["rules"] = {new_name if key == name else key: value for key, value in self.draft["rules"].items()}
        self.after_idle(self.render)
        return True

    def _delete(self, name):
        del self.draft["rules"][name]
        self.render()
        self.app.toasts.show(f"Removed '{name}'. Discard to bring it back.", "info")

    def _new_category(self):
        existing = {name.casefold() for name in self.draft["rules"]}
        name, counter = "New category", 2
        while name.casefold() in existing:
            name, counter = f"New category {counter}", counter + 1
        self.draft["rules"][name] = []
        self.render()
        # CTkScrollableFrame has no public scroll API; _parent_canvas is its scrolling canvas.
        self.after(60, lambda: (self.scroll._parent_canvas.yview_moveto(1.0), self._name_entries[name].focus_set(), self._name_entries[name].select_range(0, "end")))

    # --- filters ---------------------------------------------------------

    def _filters_card(self):
        p = theme.current
        filters = self.draft["filters"]
        frame = card(self.scroll)
        customtkinter.CTkLabel(frame, text="FILTERS", font=theme.font("title"), text_color=p["text"], anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        customtkinter.CTkLabel(frame, text="Matching files stay where they are and never appear in the move list.", font=theme.font("small"), text_color=p["muted"], anchor="w").pack(fill="x", padx=18, pady=(0, 8))
        for key, title, placeholder in FILTER_SECTIONS:
            customtkinter.CTkLabel(frame, text=title, font=theme.font("label"), text_color=p["muted"], anchor="w").pack(fill="x", padx=18, pady=(8, 2))
            chips = ChipGrid(frame, on_remove=lambda value, k=key: self._remove_filter(k, value), bg=p["panel"], empty_text="None.")
            chips.pack(fill="x", padx=14)
            chips.set_items(filters.get(key, []), p["muted"])
            add = customtkinter.CTkEntry(frame, placeholder_text=placeholder, font=theme.font("small"), height=32)
            add.pack(fill="x", padx=18, pady=(6, 4))
            add.bind("<Return>", lambda _e, k=key, entry=add, grid=chips: self._add_filter(k, entry, grid))

        options = customtkinter.CTkFrame(frame, fg_color="transparent")
        options.pack(fill="x", padx=18, pady=(10, 16))
        self.hidden_var = customtkinter.BooleanVar(value=filters.get("ignore_hidden", True))
        customtkinter.CTkSwitch(options, text="Ignore hidden files (names starting with '.')", variable=self.hidden_var, font=theme.font("body"), command=self._set_hidden).pack(side="left")
        customtkinter.CTkLabel(options, text="KB", font=theme.font("small"), text_color=p["muted"]).pack(side="right", padx=(6, 0))
        self.min_size = customtkinter.CTkEntry(options, width=70, height=30, font=theme.font("small"), justify="right")
        self.min_size.insert(0, f"{float(filters.get('min_size_kb', 0) or 0):g}")
        self.min_size.pack(side="right")
        self.min_size.bind("<Return>", lambda _e: self._commit_min_size())
        self.min_size.bind("<FocusOut>", lambda _e: self._commit_min_size())
        customtkinter.CTkLabel(options, text="Skip files smaller than", font=theme.font("body"), text_color=p["text"]).pack(side="right", padx=(0, 8))
        return frame

    def _add_filter(self, key, entry, grid):
        raw = entry.get().strip()
        value = normalize_extension(raw) if key == "ignored_extensions" else raw
        if not value:
            self._reject(entry, f"'{raw}' is not a valid value.")
            return
        values = self.draft["filters"].setdefault(key, [])
        if value not in values:
            values.append(value)
        entry.delete(0, "end")
        grid.set_items(values, theme.current["muted"])
        self._update_unsaved()

    def _remove_filter(self, key, value):
        self.draft["filters"][key] = [item for item in self.draft["filters"].get(key, []) if item != value]
        self.render()

    def _set_hidden(self):
        self.draft["filters"]["ignore_hidden"] = bool(self.hidden_var.get())
        self._update_unsaved()

    def _commit_min_size(self):
        try:
            value = float(self.min_size.get().strip() or 0)
            if value < 0:
                raise ValueError
        except ValueError:
            self._reject(self.min_size, "Minimum size must be a number of KB, 0 or more.")
            return False
        self.draft["filters"]["min_size_kb"] = value
        self._update_unsaved()
        return True

    # --- save / discard --------------------------------------------------

    def _save(self):
        for name, entry in list(self._name_entries.items()):
            if not self._rename(name, entry):
                return
        if not self._commit_min_size():
            return
        self.app.save_rules(self.draft)
        self.render()

    def _discard(self):
        self.app.rules_draft = None
        self.render()
        self.app.toasts.show("Unsaved rule changes discarded.", "info")

    def _update_unsaved(self):
        draft = self.draft
        dirty = draft["rules"] != self.app.settings["rules"] or draft["filters"] != self.app.settings["filters"]
        if dirty:
            self.unsaved.grid(row=0, column=1, padx=(10, 0))
        else:
            self.unsaved.grid_forget()

    def _reject(self, entry, message):
        p = theme.current
        self.app.toasts.show(message, "error")
        anim.animator.animate((entry, "flash"), theme.MOTION["slow"] * 2, lambda t: entry.configure(border_color=lerp_color(p["error"], p["border"], t)), easing=lambda t: t ** 3)
