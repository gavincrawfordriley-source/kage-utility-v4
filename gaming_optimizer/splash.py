"""
Splash screen with water-ripple effect around the logo.
Frameless, fades in, expanding circles pulse behind the logo, then fades out.
"""
import os
import sys
import math
import tkinter as tk
import customtkinter as ctk
from PIL import Image


def _asset_path(name):
    """Resolve asset both in dev and PyInstaller-frozen mode."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


class Splash(ctk.CTkToplevel):
    """
    Frameless, centered splash with water-ripple effect.
    Call Splash.show(root, on_done_callback) — on_done fires when it closes.
    """
    W, H = 520, 520
    BG = "#07040d"
    RIPPLE_COLOR = "#a05aff"

    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done = on_done
        self.overrideredirect(True)          # no titlebar
        self.configure(fg_color=self.BG)
        self.attributes("-topmost", True)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{(sw - self.W)//2}+{(sh - self.H)//2}")

        # ---- Canvas for water ripples (bottom layer) ----
        self.canvas = tk.Canvas(
            self, width=self.W, height=self.H,
            bg=self.BG, highlightthickness=0, bd=0,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Ripple rings state: list of dicts {radius, alpha}
        self._ripples = []
        # Center point where logo sits
        self.cx, self.cy = self.W // 2, self.H // 2 - 20

        # ---- Logo (on top of canvas via place with a transparent-ish CTkLabel) ----
        logo_path = _asset_path("splash_source.png")
        if not os.path.exists(logo_path):
            logo_path = _asset_path("icon.png")

        self._img_ref = None
        try:
            pil = Image.open(logo_path).convert("RGBA")
            pil.thumbnail((260, 260), Image.LANCZOS)
            self._img_ref = ctk.CTkImage(light_image=pil, dark_image=pil,
                                         size=pil.size)
            self._label = ctk.CTkLabel(self, text="", image=self._img_ref,
                                       fg_color=self.BG)
        except Exception:
            self._label = ctk.CTkLabel(
                self, text="KAGE",
                font=("Rajdhani", 62, "bold"),
                text_color=self.RIPPLE_COLOR, fg_color=self.BG,
            )
        self._label.place(x=self.cx, y=self.cy, anchor="center")

        # Tagline below
        self._tag = ctk.CTkLabel(
            self, text="Move like a shadow  \u5F71",
            font=("Rajdhani", 15, "bold"),
            text_color="#6c5a85", fg_color=self.BG,
        )
        self._tag.place(x=self.cx, y=self.cy + 170, anchor="center")

        # Start faded out, then fade in and start ripples
        self.attributes("-alpha", 0.0)
        self._alpha = 0.0
        self._closing = False
        self._frame = 0
        self._fade_in()
        self._pulse_ripple()   # spawn first ripple
        self._tick_ripples()   # animate ripples

    # -----------------------------------------------------
    # Fade in / out
    # -----------------------------------------------------
    def _fade_in(self):
        self._alpha = min(1.0, self._alpha + 0.08)
        try:
            self.attributes("-alpha", self._alpha)
        except Exception:
            pass
        if self._alpha < 1.0:
            self.after(30, self._fade_in)
        else:
            # After hold time, start fade-out
            self.after(1800, self._fade_out)

    def _fade_out(self):
        self._closing = True
        self._alpha = max(0.0, self._alpha - 0.1)
        try:
            self.attributes("-alpha", self._alpha)
        except Exception:
            pass
        if self._alpha > 0.0:
            self.after(30, self._fade_out)
        else:
            self._close()

    def _close(self):
        try:
            self.destroy()
        finally:
            if self.on_done:
                self.on_done()

    # -----------------------------------------------------
    # Water ripple animation
    # -----------------------------------------------------
    def _pulse_ripple(self):
        """Spawn a new ripple every ~700 ms until we start closing."""
        if self._closing:
            return
        self._ripples.append({"r": 30.0, "alpha": 1.0})
        self.after(700, self._pulse_ripple)

    def _tick_ripples(self):
        """Grow and fade each ripple, redraw canvas."""
        if self._closing and not self._ripples:
            return
        self.canvas.delete("ripple")
        alive = []
        for r in self._ripples:
            r["r"] += 2.2
            r["alpha"] -= 0.012
            if r["alpha"] <= 0 or r["r"] > 300:
                continue
            alive.append(r)
            # Convert alpha to hex color (fade purple → dark)
            a = max(0.0, min(1.0, r["alpha"]))
            # blend RIPPLE_COLOR toward BG based on alpha
            pr, pg, pb = 0xa0, 0x5a, 0xff
            br, bg, bb = 0x07, 0x04, 0x0d
            cr = int(br + (pr - br) * a)
            cg = int(bg + (pg - bg) * a)
            cb = int(bb + (pb - bb) * a)
            col = f"#{cr:02x}{cg:02x}{cb:02x}"
            self.canvas.create_oval(
                self.cx - r["r"], self.cy - r["r"],
                self.cx + r["r"], self.cy + r["r"],
                outline=col, width=2, tags="ripple",
            )
        self._ripples = alive
        # Also draw a subtle inner glow to make it feel like water
        self.canvas.create_oval(
            self.cx - 90, self.cy - 90,
            self.cx + 90, self.cy + 90,
            outline="#2a1b47", width=1, tags="ripple",
        )
        self.after(30, self._tick_ripples)

    @classmethod
    def show(cls, master, on_done):
        try:
            cls(master, on_done)
        except Exception:
            # if splash fails for any reason, jump straight to the app
            if on_done:
                on_done()
