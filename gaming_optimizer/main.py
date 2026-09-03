"""
FragBoost — Windows 11 Gaming Optimizer
Modern dark GUI with free/premium tweaks + unlock-code system.
"""
import os
import sys
import ctypes
import threading
import platform
import customtkinter as ctk
from tkinter import messagebox

if getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(sys.executable))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from optimizations import TWEAKS, CATEGORIES, is_admin
from licensing import (
    submit_code, is_unlocked, is_owner_revoked, is_owner_session,
    is_partner, is_owner, get_custom_bg_path,
)
from settings_ui import SettingsDialog, get_theme
import history
import updater
from splash import Splash
from tray import TrayController
from discord_rp import RichPresence
from sound import play_splash_sound
from voice import play_intro
import startup as autostart

APP_NAME = "Kage Utility"
APP_VER = "1.5"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

CATEGORY_ICONS = {
    "CPU & Power": "\u26A1",
    "Network": "\U0001F310",
    "GPU / DirectX": "\U0001F3AE",
    "Input": "\U0001F5B1",
    "System": "\U0001F680",
    "Gaming": "\U0001F3AE",
    "Visuals": "\u2728",
    "Startup": "\U0001F510",
    "Disk": "\U0001F4BE",
    "Privacy": "\U0001F576",
    "Audio": "\U0001F3B5",
}


def relaunch_as_admin():
    if is_admin():
        return
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Admin required", f"Failed to elevate: {e}")


# ============================================================
# Tweak card
# ============================================================
class TweakCard(ctk.CTkFrame):
    def __init__(self, master, tweak, on_change, unlocked, theme, transparent_bg=False):
        self.tweak = tweak
        self.on_change = on_change
        self.unlocked = unlocked
        self.theme = theme
        locked_visual = tweak["locked"] and not unlocked
        self.locked_visual = locked_visual

        super().__init__(
            master,
            fg_color=theme["CARD_LOCKED"] if locked_visual else theme["CARD"],
            corner_radius=12,
            border_width=1,
            border_color=theme["BORDER"],
        )
        self._build()
        self.refresh_status()

    def _build(self):
        t = self.theme
        self.grid_columnconfigure(1, weight=1)

        title_color = t["TEXT_LOCKED"] if self.locked_visual else t["TEXT"]
        desc_color = t["MUTED_LOCKED"] if self.locked_visual else t["MUTED"]
        icon_color = t["MUTED_LOCKED"] if self.locked_visual else t["ACCENT"]

        icon = ctk.CTkLabel(self, text=self.tweak["icon"],
                            font=("Segoe UI Emoji", 22),
                            text_color=icon_color, width=36)
        icon.grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=12, sticky="n")

        title_text = self.tweak["title"]
        if self.tweak["locked"]:
            title_text = ("\U0001F512  " if self.locked_visual else "\u2728  ") + title_text

        title = ctk.CTkLabel(self, text=title_text,
                             font=("Rajdhani", 15, "bold"),
                             text_color=title_color, anchor="w")
        title.grid(row=0, column=1, sticky="ew", pady=(12, 0))

        desc = ctk.CTkLabel(self, text=self.tweak["desc"],
                            font=("Inter", 11), text_color=desc_color,
                            anchor="w", justify="left", wraplength=460)
        desc.grid(row=1, column=1, sticky="ew", pady=(2, 12))

        self.status_dot = ctk.CTkLabel(self, text="\u25CF",
                                       font=("Segoe UI", 12),
                                       text_color=t["MUTED_LOCKED"] if self.locked_visual else t["MUTED"])
        self.status_dot.grid(row=0, column=2, padx=(0, 2), pady=(16, 0), sticky="e")

        self.status_text = ctk.CTkLabel(self, text="OFF",
                                        font=("Rajdhani", 11, "bold"),
                                        text_color=t["MUTED_LOCKED"] if self.locked_visual else t["MUTED"],
                                        width=32)
        self.status_text.grid(row=0, column=3, padx=(0, 10), pady=(16, 0), sticky="e")

        self.switch = ctk.CTkSwitch(
            self, text="", command=self._toggle,
            progress_color=t["GOLD"] if self.tweak["locked"] else t["ACCENT"],
            button_color=t["TEXT"], button_hover_color=t["ACCENT"],
            fg_color="#242a33", width=44,
        )
        self.switch.grid(row=1, column=2, columnspan=2,
                         padx=(0, 14), pady=(0, 10), sticky="e")

        if self.locked_visual:
            self.switch.configure(state="disabled")

    def refresh_status(self):
        t = self.theme
        if self.locked_visual:
            self.status_dot.configure(text_color=t["MUTED_LOCKED"])
            self.status_text.configure(text="LOCKED", text_color=t["MUTED_LOCKED"])
            return
        try:
            state = self.tweak["status"]()
        except Exception:
            state = "off"
        applied = state == "on"
        if applied:
            self.switch.select()
            color = t["GOLD"] if self.tweak["locked"] else t["ACCENT"]
            self.status_dot.configure(text_color=color)
            self.status_text.configure(text="ON", text_color=color)
        else:
            self.switch.deselect()
            self.status_dot.configure(text_color=t["MUTED"])
            self.status_text.configure(text="OFF", text_color=t["MUTED"])

    def _toggle(self):
        if self.locked_visual:
            return
        self.on_change(self.tweak, bool(self.switch.get()), self)


