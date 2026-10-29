# src/ui/pages/organize.py
"""Preview page: summary cards, search, category filter and the checkable move list."""

import os
from tkinter import ttk

import customtkinter
from PIL import Image, ImageDraw, ImageTk

from ...organizer import _format_size
from .. import anim, theme
from ..anim import lerp_color
from ..widgets import StatCard, card, hover_fade, make_button, scaling, set_hover_colors

CASCADE_ROWS = 18


class OrganizePage(customtkinter.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._images = {}
        self._category_colors = {}
        self._pills = {}
        self._search_job = None
        p = theme.current
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        cards = customtkinter.CTkFrame(self, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        specs = [
            ("selected", "To organize", p["accent"], str, "Files that will move when you press Start."),
            ("no_rule", "No rule", p["warning"], str, "Files without a matching rule; they go to 'Others'."),
            ("conflicts", "Renamed", p["accent_alt"], str, "Files that get a ' (n)' suffix to avoid overwriting."),
            ("ignored", "Ignored", p["muted"], str, "Files skipped by your filters."),
            ("size", "Total size", p["highlight"], _format_size, "Combined size of the selected files."),
        ]
        self.cards = {}
        for index, (key, label, color, formatter, tip) in enumerate(specs):
            cards.grid_columnconfigure(index, weight=1, uniform="cards")
            stat = StatCard(cards, label, color, formatter, tooltip=tip)
            stat.grid(row=0, column=index, sticky="nsew", padx=(0, 10) if index < len(specs) - 1 else 0)
            self.cards[key] = stat

        toolbar = customtkinter.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)
        search = customtkinter.CTkFrame(toolbar, fg_color=p["surface"], border_color=p["border"], border_width=1, corner_radius=theme.RADIUS["md"], height=40)
        search.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        customtkinter.CTkLabel(search, text=theme.ICONS["search"], font=theme.font("icon"), text_color=p["muted"]).pack(side="left", padx=(14, 6))
        self.search_entry = customtkinter.CTkEntry(search, placeholder_text="Search files in the preview…  (Ctrl+F)", border_width=0, fg_color=p["surface"], font=theme.font("body"), height=36)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=2)
        if app.search_text:
            self.search_entry.insert(0, app.search_text)
        self.search_entry.bind("<KeyRelease>", self._on_search)
        self.search_entry.bind("<Escape>", lambda _e: self._clear_search())
        make_button(toolbar, "REFRESH", app.refresh_preview, variant="ghost", width=120, tooltip="Rebuild the preview from disk (F5).").grid(row=0, column=1)

        self.pill_row = customtkinter.CTkFrame(self, fg_color="transparent", height=30)
        self.pill_row.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self.list_card = card(self, fg_color=p["surface"])
        self.list_card.grid(row=3, column=0, sticky="nsew")
        self.list_card.grid_columnconfigure(0, weight=1)
        self.list_card.grid_rowconfigure(0, weight=1)
        self._style_tree()
        self.tree = ttk.Treeview(self.list_card, style="Preview.Treeview", columns=("size", "dest", "flags"), show=("tree", "headings"), selectmode="extended")
        self.tree.heading("#0", text="  FILE", anchor="w", command=self._toggle_all)
        self.tree.heading("size", text="SIZE", anchor="e")
        self.tree.heading("dest", text="DESTINATION", anchor="w")
        self.tree.heading("flags", text="", anchor="center")
        factor = scaling(self)
        self.tree.column("#0", width=int(300 * factor), minwidth=int(160 * factor), stretch=True)
        self.tree.column("size", width=int(90 * factor), minwidth=int(70 * factor), anchor="e", stretch=False)
        self.tree.column("dest", width=int(240 * factor), minwidth=int(120 * factor), anchor="w", stretch=True)
        self.tree.column("flags", width=int(100 * factor), minwidth=int(80 * factor), anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scrollbar = customtkinter.CTkScrollbar(self.list_card, command=self.tree.yview, fg_color=p["surface"])
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 6), pady=10)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<space>", self._toggle_selection)
        self._status_colors = {
            "normal": p["text"],
            "norule": lerp_color(p["text"], p["warning"], 0.7),
            "conflict": lerp_color(p["text"], p["accent_alt"], 0.7),
            "excluded": p["muted"],
        }
        for tag, color in self._status_colors.items():
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure("odd", background=lerp_color(p["surface"], p["panel"], 0.55))
        self.tree.tag_configure("even", background=p["surface"])

        self.empty = customtkinter.CTkFrame(self.list_card, fg_color=p["surface"], corner_radius=theme.RADIUS["lg"])
        holder = customtkinter.CTkFrame(self.empty, fg_color="transparent")
        holder.place(relx=0.5, rely=0.45, anchor="center")
        self.empty_icon = customtkinter.CTkLabel(holder, text=theme.ICONS["folder"], font=customtkinter.CTkFont(family="Segoe MDL2 Assets", size=52), text_color=p["accent"])
        self.empty_title = customtkinter.CTkLabel(holder, text="", font=theme.font("title"), text_color=p["text"])
        self.empty_body = customtkinter.CTkLabel(holder, text="", font=theme.font("body"), text_color=p["muted"], wraplength=440, justify="center")
        self.empty_button = make_button(holder, "CHOOSE FOLDER", app.select_folder, width=200, height=44)
        self.empty_icon.pack(pady=(0, 10))
        self.empty_title.pack()
        self.empty_body.pack(pady=(8, 18))
        self.empty_button.pack()

        self.render(cascade=False)

    def _style_tree(self):
        p = theme.current
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Preview.Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"], rowheight=round(34 * scaling(self)), borderwidth=0, relief="flat", font=("Segoe UI", 10))
        style.map("Preview.Treeview", background=[("selected", p["raised"])], foreground=[("selected", p["text"])])
        style.configure("Preview.Treeview.Heading", background=p["surface"], foreground=p["muted"], borderwidth=0, relief="flat", font=("Segoe UI Semibold", 9), padding=(6, 8))
        style.map("Preview.Treeview.Heading", background=[("active", p["raised"])], foreground=[("active", p["text"])])
        style.layout("Preview.Treeview", [("Preview.Treeview.treearea", {"sticky": "nswe"})])

    # --- rendering -------------------------------------------------------

    def render(self, cascade=False, pills=True):
        """Rebuild cards, pills and rows from the app's preview state."""
        app = self.app
        self._update_cards()
        if pills:
            self._category_colors = {}  # rules may have been reordered or renamed
            self._render_pills()
        self.tree.delete(*self.tree.get_children())
        if app.preview_error:
            self._show_empty("error", "PREVIEW UNAVAILABLE", f"The folder could not be read:\n{app.preview_error}", "CHOOSE ANOTHER")
            return
        if not os.path.isdir(app.directory_path.get()):
            self._show_empty("folder", "DROP A FOLDER HERE", "Drag a folder from Explorer, or choose one to preview what will move.\nNothing changes on disk until you press Start.", "CHOOSE FOLDER")
            return
        items = app.visible_preview_items()
        if not items:
            if app.search_text or app.category_filter:
                self._show_empty("search", "NO MATCHES", "No files in the preview match this search or filter.", None)
            else:
                self._show_empty("check", "ALL TIDY", "Nothing in this folder needs to move. New files will be organized while monitoring is on.", None)
            return
        self.empty.grid_forget()
        p = theme.current
        for index, item in enumerate(items):
            parity = "odd" if index % 2 else "even"
            tags = (parity, f"in{index}") if cascade and index < CASCADE_ROWS else (parity, self._status_tag(item))
            self.tree.insert("", "end", iid=item["source_path"], text=" " + item["filename"], image=self._row_image(item), values=self._row_values(item), tags=tags)
        if cascade:
            for index, item in enumerate(items[:CASCADE_ROWS]):
                self._cascade(index, item, p)

    def _cascade(self, index, item, p):
        tag = f"in{index}"
        final = self._status_colors[self._status_tag(item)]
        start = p["surface"]
        iid = item["source_path"]
        parity = "odd" if index % 2 else "even"

        def done():
            if self.tree.exists(iid):
                self.tree.item(iid, tags=(parity, self._status_tag(item)))

        anim.animator.animate(
            (self, tag), 280, lambda t: self.tree.tag_configure(tag, foreground=lerp_color(start, final, t)),
            on_done=done, delay_ms=index * 22,
        )

    def _show_empty(self, icon, title, body, button_text):
        p = theme.current
        self.empty.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=2, pady=2)
        self.empty_icon.configure(text=theme.ICONS.get(icon, theme.ICONS["info"]), text_color=p["error"] if icon == "error" else p["accent"])
        self.empty_title.configure(text=title)
        self.empty_body.configure(text=body)
        if button_text:
            self.empty_button.configure(text=button_text)
            self.empty_button.pack()
        else:
            self.empty_button.pack_forget()
        final_title, final_body = p["text"], p["muted"]
        anim.animator.animate(
            (self, "empty"), theme.MOTION["slow"],
            lambda t: (self.empty_title.configure(text_color=lerp_color(p["surface"], final_title, t)),
                       self.empty_body.configure(text_color=lerp_color(p["surface"], final_body, t))),
        )

    def _status_tag(self, item):
        if self.app.is_excluded(item):
            return "excluded"
        if not item["has_rule"]:
            return "norule"
        if item["conflict"]:
            return "conflict"
        return "normal"

    def _row_values(self, item):
        destination = os.path.relpath(item["destination_path"], self.app.directory_path.get())
        flags = []
        if not item["has_rule"]:
            flags.append("NO RULE")
        if item["conflict"]:
            flags.append("RENAME")
        return (_format_size(item["size"]), f"→  {destination}", " · ".join(flags))

    def _category_color(self, name):
        if name not in self._category_colors:
            names = list(self.app.settings["rules"].keys())
            index = names.index(name) if name in names else len(self._category_colors) + len(names)
            self._category_colors[name] = theme.series_color(theme.current, index)
        return self._category_colors[name]

    def _row_image(self, item):
        checked = not self.app.is_excluded(item)
        color = self._category_color(item["destination_folder"])
        key = (checked, color)
        if key not in self._images:
            self._images[key] = self._make_image(checked, color)
        return self._images[key]

    def _make_image(self, checked, color):
        """Checkbox + category dot, drawn 4x and downsampled for smooth edges."""
        p = theme.current
        s = scaling(self) * 4
        box, gap, dot, pad = 16 * s, 10 * s, 8 * s, 4 * s
        width, height = int(pad + box + gap + dot + 4 * s), int(box + 4 * s)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        top = (height - box) / 2
        rect = [pad, top, pad + box, top + box]
        if checked:
            draw.rounded_rectangle(rect, radius=4.5 * s, fill=p["accent"])
            draw.line([(pad + 4 * s, top + 8.5 * s), (pad + 7 * s, top + 11.5 * s), (pad + 12.5 * s, top + 5 * s)], fill=p["on_accent"], width=int(2.2 * s), joint="curve")
        else:
            draw.rounded_rectangle(rect, radius=4.5 * s, outline=p["muted"], width=int(1.6 * s))
        cx, cy = pad + box + gap + dot / 2, height / 2
        draw.ellipse([cx - dot / 2, cy - dot / 2, cx + dot / 2, cy + dot / 2], fill=color if checked else p["border"])
        image = image.resize((max(1, width // 4), max(1, height // 4)), Image.LANCZOS)
        return ImageTk.PhotoImage(image, master=self)

    def _update_cards(self, animate=True):
        app = self.app
        selected = app.selected_move_items()
        values = {
            "selected": len(selected),
            "no_rule": sum(1 for item in selected if not item["has_rule"]),
            "conflicts": sum(1 for item in selected if item["conflict"]),
            "ignored": sum(1 for item in app.preview_plan if item["status"] == "ignored"),
            "size": sum(item["size"] for item in selected),
        }
        for key, value in values.items():
            self.cards[key].set(value, animate)

    def _render_pills(self):
        p = theme.current
        for pill in self._pills.values():
            pill.destroy()
        self._pills = {}
        counts = {}
        for item in self.app.move_items():
            counts[item["destination_folder"]] = counts.get(item["destination_folder"], 0) + 1
        if not counts:
            return
        if self.app.category_filter not in counts:
            self.app.category_filter = None
        entries = [(None, f"All  {sum(counts.values())}")] + [(name, f"{name}  {count}") for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        for key, text in entries:
            pill = customtkinter.CTkButton(
                self.pill_row, text=text, font=theme.font("small"), height=30, corner_radius=15, border_width=1,
                width=40, hover=False, command=lambda k=key: self._select_category(k),
            )
            hover_fade(pill, p["surface"], p["raised"])
            pill.pack(side="left", padx=(0, 6))
            self._pills[key] = pill
        self._paint_pills()

    def _paint_pills(self):
        p = theme.current
        for key, pill in self._pills.items():
            active = key == self.app.category_filter
            color = p["accent"] if key is None else self._category_color(key)
            set_hover_colors(pill, p["accent"] if active else p["surface"], p["accent_soft"] if active else p["raised"])
            pill.configure(text_color=p["on_accent"] if active else p["text"], border_color=p["accent"] if active else lerp_color(p["border"], color, 0.35))

    def _select_category(self, key):
        self.app.category_filter = key
        self._paint_pills()
        self.render(pills=False)

    # --- interaction -----------------------------------------------------

    def _on_search(self, _event=None):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(140, self._apply_search)

    def _apply_search(self):
        self._search_job = None
        text = self.search_entry.get().strip()
        if text != self.app.search_text:
            self.app.search_text = text
            self.render(pills=False)

    def _clear_search(self):
        self.search_entry.delete(0, "end")
        self._apply_search()

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def _items_for(self, iids):
        by_path = {item["source_path"]: item for item in self.app.move_items()}
        return [by_path[iid] for iid in iids if iid in by_path]

    def _set_included(self, items, included):
        self.app.set_included(items, included)
        for item in items:
            iid = item["source_path"]
            if self.tree.exists(iid):
                parity = self.tree.item(iid, "tags")[0]
                self.tree.item(iid, image=self._row_image(item), tags=(parity, self._status_tag(item)))
        self._update_cards()

    def _toggle(self, iids):
        items = self._items_for(iids)
        if items:
            self._set_included(items, any(self.app.is_excluded(item) for item in items))

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "tree" and "image" in self.tree.identify_element(event.x, event.y):
            row = self.tree.identify_row(event.y)
            if row:
                self._toggle([row])
                return "break"
        return None

    def _on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if row and self.tree.identify_region(event.x, event.y) in ("tree", "cell"):
            self._toggle([row])
            return "break"
        return None

    def _toggle_selection(self, _event=None):
        self._toggle(self.tree.selection())
        return "break"

    def _toggle_all(self):
        self._toggle(self.tree.get_children())
