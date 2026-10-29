# src/ui/anim.py
"""Tween engine for Tk: one `after` loop drives every running animation."""

import time
import tkinter as tk

FRAME_MS = 16
LOOP_FRAME_MS = 66


def linear(t):
    return t


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return t * t * (3 - 2 * t)


def ease_out_back(t):
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(a, b, t):
    start, end = hex_to_rgb(a), hex_to_rgb(b)
    return "#" + "".join(f"{round(lerp(x, y, t)):02x}" for x, y in zip(start, end))


def system_reduce_motion():
    """True when Windows has 'Animation effects' turned off."""
    try:
        import ctypes
        enabled = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)  # SPI_GETCLIENTAREAANIMATION
        return not enabled.value
    except (AttributeError, OSError):
        return False


class Animator:
    """Runs keyed tweens. Starting a tween with a key replaces the one already running under it."""

    def __init__(self, root, clock=time.monotonic):
        self._root = root
        self._clock = clock
        self._anims = {}
        self._job = None
        self.reduce_motion = False

    def animate(self, key, duration_ms, on_update, easing=ease_out_cubic, on_done=None, delay_ms=0, loop=False):
        """Call ``on_update(eased_t)`` each frame; loops repeat forever until cancelled."""
        self._anims.pop(key, None)
        if self.reduce_motion or duration_ms <= 0:
            # Loops are decoration: at rest they show phase 0. One-shot tweens jump to the end.
            if self._call(on_update, 0.0 if loop else 1.0) and on_done and not loop:
                self._call(on_done)
            return key
        self._anims[key] = {
            "start": self._clock() + delay_ms / 1000,
            "duration": duration_ms / 1000,
            "on_update": on_update,
            "easing": easing,
            "on_done": on_done,
            "loop": loop,
        }
        self._schedule()
        return key

    def cancel(self, key):
        self._anims.pop(key, None)

    def cancel_all(self):
        self._anims.clear()
        if self._job is not None:
            try:
                self._root.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def is_running(self, key):
        return key in self._anims

    def _call(self, callback, *args):
        try:
            callback(*args)
            return True
        except tk.TclError:  # the widget was destroyed mid-animation
            return False

    def _schedule(self):
        if self._job is None and self._anims:
            # Slow decorative loops (pulses, glows) look the same at ~15 fps and cost far less idle CPU.
            only_loops = all(anim["loop"] for anim in self._anims.values())
            self._job = self._root.after(LOOP_FRAME_MS if only_loops else FRAME_MS, self._tick)

    def _tick(self):
        self._job = None
        now = self._clock()
        for key, anim in list(self._anims.items()):
            if self._anims.get(key) is not anim:
                continue  # replaced or cancelled by an earlier callback in this frame
            elapsed = now - anim["start"]
            if elapsed < 0:
                continue
            if anim["loop"]:
                t = (elapsed % anim["duration"]) / anim["duration"]
            else:
                t = min(1.0, elapsed / anim["duration"])
            if not self._call(anim["on_update"], anim["easing"](t)):
                self._anims.pop(key, None)
                continue
            if not anim["loop"] and t >= 1.0:
                self._anims.pop(key, None)
                if anim["on_done"]:
                    self._call(anim["on_done"])
        self._schedule()


animator = None


def install(root):
    """Create the app-wide animator the widgets share."""
    global animator
    animator = Animator(root)
    return animator