# ============================================================
# Partner Welcome Modal — shown once when someone enters partner code
# ============================================================
class PartnerWelcome(ctk.CTkToplevel):
    PARTNER_COLOR = "#2dd4bf"
    PARTNER_BG = "#0d2a26"

    def __init__(self, master, theme):
        super().__init__(master)
        self.theme = theme
        self.title("Welcome, Partner")
        self.geometry("520x360")
        self.resizable(False, False)
        self.configure(fg_color=self.PARTNER_BG)
        self.transient(master)
        self.grab_set()

        # Big handshake icon
        ctk.CTkLabel(
            self, text="\U0001F91D",
            font=("Segoe UI Emoji", 64),
            text_color=self.PARTNER_COLOR,
        ).pack(pady=(30, 8))

        # Heading
        ctk.CTkLabel(
            self, text="Welcome to the Kage Family",
            font=("Rajdhani", 22, "bold"),
            text_color=self.PARTNER_COLOR,
        ).pack(pady=(0, 4))

        # Body — the exact message
        body = (
            "Thank you for joining us.\n"
            "We are looking forward to working with you.\n\n"
            "\u2014 Scary & Peachy"
        )
        ctk.CTkLabel(
            self, text=body,
            font=("Inter", 12),
            text_color=theme["TEXT"], justify="center",
        ).pack(pady=(0, 18))

        # Perks summary
        perks_frame = ctk.CTkFrame(self, fg_color=self.PARTNER_BG)
        perks_frame.pack(pady=(0, 8))
        for line in [
            "\u2605  Full Premium access",
            "\U0001F91D  Partner-exclusive tweaks",
            "\U0001F3A8  Custom background wallpapers",
        ]:
            ctk.CTkLabel(
                perks_frame, text=line,
                font=("Rajdhani", 12, "bold"),
                text_color=self.PARTNER_COLOR,
            ).pack(anchor="w", pady=1)

        # Close button
        ctk.CTkButton(
            self, text="LET'S GO",
            command=self.destroy,
            fg_color=self.PARTNER_COLOR, hover_color="#14b8a6", text_color="#053b32",
            font=("Rajdhani", 14, "bold"), width=180, height=38, corner_radius=10,
        ).pack(pady=(12, 20))


# ============================================================
# Unlock dialog
# ============================================================
class UnlockDialog(ctk.CTkToplevel):
    def __init__(self, master, theme, on_result):
        super().__init__(master)
        self.theme = theme
        self.on_result = on_result
        self.title("Enter Code")
        self.geometry("440x290")
        self.resizable(False, False)
        self.configure(fg_color=theme["BG"])
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text="\U0001F512  ENTER UNLOCK CODE",
                     font=("Rajdhani", 20, "bold"),
                     text_color=theme["GOLD"]).pack(pady=(28, 4))

        ctk.CTkLabel(self,
                     text="Premium code unlocks all 53 tweaks on this PC.",
                     font=("Inter", 11), text_color=theme["MUTED"]).pack(pady=(0, 20))

        self.entry = ctk.CTkEntry(self, width=280, height=44,
                                  font=("JetBrains Mono", 16),
                                  justify="center", show="",
                                  placeholder_text="XXXXXX",
                                  fg_color=theme["CARD"], border_color=theme["BORDER"])
        self.entry.pack(pady=(0, 6))
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self._submit())

        self.msg = ctk.CTkLabel(self, text="", font=("Inter", 11),
                                text_color=theme["MUTED"], wraplength=380)
        self.msg.pack(pady=(6, 10))

        btns = ctk.CTkFrame(self, fg_color=theme["BG"])
        btns.pack(pady=(4, 20))
        ctk.CTkButton(btns, text="Cancel", command=self.destroy,
                      fg_color="#242a33", hover_color="#2f3742",
                      text_color=theme["TEXT"], width=110, height=36,
                      font=("Rajdhani", 13, "bold")).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="SUBMIT", command=self._submit,
                      fg_color=theme["GOLD"], hover_color="#dbaf3e",
                      text_color="#141005", width=110, height=36,
                      font=("Rajdhani", 13, "bold")).pack(side="left", padx=6)

    def _submit(self):
        level, message = submit_code(self.entry.get())
        t = self.theme
        if level in ("unlock", "already"):
            color = t["ACCENT"]
        elif level == "owner_unlock":
            color = t["GOLD"]
        elif level == "partner_unlock":
            color = "#2dd4bf"
        else:
            color = t["DANGER"]
        self.msg.configure(text=message, text_color=color)
        if level in ("unlock", "owner_unlock", "partner_unlock"):
            # Store level so on_result can show the partner welcome popup
            self._final_level = level
            self.after(1100, self._finalize)

    def _finalize(self):
        # Trigger main window rebuild first, then show welcome popup for partners
        try:
            self.on_result()
        finally:
            level = getattr(self, "_final_level", None)
            self.destroy()
            if level == "partner_unlock":
                # Show welcome on next tick so parent has finished rebuilding
                try:
                    root = self.master
                    root.after(200, lambda: PartnerWelcome(root, self.theme))
                except Exception:
                    pass


