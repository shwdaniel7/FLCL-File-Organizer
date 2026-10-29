# src/ui/theme.py
"""Design tokens (palettes, spacing, radii, motion, type) and the CTk theme derived from them."""

import copy
import tkinter.font as tkfont

import customtkinter

from ..organizer import resource_path
from .anim import hex_to_rgb

PALETTES = {
    "FLCL": {
        "window": "#0D1015",
        "panel": "#151922",
        "surface": "#1C2230",
        "raised": "#262E40",
        "border": "#2F3A4D",
        "text": "#EEF3FF",
        "muted": "#A3AEC2",
        "accent": "#FF3399",
        "accent_soft": "#D9277F",
        "accent_alt": "#34E0D0",
        "highlight": "#FFD84D",
        "on_accent": "#16060F",
        "success": "#5EE6A0",
        "warning": "#F7D76A",
        "error": "#FF6B7A",
        "series": ["#FF3399", "#34E0D0", "#FFD84D", "#9B7BFF", "#FF8A4C", "#5EE6A0", "#4CA8FF", "#FF6B7A"],
    },
    "Neutral": {
        "window": "#0F1317",
        "panel": "#161B21",
        "surface": "#1D232B",
        "raised": "#273039",
        "border": "#323C48",
        "text": "#E8EEF7",
        "muted": "#A3AFBD",
        "accent": "#74C0FC",
        "accent_soft": "#4FA8F0",
        "accent_alt": "#8CE0C4",
        "highlight": "#E8C859",
        "on_accent": "#08131D",
        "success": "#7AD7A6",
        "warning": "#E8C859",
        "error": "#FF8A80",
        "series": ["#74C0FC", "#8CE0C4", "#E8C859", "#B9A6FF", "#F4A980", "#7AD7A6", "#9FB4C8", "#FF8A80"],
    },
}
DEFAULT_THEME = "FLCL"

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = {"sm": 8, "md": 12, "lg": 16, "pill": 999}
MOTION = {"fast": 120, "base": 220, "slow": 450, "pulse": 1600}

# Segoe MDL2 Assets ships with Windows 10 and 11.
ICONS = {
    "organize": "", "activity": "", "reports": "", "rules": "",
    "settings": "", "menu": "", "play": "", "pause": "",
    "stop": "", "undo": "", "refresh": "", "search": "",
    "folder": "", "theme": "", "add": "", "close": "",
    "check": "", "info": "", "warning": "", "error": "",
    "export": "", "delete": "", "save": "",
}

current = PALETTES[DEFAULT_THEME]
_fonts = {}
_display_family = "Segoe UI Black"


def palette(name):
    return PALETTES.get(name, PALETTES[DEFAULT_THEME])


def relative_luminance(color):
    channels = []
    for value in hex_to_rgb(color):
        c = value / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def series_color(p, index):
    return p["series"][index % len(p["series"])]


def build_ctk_theme(base, p):
    """Return a CTk theme dict where every widget starts with this palette's colors."""
    theme = copy.deepcopy(base)
    overrides = {
        "CTk": {"fg_color": p["window"]},
        "CTkToplevel": {"fg_color": p["window"]},
        "CTkFrame": {"corner_radius": RADIUS["lg"], "fg_color": p["panel"], "top_fg_color": p["surface"], "border_color": p["border"]},
        "CTkButton": {"corner_radius": RADIUS["md"], "fg_color": p["accent"], "hover_color": p["accent_soft"], "border_color": p["accent"], "text_color": p["on_accent"], "text_color_disabled": p["muted"]},
        "CTkLabel": {"text_color": p["text"]},
        "CTkEntry": {"corner_radius": RADIUS["md"], "border_width": 1, "fg_color": p["surface"], "border_color": p["border"], "text_color": p["text"], "placeholder_text_color": p["muted"]},
        "CTkCheckBox": {"corner_radius": 6, "border_width": 2, "fg_color": p["accent"], "border_color": p["border"], "hover_color": p["accent_soft"], "checkmark_color": p["on_accent"], "text_color": p["text"], "text_color_disabled": p["muted"]},
        "CTkSwitch": {"fg_color": p["border"], "progress_color": p["accent"], "button_color": p["text"], "button_hover_color": "#FFFFFF", "text_color": p["text"], "text_color_disabled": p["muted"]},
        "CTkRadioButton": {"fg_color": p["accent"], "border_color": p["border"], "hover_color": p["accent_soft"], "text_color": p["text"]},
        "CTkProgressBar": {"fg_color": p["surface"], "progress_color": p["accent"], "border_color": p["border"]},
        "CTkSlider": {"fg_color": p["surface"], "progress_color": p["accent"], "button_color": p["accent"], "button_hover_color": p["accent_soft"]},
        "CTkOptionMenu": {"corner_radius": RADIUS["md"], "fg_color": p["surface"], "button_color": p["surface"], "button_hover_color": p["raised"], "text_color": p["text"], "text_color_disabled": p["muted"]},
        "CTkComboBox": {"fg_color": p["surface"], "border_color": p["border"], "button_color": p["border"], "button_hover_color": p["raised"], "text_color": p["text"]},
        "CTkScrollbar": {"button_color": p["border"], "button_hover_color": p["muted"]},
        "CTkSegmentedButton": {"fg_color": p["surface"], "selected_color": p["accent"], "selected_hover_color": p["accent_soft"], "unselected_color": p["surface"], "unselected_hover_color": p["raised"], "text_color": p["text"], "text_color_disabled": p["muted"]},
        "CTkTextbox": {"corner_radius": RADIUS["md"], "border_width": 0, "fg_color": p["surface"], "border_color": p["border"], "text_color": p["text"], "scrollbar_button_color": p["border"], "scrollbar_button_hover_color": p["muted"]},
        "CTkScrollableFrame": {"label_fg_color": p["panel"]},
        "DropdownMenu": {"fg_color": p["panel"], "hover_color": p["raised"], "text_color": p["text"]},
        "CTkFont": {"family": "Segoe UI", "size": 13, "weight": "normal"},
    }
    for widget, values in overrides.items():
        theme.setdefault(widget, {}).update(values)
    return theme


def apply(name):
    """Make ``name`` the active palette. Widgets created afterwards use it."""
    global current
    current = palette(name)
    customtkinter.set_appearance_mode("dark")
    customtkinter.set_default_color_theme("dark-blue")
    customtkinter.ThemeManager.theme = build_ctk_theme(customtkinter.ThemeManager.theme, current)
    return current


def load_fonts(root):
    """Register the bundled Daydream font; fall back to a heavy system face when it is unavailable."""
    global _display_family
    try:
        customtkinter.FontManager.load_font(resource_path("assets/Daydream.ttf"))
    except Exception as error:  # FontManager raises plain Exceptions on Windows API failures
        print(f"Warning: could not load Daydream font: {error}")
    # families() is cached at Tk startup, so ask Tk what the family actually resolves to.
    if tkfont.Font(root, family="Daydream").actual("family") == "Daydream":
        _display_family = "Daydream"


_FONT_SPECS = {
    "display": ("display", 22, "normal"),
    "title": ("display", 15, "normal"),
    "number": ("display", 20, "normal"),
    "button": ("display", 11, "normal"),
    "label": ("display", 9, "normal"),
    "body": ("Segoe UI", 13, "normal"),
    "body_bold": ("Segoe UI Semibold", 13, "normal"),
    "small": ("Segoe UI", 11, "normal"),
    "mono": ("Consolas", 11, "normal"),
    "icon": ("Segoe MDL2 Assets", 14, "normal"),
    "icon_lg": ("Segoe MDL2 Assets", 20, "normal"),
}


def font(role):
    if role not in _fonts:
        family, size, weight = _FONT_SPECS[role]
        _fonts[role] = customtkinter.CTkFont(family=_display_family if family == "display" else family, size=size, weight=weight)
    return _fonts[role]