# ============================================================
# Main App
# ============================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.theme_name, self.theme = get_theme()
        self.title(f"{APP_NAME} \u2014 Windows Gaming Optimizer")
        # Set window icon if available
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if getattr(sys, "frozen", False):
                icon_path = os.path.join(sys._MEIPASS, "icon.ico") if hasattr(sys, "_MEIPASS") else icon_path
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass
        self.geometry("980x840")
        self.minsize(880, 700)
        self.configure(fg_color=self.theme["BG"])
        # fully opaque window (no see-through)
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass
        # background image (custom > packaged default)
        self._bg_img = None
        self._has_custom_bg = False
        try:
            from PIL import Image
            # 1) Custom user-supplied background (owner/partner only)
            bg_path = None
            if is_owner() or is_partner():
                cust = get_custom_bg_path()
                if cust and os.path.exists(cust):
                    bg_path = cust
                    self._has_custom_bg = True
            # 2) Fallback to packaged default
            if not bg_path:
                bg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bg.png")
                if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                    bg_path = os.path.join(sys._MEIPASS, "bg.png")
            if os.path.exists(bg_path):
                pil = Image.open(bg_path).convert("RGB")
                self._bg_img = ctk.CTkImage(light_image=pil, dark_image=pil,
                                            size=(2560, 1600))
                self._bg_label = ctk.CTkLabel(self, image=self._bg_img, text="")
                self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                self._bg_label.lower()
        except Exception:
            pass
        # tray + rp start after window shown
        self.cards = []
        self.tray = TrayController(self)
        self.rp = RichPresence()
        self._build_ui()
        self._check_platform()
        updater.check_async(self._on_update_available)
        self.tray.start()
        self.rp.connect_async()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # honour --tray flag: start minimized
        if "--tray" in sys.argv and self.tray.available:
            self.after(200, self.withdraw)

    def _unlocked(self):
        return is_unlocked()

    def _build_ui(self):
        t = self.theme
        # ---------- Header ----------
        header = ctk.CTkFrame(self, fg_color="transparent", height=90)
        header.pack(fill="x", padx=16, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="\u25B2",
                     font=("Segoe UI", 40, "bold"),
                     text_color=t["ACCENT"]).grid(row=0, column=0, rowspan=2,
                                                  padx=(0, 12), sticky="w")

        ctk.CTkLabel(header, text="PS",
                     font=("Rajdhani", 32, "bold"),
                     text_color=t["TEXT"], anchor="w").grid(row=0, column=1, sticky="sw")

        ctk.CTkLabel(header,
                     text="Gaming Lounge  \u2014  63 Windows tweaks, fully reversible.   \u5F71  Move like a shadow.",
                     font=("Inter", 11), text_color=t["MUTED"],
                     anchor="w").grid(row=1, column=1, sticky="nw")

        # Badges (right)
        badges = ctk.CTkFrame(header, fg_color=t["BG"])
        badges.grid(row=0, column=2, rowspan=2, sticky="e")

        if self._unlocked():
            self.premium_badge = ctk.CTkLabel(
                badges, text="\u2605 PREMIUM",
                font=("Rajdhani", 12, "bold"),
                text_color=t["GOLD"], fg_color="#211a08", corner_radius=8,
                width=100, height=26,
            )
        else:
            self.premium_badge = ctk.CTkLabel(
                badges, text="FREE",
                font=("Rajdhani", 12, "bold"),
                text_color=t["MUTED"], fg_color="#161a1f", corner_radius=8,
                width=100, height=26,
            )
        self.premium_badge.pack(side="right", padx=(4, 0))

        # Partner badge (cyan/teal) — shown to partners + owners
        if is_partner():
            self.partner_badge = ctk.CTkLabel(
                badges, text="\U0001F91D PARTNER",
                font=("Rajdhani", 12, "bold"),
                text_color="#2dd4bf", fg_color="#0d2a26", corner_radius=8,
                width=100, height=26,
            )
            self.partner_badge.pack(side="right", padx=(4, 0))

        admin_txt = "\u2713 ADMIN" if is_admin() else "\u26A0 NO ADMIN"
        admin_color = t["ACCENT"] if is_admin() else t["DANGER"]
        self.admin_badge = ctk.CTkLabel(
            badges, text=admin_txt, font=("Rajdhani", 12, "bold"),
            text_color=admin_color, fg_color="#141a1f", corner_radius=8,
            width=100, height=26,
        )
        self.admin_badge.pack(side="right", padx=(4, 4))

        if is_owner_session():
            self.owner_badge = ctk.CTkLabel(
                badges, text="\U0001F451 OWNER",
                font=("Rajdhani", 12, "bold"),
                text_color=t["GOLD"], fg_color="#211a08", corner_radius=8,
                width=90, height=26,
            )
            self.owner_badge.pack(side="right", padx=(4, 4))

        # ---------- Admin warning banner ----------
        if not is_admin():
            warn = ctk.CTkFrame(self, fg_color="#3d1520",
                                corner_radius=10, border_width=1,
                                border_color=t["DANGER"])
            warn.pack(fill="x", padx=16, pady=(2, 4))
            warn.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(warn, text="\u26A0",
                         font=("Segoe UI Emoji", 22),
                         text_color=t["DANGER"], width=40).grid(row=0, column=0,
                                                                rowspan=2, padx=(12, 4), pady=8)
            ctk.CTkLabel(
                warn, text="NOT RUNNING AS ADMINISTRATOR",
                font=("Rajdhani", 14, "bold"),
                text_color=t["DANGER"], anchor="w",
            ).grid(row=0, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(
                warn,
                text="Most tweaks change system-wide registry keys and WILL silently fail without admin. "
                     "Click 'RUN AS ADMIN' on the right to relaunch elevated.",
                font=("Inter", 11), text_color=t["TEXT"],
                anchor="w", justify="left", wraplength=700,
            ).grid(row=1, column=1, sticky="w", pady=(0, 10))

        # ---------- Action bar ----------
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(4, 6))

        ctk.CTkButton(
            actions, text="\u26A1  APPLY ALL",
            command=self.apply_all,
            fg_color=t["ACCENT"], hover_color=t["ACCENT_DIM"], text_color="#0a0f0a",
            font=("Rajdhani", 14, "bold"), height=40, corner_radius=10, width=150,
        ).pack(side="left")

        ctk.CTkButton(
            actions, text="\u21BA  RESTORE ALL",
            command=self.restore_all,
            fg_color="#242a33", hover_color="#2f3742", text_color=t["TEXT"],
            font=("Rajdhani", 14, "bold"), height=40, corner_radius=10, width=140,
        ).pack(side="left", padx=(8, 0))

        # Undo last
        self.btn_undo = ctk.CTkButton(
            actions, text="\u238C  UNDO LAST",
            command=self.undo_last,
            fg_color="#2a1b47", hover_color="#3d2865", text_color=t["ACCENT"],
            font=("Rajdhani", 14, "bold"), height=40, corner_radius=10, width=140,
        )
        self.btn_undo.pack(side="left", padx=(8, 0))
        self._refresh_undo_state()

        if not self._unlocked():
            self.btn_unlock = ctk.CTkButton(
                actions, text="\U0001F512  ENTER CODE",
                command=self._open_unlock,
                fg_color=t["GOLD"], hover_color="#dbaf3e", text_color="#141005",
                font=("Rajdhani", 14, "bold"), height=40, corner_radius=10, width=150,
            )
            self.btn_unlock.pack(side="left", padx=(8, 0))
        else:
            self.btn_unlock = ctk.CTkButton(
                actions, text="\U0001F511  MANAGE CODE",
                command=self._open_unlock,
                fg_color="#242a33", hover_color="#2f3742", text_color=t["GOLD"],
                font=("Rajdhani", 13, "bold"), height=40, corner_radius=10, width=150,
            )
            self.btn_unlock.pack(side="left", padx=(8, 0))

        # Settings gear
        ctk.CTkButton(
            actions, text="\u2699  SETTINGS",
            command=self._open_settings,
            fg_color="#242a33", hover_color="#2f3742", text_color=t["TEXT"],
            font=("Rajdhani", 13, "bold"), height=40, corner_radius=10, width=140,
        ).pack(side="left", padx=(8, 0))

        # Reboot button - critical for tweaks that need reboot to take effect
        ctk.CTkButton(
            actions, text="\U0001F504  REBOOT",
            command=self._reboot_prompt,
            fg_color="#242a33", hover_color="#3d2865", text_color=t["ACCENT"],
            font=("Rajdhani", 13, "bold"), height=40, corner_radius=10, width=120,
        ).pack(side="left", padx=(8, 0))

        if not is_admin():
            ctk.CTkButton(
                actions, text="\U0001F510  RUN AS ADMIN",
                command=relaunch_as_admin,
                fg_color=t["DANGER"], hover_color="#c44660", text_color="#150507",
                font=("Rajdhani", 13, "bold"), height=40, corner_radius=10, width=160,
            ).pack(side="right")

        # ---------- Info banner: how to verify tweaks ----------
        info = ctk.CTkFrame(self, fg_color="#0f1a24",
                            corner_radius=10, border_width=1,
                            border_color=t["ACCENT_DIM"])
        info.pack(fill="x", padx=16, pady=(2, 4))
        info.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(info, text="\u2139",
                     font=("Segoe UI Emoji", 18),
                     text_color=t["ACCENT"], width=32).grid(row=0, column=0,
                                                            rowspan=2, padx=(12, 4), pady=8)
        ctk.CTkLabel(
            info, text="How to know a tweak really applied",
            font=("Rajdhani", 13, "bold"),
            text_color=t["ACCENT"], anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(8, 0))
        ctk.CTkLabel(
            info,
            text="If a tweak's switch turns ON and stays ON, the registry change succeeded. "
                 "Many tweaks are INVISIBLE in Windows Settings (they work at a lower level for games / drivers). "
                 "For power plans, visual effects, and Game Bar \u2192 REBOOT to see the change in Windows.",
            font=("Inter", 11), text_color=t["MUTED"],
            anchor="w", justify="left", wraplength=820,
        ).grid(row=1, column=1, sticky="w", pady=(0, 10))

        # ---------- Tabs: Free / Premium ----------
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="transparent",
            segmented_button_fg_color="#161a1f",
            segmented_button_selected_color=t["ACCENT"],
            segmented_button_selected_hover_color=t["ACCENT_DIM"],
            segmented_button_unselected_color="#242a33",
            segmented_button_unselected_hover_color="#2f3742",
            text_color=t["TEXT"],
            corner_radius=10,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(2, 4))

        # Add tabs with clear labels
        free_count = sum(1 for tw in TWEAKS if not tw["locked"])
        prem_count = sum(1 for tw in TWEAKS if tw["locked"] and not tw.get("partner_only"))
        part_count = sum(1 for tw in TWEAKS if tw.get("partner_only"))
        home_tab_name = "\U0001F3E0  HOME"
        free_tab_name = f"\u26A1  FREE  ({free_count})"
        prem_tab_name = f"\u2605  PREMIUM  ({prem_count})"
        part_tab_name = f"\U0001F91D  PARTNER  ({part_count})"
        self.tabview.add(home_tab_name)
        self.tabview.add(free_tab_name)
        self.tabview.add(prem_tab_name)
        # Partner tab only if this PC has partner or owner
        if is_partner():
            self.tabview.add(part_tab_name)
        # Force each tab's inner content frame transparent so custom bg shows through
        for tab_name in [home_tab_name, free_tab_name, prem_tab_name] + ([part_tab_name] if is_partner() else []):
            try:
                self.tabview.tab(tab_name).configure(fg_color="transparent")
            except Exception:
                pass
        self._home_tab_name = home_tab_name
        self._free_tab_name = free_tab_name
        self._prem_tab_name = prem_tab_name
        self._part_tab_name = part_tab_name

        # Home tab: live system stats
        self._build_home_tab(self.tabview.tab(home_tab_name))

        # Scrollable frames inside each tab — TRANSPARENT so custom backgrounds show through
        self.scroll_free = ctk.CTkScrollableFrame(
            self.tabview.tab(free_tab_name), fg_color="transparent", corner_radius=0
        )
        self.scroll_free.pack(fill="both", expand=True)

        self.scroll_prem = ctk.CTkScrollableFrame(
            self.tabview.tab(prem_tab_name), fg_color="transparent", corner_radius=0
        )
        self.scroll_prem.pack(fill="both", expand=True)

        self.scroll_part = None
        if is_partner():
            self.scroll_part = ctk.CTkScrollableFrame(
                self.tabview.tab(part_tab_name), fg_color="transparent", corner_radius=0
            )
            self.scroll_part.pack(fill="both", expand=True)

        self._render_cards()

        # ---------- Status bar ----------
        self.status_bar = ctk.CTkLabel(self, text=f"Ready.  Theme: {self.theme_name}",
                                       font=("Inter", 11),
                                       text_color=t["MUTED"], anchor="w")
        self.status_bar.pack(fill="x", padx=20, pady=(0, 6))

    def _build_home_tab(self, parent):
        """Home dashboard with live CPU/GPU/RAM stats."""
        import system_monitor
        t = self.theme

        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=6, pady=(8, 6))
        wrap.grid_columnconfigure((0, 1, 2), weight=1)

        # Save refs so we can update them
        self._home_labels = {}

        def make_stat_card(col, key, title, unit_suffix, ring_color):
            card = ctk.CTkFrame(wrap, fg_color=t["CARD"], corner_radius=14,
                                border_width=1, border_color=t["BORDER"])
            card.grid(row=0, column=col, padx=6, pady=6, sticky="nsew")

            ctk.CTkLabel(card, text=title,
                         font=("Rajdhani", 12, "bold"),
                         text_color=t["MUTED"], anchor="w").pack(anchor="w", padx=16, pady=(12, 0))

            big = ctk.CTkLabel(card, text="--",
                               font=("Rajdhani", 34, "bold"),
                               text_color=ring_color)
            big.pack(anchor="w", padx=16, pady=(0, 4))

            bar = ctk.CTkProgressBar(card, height=8, corner_radius=4,
                                     progress_color=ring_color,
                                     fg_color=t["BORDER"])
            bar.set(0)
            bar.pack(fill="x", padx=16, pady=(0, 8))

            sub = ctk.CTkLabel(card, text=unit_suffix,
                               font=("Inter", 10),
                               text_color=t["MUTED"], anchor="w")
            sub.pack(anchor="w", padx=16, pady=(0, 12))

            self._home_labels[key] = (big, bar, sub)

        make_stat_card(0, "cpu", "\u26A1  CPU USAGE",     "\u2014",  t["ACCENT"])
        make_stat_card(1, "gpu", "\U0001F3AE  GPU USAGE", "\u2014",  "#ff5a7c")
        make_stat_card(2, "ram", "\U0001F4BE  RAM USAGE", "\u2014",  t["GOLD"])

        # Temperature Row
        temp_row = ctk.CTkFrame(wrap, fg_color=t["CARD"], corner_radius=14,
                                border_width=1, border_color=t["BORDER"])
        temp_row.grid(row=1, column=0, columnspan=3, padx=6, pady=(4, 8), sticky="ew")
        temp_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(temp_row, text="\U0001F321  TEMPERATURE MONITOR",
                     font=("Rajdhani", 13, "bold"),
                     text_color=t["MUTED"], anchor="w").grid(row=0, column=0, columnspan=2,
                                                             padx=16, pady=(10, 4), sticky="w")
        cpu_t = ctk.CTkLabel(temp_row, text="CPU:  \u2014",
                             font=("Rajdhani", 22, "bold"),
                             text_color=t["ACCENT"])
        cpu_t.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")
        gpu_t = ctk.CTkLabel(temp_row, text="GPU:  \u2014",
                             font=("Rajdhani", 22, "bold"),
                             text_color="#ff5a7c")
        gpu_t.grid(row=1, column=1, padx=16, pady=(0, 12), sticky="w")
        self._home_labels["cpu_temp"] = cpu_t
        self._home_labels["gpu_temp"] = gpu_t

        # NVIDIA Profile Inspector partner card (only for partners)
        if is_partner():
            import nvidia_inspector
            nv_card = ctk.CTkFrame(wrap, fg_color="#0d2a26", corner_radius=14,
                                   border_width=1, border_color="#2dd4bf")
            nv_card.grid(row=2, column=0, columnspan=3, padx=6, pady=(4, 8), sticky="ew")

            ctk.CTkLabel(nv_card,
                         text="\U0001F3AE  NVIDIA PROFILE INSPECTOR  \u2014  Partner Auto-Optimize",
                         font=("Rajdhani", 14, "bold"),
                         text_color="#2dd4bf", anchor="w").pack(anchor="w", padx=16, pady=(12, 2))

            found = nvidia_inspector.find_inspector()
            if found:
                info_text = f"Detected: {found}\nWe'll silently apply the Kage max-performance NVIDIA profile."
                nv_msg_color = t["MUTED"]
            else:
                info_text = ("Not found. Download from "
                             "https://github.com/Orbmu2k/nvidiaProfileInspector "
                             "and put it in Desktop or Downloads, then click detect.")
                nv_msg_color = t["MUTED"]

            self._nv_status = ctk.CTkLabel(nv_card, text=info_text,
                                           font=("Inter", 10), text_color=nv_msg_color,
                                           justify="left", anchor="w", wraplength=800)
            self._nv_status.pack(anchor="w", padx=16, pady=(0, 8))

            bar = ctk.CTkFrame(nv_card, fg_color="#0d2a26")
            bar.pack(anchor="w", padx=16, pady=(0, 14))

            ctk.CTkButton(
                bar, text="\U0001F50D  RE-DETECT",
                command=self._nv_detect,
                fg_color="#242a33", hover_color="#2f3742",
                text_color=t["TEXT"], font=("Rajdhani", 12, "bold"),
                height=32, corner_radius=8, width=130,
            ).pack(side="left", padx=(0, 6))

            ctk.CTkButton(
                bar, text="\u26A1  APPLY OPTIMIZED PROFILE",
                command=self._nv_apply,
                fg_color="#2dd4bf", hover_color="#14b8a6", text_color="#053b32",
                font=("Rajdhani", 12, "bold"),
                height=32, corner_radius=8, width=220,
            ).pack(side="left", padx=(0, 6))

            ctk.CTkButton(
                bar, text="OPEN GUI",
                command=self._nv_launch_gui,
                fg_color="#242a33", hover_color="#2f3742",
                text_color=t["TEXT"], font=("Rajdhani", 12, "bold"),
                height=32, corner_radius=8, width=110,
            ).pack(side="left")

        # Start the live update loop
        self._tick_home()

    def _tick_home(self):
        """Update home tab stats every 1500ms."""
        try:
            import system_monitor
            snap = system_monitor.snapshot()

            cpu_big, cpu_bar, cpu_sub = self._home_labels["cpu"]
            cpu_big.configure(text=f"{snap['cpu_pct']:.0f}%")
            cpu_bar.set(snap["cpu_pct"] / 100)
            cpu_sub.configure(text="Overall load")

            gpu_big, gpu_bar, gpu_sub = self._home_labels["gpu"]
            if snap["gpu_present"]:
                gpu_big.configure(text=f"{snap['gpu_pct']:.0f}%")
                gpu_bar.set(snap["gpu_pct"] / 100)
                gpu_sub.configure(text="NVIDIA GPU")
            else:
                gpu_big.configure(text="\u2014")
                gpu_bar.set(0)
                gpu_sub.configure(text="No NVIDIA GPU detected")

            ram_big, ram_bar, ram_sub = self._home_labels["ram"]
            ram_big.configure(text=f"{snap['ram_pct']:.0f}%")
            ram_bar.set(snap["ram_pct"] / 100)
            ram_sub.configure(text=f"{snap['ram_used_gb']:.1f} GB / {snap['ram_total_gb']:.1f} GB")

            ct = snap["cpu_temp"]
            self._home_labels["cpu_temp"].configure(
                text=f"CPU:  {ct:.0f}\u00B0C" if ct is not None else "CPU:  n/a"
            )
            gt = snap["gpu_temp"]
            self._home_labels["gpu_temp"].configure(
                text=f"GPU:  {gt:.0f}\u00B0C" if gt is not None else "GPU:  n/a"
            )
        except Exception:
            pass
        self.after(1500, self._tick_home)

    def _nv_detect(self):
        import nvidia_inspector
        found = nvidia_inspector.find_inspector()
        if found:
            self._nv_status.configure(
                text=f"Detected: {found}",
                text_color=self.theme["ACCENT"],
            )
        else:
            self._nv_status.configure(
                text="Still not found. Put nvidiaProfileInspector.exe in Desktop or Downloads and click detect again.",
                text_color=self.theme["DANGER"],
            )

    def _nv_apply(self):
        import nvidia_inspector
        found = nvidia_inspector.find_inspector()
        if not found:
            messagebox.showwarning(
                "Not installed",
                "nvidiaProfileInspector.exe not found. Download it and put it in Desktop or Downloads."
            )
            return
        if not messagebox.askyesno(
            "Apply optimized NVIDIA profile",
            "Apply the Kage max-performance NVIDIA driver profile globally?\n\n"
            "Includes: Prefer Max Performance, Threaded Optimization ON, "
            "Low Latency ULTRA, Shader Cache Unlimited, VSync OFF."
        ):
            return
        ok, msg = nvidia_inspector.apply_optimized(found)
        self.set_status(msg, self.theme["ACCENT"] if ok else self.theme["DANGER"])

    def _nv_launch_gui(self):
        import nvidia_inspector
        found = nvidia_inspector.find_inspector()
        if not found:
            messagebox.showwarning("Not installed",
                                   "nvidiaProfileInspector.exe not found.")
            return
        nvidia_inspector.launch_gui(found)

    def _render_cards(self):
        for w in self.scroll_free.winfo_children():
            w.destroy()
        for w in self.scroll_prem.winfo_children():
            w.destroy()
        if self.scroll_part is not None:
            for w in self.scroll_part.winfo_children():
                w.destroy()
        self.cards = []
        unlocked = self._unlocked()
        t = self.theme

        # Bucket tweaks into free / premium / partner by tier
        free_by_cat = {}
        prem_by_cat = {}
        part_by_cat = {}
        for tw in TWEAKS:
            if tw.get("partner_only"):
                part_by_cat.setdefault(tw["category"], []).append(tw)
            elif tw["locked"]:
                prem_by_cat.setdefault(tw["category"], []).append(tw)
            else:
                free_by_cat.setdefault(tw["category"], []).append(tw)

        def render_bucket(parent, by_cat, tier):
            """tier ∈ {'free', 'premium', 'partner'}"""
            for cat in CATEGORIES:
                items = by_cat.get(cat, [])
                if not items:
                    continue

                if tier == "partner":
                    header_color = "#2dd4bf"  # cyan
                    marker = "  \U0001F91D"
                elif tier == "premium":
                    header_color = t["GOLD"]
                    marker = "  \U0001F512" if not unlocked else "  \u2605"
                else:
                    header_color = t["ACCENT"]
                    marker = ""

                header = ctk.CTkFrame(parent, fg_color=t["BG"], height=36)
                header.pack(fill="x", pady=(14, 4), padx=6)
                icon = CATEGORY_ICONS.get(cat, "\u25CF")
                ctk.CTkLabel(
                    header,
                    text=f"{icon}   {cat.upper()}{marker}",
                    font=("Rajdhani", 15, "bold"),
                    text_color=header_color if (tier == "free" or unlocked or tier == "partner")
                                          else t["MUTED_LOCKED"],
                    anchor="w",
                ).pack(side="left")

                ctk.CTkLabel(
                    header, text=f"{len(items)} tweaks",
                    font=("Inter", 10),
                    text_color=t["MUTED"], anchor="e",
                ).pack(side="right", padx=(0, 4))

                for tw in items:
                    card = TweakCard(parent, tw, self.on_toggle, unlocked, t,
                                     transparent_bg=self._has_custom_bg)
                    card.pack(fill="x", padx=6, pady=4)
                    self.cards.append(card)

        # Free tab: only free tweaks
        render_bucket(self.scroll_free, free_by_cat, "free")

        # Premium tab: premium tweaks with locked/unlocked visuals
        if not unlocked:
            banner = ctk.CTkFrame(self.scroll_prem, fg_color="#211a08",
                                  corner_radius=10, border_width=1,
                                  border_color=t["GOLD"])
            banner.pack(fill="x", padx=6, pady=(6, 10))
            ctk.CTkLabel(
                banner,
                text="\U0001F512  PREMIUM LOCKED",
                font=("Rajdhani", 16, "bold"),
                text_color=t["GOLD"], anchor="w",
            ).pack(fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(
                banner,
                text="Enter your unlock code to activate these tweaks. "
                     "Click 'ENTER CODE' up top.",
                font=("Inter", 11),
                text_color=t["MUTED"], anchor="w", justify="left",
            ).pack(fill="x", padx=14, pady=(2, 12))
        render_bucket(self.scroll_prem, prem_by_cat, "premium")

        # Partner tab (visible only if partner)
        if self.scroll_part is not None:
            banner = ctk.CTkFrame(self.scroll_part, fg_color="#0d2a26",
                                  corner_radius=10, border_width=1,
                                  border_color="#2dd4bf")
            banner.pack(fill="x", padx=6, pady=(6, 10))
            ctk.CTkLabel(
                banner,
                text="\U0001F91D  PARTNER EXCLUSIVE",
                font=("Rajdhani", 16, "bold"),
                text_color="#2dd4bf", anchor="w",
            ).pack(fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(
                banner,
                text="Hand-picked hardcore tweaks reserved for partners. "
                     "Use Settings \u2192 Customize to change the app background.",
                font=("Inter", 11),
                text_color=t["MUTED"], anchor="w", justify="left",
            ).pack(fill="x", padx=14, pady=(2, 12))
            render_bucket(self.scroll_part, part_by_cat, "partner")

    def _on_close(self):
        """Hide to tray if available, otherwise quit."""
        if self.tray.available:
            try:
                self.withdraw()
                self.tray.notify("Kage Utility", "Still running \u2014 tray icon in the system tray.")
            except Exception:
                self.destroy()
        else:
            try:
                self.rp.close()
            except Exception:
                pass
            self.destroy()

    def _refresh_undo_state(self):
        if hasattr(self, "btn_undo"):
            if history.has_undo():
                last = history.peek()
                self.btn_undo.configure(
                    state="normal",
                    text=f"\u238C  UNDO: {last['title'][:18]}\u2026" if len(last["title"]) > 18 else f"\u238C  UNDO",
                )
            else:
                self.btn_undo.configure(state="disabled", text="\u238C  UNDO LAST")

    def undo_last(self):
        tw = history.pop()
        if not tw:
            return

        def worker():
            self.set_status(f"Undoing: {tw['title']}\u2026", self.theme["ACCENT"])
            try:
                tw["restore"]()
                self.set_status(f"\u21BA Undid: {tw['title']}", self.theme["MUTED"])
            except Exception as e:
                self.set_status(f"\u2717 Undo failed on '{tw['title']}': {e}",
                                self.theme["DANGER"])
            for card in self.cards:
                if card.tweak["id"] == tw["id"]:
                    card.refresh_status()
                    break
            self._refresh_undo_state()

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_available(self, info):
        # Called from a background thread — marshal to Tk main thread
        def show():
            msg = (
                f"Kage Utility {info['version']} is available "
                f"(you're on {updater.APP_VERSION}).\n\n"
                f"{info.get('notes', '')[:300] or 'Open the release page for details.'}\n\n"
                "Open the download page now?"
            )
            if messagebox.askyesno("Update available", msg):
                try:
                    import webbrowser
                    webbrowser.open(info["url"])
                except Exception:
                    pass

        self.after(600, show)

    def _check_platform(self):
        if platform.system() != "Windows":
            messagebox.showwarning(
                "Not Windows",
                "FragBoost is designed for Windows 11. On other platforms "
                "the tweaks will silently fail \u2014 nothing will be harmed."
            )
        if is_owner_revoked():
            self.set_status(
                "\U0001F451  Owner has revoked premium on this PC. Enter owner code to restore.",
                self.theme["DANGER"],
            )

    def set_status(self, msg, color=None):
        if color is None:
            color = self.theme["MUTED"]
        self.status_bar.configure(text=msg, text_color=color)

    def _open_unlock(self):
        UnlockDialog(self, self.theme, on_result=self._rebuild)

    def _open_settings(self):
        SettingsDialog(
            self, self.theme,
            on_theme_change=self._on_theme_change,
            on_profile_apply=self._apply_profile_ids,
        )

    def _reboot_prompt(self):
        if messagebox.askyesno(
            "Reboot PC",
            "Reboot now so all applied tweaks fully take effect?\n\n"
            "Save any open work first. Windows will restart in 10 seconds."
        ):
            try:
                import subprocess
                subprocess.Popen(
                    ["shutdown", "/r", "/t", "10", "/c", "Kage Utility — applying tweaks"],
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self.set_status("\U0001F504  Rebooting in 10 seconds...", self.theme["ACCENT"])
            except Exception as e:
                self.set_status(f"\u2717 Reboot failed: {e}", self.theme["DANGER"])

    def _on_theme_change(self, name):
        self.theme_name = name
        from settings_ui import get_theme as gt
        _, self.theme = gt()
        self.configure(fg_color=self.theme["BG"])
        self._rebuild()

    def _rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.cards = []
        self._build_ui()

    def _apply_profile_ids(self, tweak_ids):
        unlocked = self._unlocked()

        def worker():
            applied = skipped = failed = 0
            for tid in tweak_ids:
                tw = next((x for x in TWEAKS if x["id"] == tid), None)
                if not tw:
                    continue
                if tw["locked"] and not unlocked:
                    skipped += 1
                    continue
                if tw.get("requires_admin") and not is_admin():
                    skipped += 1
                    continue
                self.set_status(f"Applying: {tw['title']}\u2026", self.theme["ACCENT"])
                try:
                    tw["apply"]()
                    applied += 1
                except Exception:
                    failed += 1
            for card in self.cards:
                card.refresh_status()
            self.set_status(
                f"\u2713 Profile applied: {applied} on, {skipped} skipped, {failed} failed.",
                self.theme["ACCENT"],
            )

        threading.Thread(target=worker, daemon=True).start()

    def on_toggle(self, tweak, wants_on, card):
        if tweak.get("requires_admin") and not is_admin():
            messagebox.showwarning(
                "Admin required",
                f"'{tweak['title']}' needs administrator rights.\n\n"
                "Click 'RUN AS ADMIN' to relaunch elevated."
            )
            card.refresh_status()
            return

        def worker():
            self.set_status(f"Working: {tweak['title']}\u2026", self.theme["ACCENT"])
            try:
                if wants_on:
                    result = tweak["apply"]()
                    # One-shot actions (clean temp, flush DNS) don't have a "stays on" state,
                    # so we skip the verify step entirely.
                    is_action = tweak.get("action", False)
                    if is_action:
                        # Special result reporting for clean_temp (returns MB)
                        if tweak["id"] == "clean_temp" and isinstance(result, int):
                            mb = result / (1024 * 1024)
                            self.set_status(f"\u2713 Cleaned {mb:.1f} MB of temp files.",
                                            self.theme["ACCENT"])
                        else:
                            self.set_status(f"\u2713 Ran: {tweak['title']}",
                                            self.theme["ACCENT"])
                        history.record(tweak)
                    else:
                        # Persistent state — verify by reading real state
                        try:
                            actual = tweak["status"]()
                        except Exception:
                            actual = "off"
                        if actual != "on":
                            history.record(tweak)
                            if not is_admin():
                                self.set_status(
                                    f"\u26A0 '{tweak['title']}' didn't stick. "
                                    "You're NOT running as admin \u2014 click 'RUN AS ADMIN' at the top-right.",
                                    self.theme["DANGER"],
                                )
                            else:
                                self.set_status(
                                    f"\u2713 Applied '{tweak['title']}' \u2014 "
                                    "reboot recommended for the change to become visible.",
                                    self.theme["GOLD"],
                                )
                        else:
                            history.record(tweak)
                            self.rp.update(f"Applied: {tweak['title'][:40]}",
                                           "Optimizing with Kage")
                            self.set_status(f"\u2713 Applied: {tweak['title']}  (reboot may be needed for full effect)",
                                            self.theme["ACCENT"])
                else:
                    tweak["restore"]()
                    history.drop(tweak["id"])
                    self.set_status(f"\u21BA Restored: {tweak['title']}",
                                    self.theme["MUTED"])
            except PermissionError as pe:
                if not is_admin():
                    self.set_status(
                        f"\u2717 '{tweak['title']}' needs Administrator. Click 'RUN AS ADMIN'.",
                        self.theme["DANGER"],
                    )
                else:
                    self.set_status(
                        f"\u2717 '{tweak['title']}' blocked by Windows even as admin: {pe}",
                        self.theme["DANGER"],
                    )
            except Exception as e:
                self.set_status(f"\u2717 Error on '{tweak['title']}': {e}",
                                self.theme["DANGER"])
            finally:
                card.refresh_status()
                self._refresh_undo_state()

        threading.Thread(target=worker, daemon=True).start()

    def apply_all(self):
        unlocked = self._unlocked()
        eligible = [c for c in self.cards if not (c.tweak["locked"] and not unlocked)]
        locked_count = len(self.cards) - len(eligible)

        confirm_text = (
            f"Apply {len(eligible)} tweaks?\n\n"
            "Every change is backed up and reversible via 'Restore All'."
        )
        if locked_count:
            confirm_text += f"\n\n\U0001F512 {locked_count} premium tweaks will be skipped."

        if not messagebox.askyesno("Apply all", confirm_text):
            return

        def worker():
            for card in eligible:
                tw = card.tweak
                if tw.get("requires_admin") and not is_admin():
                    self.set_status(f"Skipping (needs admin): {tw['title']}",
                                    self.theme["DANGER"])
                    continue
                self.set_status(f"Applying: {tw['title']}\u2026", self.theme["ACCENT"])
                try:
                    tw["apply"]()
                    history.record(tw)
                except Exception as e:
                    self.set_status(f"\u2717 {tw['title']}: {e}", self.theme["DANGER"])
                card.refresh_status()
            self._refresh_undo_state()
            self.set_status(
                "\u2713 Done. Reboot recommended for full effect.", self.theme["ACCENT"]
            )

        threading.Thread(target=worker, daemon=True).start()

    def restore_all(self):
        if not messagebox.askyesno(
            "Restore defaults",
            "Restore every setting FragBoost changed back to its original value?"
        ):
            return

        def worker():
            for card in self.cards:
                if card.locked_visual:
                    continue
                tw = card.tweak
                self.set_status(f"Restoring: {tw['title']}\u2026", self.theme["MUTED"])
                try:
                    tw["restore"]()
                except Exception as e:
                    self.set_status(f"\u2717 {tw['title']}: {e}", self.theme["DANGER"])
                card.refresh_status()
            history.clear()
            self._refresh_undo_state()
            self.set_status("\u21BA All settings restored.", self.theme["MUTED"])

        threading.Thread(target=worker, daemon=True).start()


def main():
    # Bootstrap: create a hidden root, show splash, then reveal the app.
    root = ctk.CTk()
    root.withdraw()  # hide the root while splash is up

    app_holder = {"app": None}

    def build_app():
        try:
            root.destroy()
        except Exception:
            pass
        app_holder["app"] = App()
        app_holder["app"].mainloop()

    Splash.show(root, on_done=build_app)
    # Startup sound is OPT-IN via Settings → System → "Startup sound"
    try:
        from settings_ui import load_settings
        if load_settings().get("startup_sound", False):
            play_intro()
    except Exception:
        pass
    root.mainloop()


if __name__ == "__main__":
    main()
