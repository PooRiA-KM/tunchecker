import time
import subprocess
import threading
import json
import os
import socket
import ipaddress
import re
from datetime import datetime

import requests
import customtkinter as ctk
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import psutil

# ============================================
# تنظیمات ثابت و پالت رنگی
# ============================================
CONFIG_FILE = "config.json"
LOG_FILE = "app_logs.txt"

# پالت رنگی تم دارک مدرن
COLORS = {
    "bg_primary": "#0d1117",       # مشکی خاکستری
    "bg_secondary": "#161b22",     # خاکستری تیره
    "bg_tertiary": "#21262d",      # خاکستری متوسط
    "border": "#30363d",           # حاشیه
    "text_primary": "#c9d1d9",     # متن روشن
    "text_secondary": "#8b949e",   # متن خاکستری
    "accent_blue": "#58a6ff",      # آبی ملایم
    "accent_green": "#3fb950",     # سبز ملایم
    "accent_red": "#f85149",       # قرمز ملایم
    "accent_yellow": "#d29922",    # زرد ملایم
    "accent_purple": "#bc8cff",    # بنفش ملایم
}

# تنظیمات ظاهری CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ============================================
# کامپوننت کارت سفارشی
# ============================================
class CardFrame(ctk.CTkFrame):
    """یک کارت مدرن با عنوان و حاشیه"""
    def __init__(self, parent, title, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_secondary"],
                         corner_radius=12, border_width=1,
                         border_color=COLORS["border"], **kwargs)

        # عنوان کارت
        self.title_label = ctk.CTkLabel(
            self, text=title, font=("Segoe UI", 14, "bold"),
            text_color=COLORS["accent_blue"]
        )
        self.title_label.pack(anchor="w", padx=12, pady=(10, 4))


class StatusBadge(ctk.CTkFrame):
    """بج وضعیت با رنگ شاخص"""
    def __init__(self, parent, text="Inactive", color="gray", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.dot = ctk.CTkLabel(self, text="●", font=("Segoe UI", 16),
                                text_color=color)
        self.dot.pack(side="left", padx=(0, 6))
        self.label = ctk.CTkLabel(self, text=text, font=("Segoe UI", 13, "bold"),
                                  text_color=color)
        self.label.pack(side="left")
        self.current_color = color
        self.current_text = text

    def update_status(self, text, color):
        if text != self.current_text or color != self.current_color:
            self.dot.configure(text_color=color)
            self.label.configure(text=text, text_color=color)
            self.current_text = text
            self.current_color = color


# ============================================
# کلاس اصلی برنامه
# ============================================
class VPNMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TUN Checker")
        self.root.geometry("560x850")  # کمی ارتفاع را بیشتر کردم برای چک‌باکس‌های جدید
        self.root.minsize(520, 800)
        self.root.configure(fg_color=COLORS["bg_primary"])

        # متغیرهای وضعیت
        self.is_running = False
        self.monitor_thread = None
        self.tray_icon = None

        # متغیرهای نمایش/مخفی‌سازی پسورد
        self.show_token = False
        self.show_chat_id = False

        # متغیرهای ردیابی وضعیت برای جلوگیری از اسپم
        self.last_overall_status = None
        self.last_alert_time = 0  # ✅ جدید: زمان آخرین هشدار
        self.alert_cooldown = 15  # ✅ جدید: حداقل ۶۰ ثانیه بین دو هشدار

        # متغیرهای چک‌باکس‌ها
        self.ping_enabled = ctk.BooleanVar(value=False)
        self.local_cidr_enabled = ctk.BooleanVar(value=False)  # جدید
        self.public_ip_enabled = ctk.BooleanVar(value=False)  # جدید

        self.setup_ui()
        self.refresh_adapters()
        self.load_settings()
        self.log("Application initialized successfully.")

        # تغییر رفتار دکمه ضربدر پنجره به پنهان شدن در Tray
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # راه‌اندازی آیکون تری
        self.setup_tray()

    # ============================================
    # راه‌اندازی UI
    # ============================================
    def setup_ui(self):
        default_font = ("Segoe UI", 13)
        small_font = ("Segoe UI", 12)

        self.tabview = ctk.CTkTabview(
            self.root, fg_color=COLORS["bg_primary"],
            segmented_button_fg_color=COLORS["bg_secondary"],
            segmented_button_selected_color=COLORS["accent_blue"],
            segmented_button_selected_hover_color=COLORS["accent_blue"],
            segmented_button_unselected_color=COLORS["bg_secondary"],
            segmented_button_unselected_hover_color=COLORS["bg_tertiary"],
            corner_radius=12
        )
        self.tabview.pack(fill="both", expand=True, padx=8, pady=8)

        # تب 1: تنظیمات
        self.tab_settings = self.tabview.add("⚙️ Settings")
        self.tab_settings.configure(fg_color=COLORS["bg_primary"])

        # تب 2: مانیتورینگ
        self.tab_monitor = self.tabview.add("📊 Monitor")
        self.tab_monitor.configure(fg_color=COLORS["bg_primary"])

        self._build_settings_tab(default_font, small_font)
        self._build_monitor_tab(default_font, small_font)

    def _build_settings_tab(self, default_font, small_font):
        """ساخت تب تنظیمات با کارت‌های مجزا"""
        # اسکرول‌ویو برای تب تنظیمات
        scroll_frame = ctk.CTkScrollableFrame(
            self.tab_settings, fg_color="transparent",
            scrollbar_button_color=COLORS["bg_tertiary"]
        )
        scroll_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # --- کارت 1: Network Adapter & Interval ---
        card1 = CardFrame(scroll_frame, "🌐 Network Adapter & Interval")
        card1.pack(fill="x", padx=3, pady=4)

        inner1 = ctk.CTkFrame(card1, fg_color="transparent")
        inner1.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(inner1, text="Adapter:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=0, column=0, sticky="w", pady=5)
        self.combo_adapters = ctk.CTkComboBox(
            inner1, state="readonly", width=280, font=default_font,
            fg_color=COLORS["bg_tertiary"], button_color=COLORS["accent_blue"],
            button_hover_color=COLORS["accent_blue"],
            dropdown_fg_color=COLORS["bg_secondary"],
            dropdown_hover_color=COLORS["bg_tertiary"],
            dropdown_text_color=COLORS["text_primary"]
        )
        self.combo_adapters.grid(row=0, column=1, padx=10, pady=5)

        btn_refresh = ctk.CTkButton(
            inner1, text="🔄", width=40, font=default_font,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["border"],
            command=self.refresh_adapters
        )
        btn_refresh.grid(row=0, column=2, padx=2)

        ctk.CTkLabel(inner1, text="Check Interval (sec):", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", pady=5)
        self.entry_interval = ctk.CTkEntry(
            inner1, width=100, font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="10"
        )
        self.entry_interval.insert(0, "10")
        self.entry_interval.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # --- کارت 2: Telegram Bot & Proxy ---
        card2 = CardFrame(scroll_frame, "🤖 Telegram Bot & Proxy Settings")
        card2.pack(fill="x", padx=3, pady=4)

        inner2 = ctk.CTkFrame(card2, fg_color="transparent")
        inner2.pack(fill="x", padx=10, pady=(0, 8))

        # Bot Token
        ctk.CTkLabel(inner2, text="Bot Token:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=0, column=0, sticky="w", pady=4)
        self.entry_bot_token = ctk.CTkEntry(
            inner2, width=280, show="*", font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="Enter bot token"
        )
        self.entry_bot_token.grid(row=0, column=1, padx=10, pady=4)
        self.btn_toggle_token = ctk.CTkButton(
            inner2, text="👁️", width=40,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["border"],
            command=self.toggle_token_visibility
        )
        self.btn_toggle_token.grid(row=0, column=2, padx=2)

        # Chat ID
        ctk.CTkLabel(inner2, text="Chat ID:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", pady=4)
        self.entry_chat_id = ctk.CTkEntry(
            inner2, width=280, show="*", font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="Enter chat ID"
        )
        self.entry_chat_id.grid(row=1, column=1, padx=10, pady=4)
        self.btn_toggle_chat_id = ctk.CTkButton(
            inner2, text="👁️", width=40,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["border"],
            command=self.toggle_chat_id_visibility
        )
        self.btn_toggle_chat_id.grid(row=1, column=2, padx=2)

        # Proxy
        ctk.CTkLabel(inner2, text="Proxy IP (Optional):", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=2, column=0, sticky="w", pady=4)
        self.entry_proxy_ip = ctk.CTkEntry(
            inner2, width=150, font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="127.0.0.1"
        )
        self.entry_proxy_ip.grid(row=2, column=1, sticky="w", padx=10, pady=4)

        ctk.CTkLabel(inner2, text="Port:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=3, column=0, sticky="w", pady=4)
        self.entry_proxy_port = ctk.CTkEntry(
            inner2, width=100, font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="8080"
        )
        self.entry_proxy_port.grid(row=3, column=1, sticky="w", padx=10, pady=4)

        # دکمه تست
        self.btn_test_telegram = ctk.CTkButton(
            card2, text="🔔 Test Bot Connection", font=("Segoe UI", 13, "bold"),
            fg_color=COLORS["accent_purple"], hover_color="#7c3aed",
            height=36, command=self.test_telegram
        )
        self.btn_test_telegram.pack(fill="x", padx=10, pady=(0, 10))

        # --- کارت 3: Target Settings ---
        card3 = CardFrame(scroll_frame, "🎯 Target Settings")
        card3.pack(fill="x", padx=3, pady=4)

        inner3 = ctk.CTkFrame(card3, fg_color="transparent")
        inner3.pack(fill="x", padx=10, pady=(0, 8))

        # Ping
        self.chk_ping = ctk.CTkCheckBox(
            inner3, text="Enable Ping Check", variable=self.ping_enabled,
            font=default_font, text_color=COLORS["text_primary"],
            fg_color=COLORS["accent_blue"], hover_color=COLORS["accent_blue"]
        )
        self.chk_ping.grid(row=0, column=0, columnspan=2, sticky="w", pady=4)

        ctk.CTkLabel(inner3, text="Ping Target IP:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", pady=4)
        self.entry_ping_ip = ctk.CTkEntry(
            inner3, width=200, font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="192.168.1.1"
        )
        self.entry_ping_ip.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        # Local CIDR (جدید)
        self.chk_local_cidr = ctk.CTkCheckBox(
            inner3, text="Enable Local CIDR Check", variable=self.local_cidr_enabled,
            font=default_font, text_color=COLORS["text_primary"],
            fg_color=COLORS["accent_blue"], hover_color=COLORS["accent_blue"]
        )
        self.chk_local_cidr.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 4))

        ctk.CTkLabel(inner3, text="Expected Local CIDR:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=3, column=0, sticky="w", pady=4)
        self.entry_local_cidr = ctk.CTkEntry(
            inner3, width=200, font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="192.168.0.0/16"
        )
        self.entry_local_cidr.insert(0, "192.168.0.0/16")
        self.entry_local_cidr.grid(row=3, column=1, sticky="w", padx=10, pady=4)

        # Public IP (جدید)
        self.chk_public_ip = ctk.CTkCheckBox(
            inner3, text="Enable Public IP Check", variable=self.public_ip_enabled,
            font=default_font, text_color=COLORS["text_primary"],
            fg_color=COLORS["accent_blue"], hover_color=COLORS["accent_blue"]
        )
        self.chk_public_ip.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        ctk.CTkLabel(inner3, text="Expected Public IP:", font=default_font,
                     text_color=COLORS["text_secondary"]).grid(row=5, column=0, sticky="w", pady=4)
        self.entry_public_ip = ctk.CTkEntry(
            inner3, width=200, font=default_font,
            fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"], placeholder_text="203.0.113.5"
        )
        self.entry_public_ip.grid(row=5, column=1, sticky="w", padx=10, pady=4)

        # دکمه ذخیره
        self.btn_save_settings = ctk.CTkButton(
            card3, text="💾 Save All Settings", font=("Segoe UI", 13, "bold"),
            fg_color=COLORS["accent_green"], hover_color="#059669",
            height=36, command=self.save_settings
        )
        self.btn_save_settings.pack(fill="x", padx=10, pady=(10, 10))

    def _build_monitor_tab(self, default_font, small_font):
        """ساخت تب مانیتورینگ با کارت‌های وضعیت زنده"""
        # --- نوار وضعیت بالا ---
        top_bar = ctk.CTkFrame(self.tab_monitor, fg_color=COLORS["bg_secondary"],
                               corner_radius=12, border_width=1,
                               border_color=COLORS["border"])
        top_bar.pack(fill="x", padx=3, pady=3)

        status_row = ctk.CTkFrame(top_bar, fg_color="transparent")
        status_row.pack(fill="x", padx=8, pady=8)

        # دکمه Start/Stop
        self.btn_toggle = ctk.CTkButton(
            status_row, text="▶ Start Monitoring",
            font=("Segoe UI", 14, "bold"),
            fg_color=COLORS["accent_green"], hover_color="#059669",
            height=40, corner_radius=8, command=self.toggle_monitoring
        )
        self.btn_toggle.pack(side="left", padx=(0, 15))

        # بج وضعیت کلی
        self.badge_overall = StatusBadge(status_row, "Inactive", COLORS["text_secondary"])
        self.badge_overall.pack(side="right")

        # لیبل وضعیت آداپتور
        self.lbl_status = ctk.CTkLabel(
            top_bar, text="Status: Inactive", font=("Segoe UI", 13),
            text_color=COLORS["text_secondary"]
        )
        self.lbl_status.pack(padx=8, pady=(0, 8), anchor="w")

        # --- کارت‌های وضعیت زنده ---
        cards_container = ctk.CTkFrame(self.tab_monitor, fg_color="transparent")
        cards_container.pack(fill="x", padx=3, pady=3)

        # کارت 1: Ping
        self.card_ping = CardFrame(cards_container, "📡 Ping Status")
        self.card_ping.pack(side="left", fill="both", expand=True, padx=(0, 2), pady=2)

        self.lbl_ping_target = ctk.CTkLabel(
            self.card_ping, text="Target: Not set", font=small_font,
            text_color=COLORS["text_secondary"]
        )
        self.lbl_ping_target.pack(padx=10, pady=(4, 2), anchor="w")

        self.lbl_ping_latency = ctk.CTkLabel(
            self.card_ping, text="-- ms", font=("Segoe UI", 26, "bold"),
            text_color=COLORS["text_secondary"]
        )
        self.lbl_ping_latency.pack(pady=4)

        self.badge_ping = StatusBadge(self.card_ping, "Not Checked", COLORS["text_secondary"])
        self.badge_ping.pack(pady=(0, 10))

        # کارت 2: Local Network
        self.card_local = CardFrame(cards_container, "🏠 Local Network")
        self.card_local.pack(side="left", fill="both", expand=True, padx=2, pady=2)

        self.lbl_local_ip = ctk.CTkLabel(
            self.card_local, text="IP: Not checked", font=small_font,
            text_color=COLORS["text_secondary"]
        )
        self.lbl_local_ip.pack(padx=10, pady=(4, 2), anchor="w")

        self.lbl_local_cidr = ctk.CTkLabel(
            self.card_local, text="CIDR: --", font=("Segoe UI", 15, "bold"),
            text_color=COLORS["text_secondary"]
        )
        self.lbl_local_cidr.pack(pady=4)

        self.badge_local = StatusBadge(self.card_local, "Not Checked", COLORS["text_secondary"])
        self.badge_local.pack(pady=(0, 10))

        # کارت 3: Public IP
        self.card_public = CardFrame(cards_container, "🌍 Public IP")
        self.card_public.pack(side="left", fill="both", expand=True, padx=(2, 0), pady=2)

        self.lbl_public_current = ctk.CTkLabel(
            self.card_public, text="Current: Not checked", font=small_font,
            text_color=COLORS["text_secondary"]
        )
        self.lbl_public_current.pack(padx=10, pady=(4, 2), anchor="w")

        self.lbl_public_expected = ctk.CTkLabel(
            self.card_public, text="Expected: --", font=("Segoe UI", 15, "bold"),
            text_color=COLORS["text_secondary"]
        )
        self.lbl_public_expected.pack(pady=4)

        self.badge_public = StatusBadge(self.card_public, "Not Checked", COLORS["text_secondary"])
        self.badge_public.pack(pady=(0, 10))

        # --- کنسول لاگ ---
        log_card = CardFrame(self.tab_monitor, "📜 Event Logs")
        log_card.pack(fill="both", expand=True, padx=3, pady=3)

        self.txt_logs = ctk.CTkTextbox(
            log_card, font=("Consolas", 12),
            fg_color=COLORS["bg_primary"],
            text_color=COLORS["text_primary"],
            corner_radius=8, border_width=1,
            border_color=COLORS["border"],
            wrap="word"
        )
        self.txt_logs.pack(fill="both", expand=True, padx=6, pady=6)

    # ============================================
    # متدهای کمکی UI
    # ============================================
    def log(self, message):
        """ثبت لاگ در باکس و فایل با محدودیت"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{now}] {message}\n"

        def _update():
            try:
                self.txt_logs.insert("end", formatted)
                self.txt_logs.see("end")

                # ✅ محدود کردن تعداد خطوط در Textbox (حداکثر ۵۰۰ خط)
                line_count = int(self.txt_logs.index('end-1c').split('.')[0])
                if line_count > 500:
                    # حذف ۱۰۰ خط قدیمی
                    self.txt_logs.delete("1.0", "100.0")
                    self.log("🗑️ Old logs cleared from UI (keeping last 500 lines)")
            except Exception:
                pass

        self.root.after(0, _update)

        # ✅ Log Rotation: بررسی حجم فایل
        try:
            if os.path.exists(LOG_FILE):
                file_size = os.path.getsize(LOG_FILE)
                # اگر فایل بیشتر از ۱ مگابایت شد، آن را بایگانی کن
                if file_size > 1_000_000:  # ۱ مگابایت
                    self._rotate_log_file()

            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(formatted)
        except Exception as e:
            print(f"خطا در نوشتن لاگ: {e}")

    def _rotate_log_file(self):
        """چرخش فایل لاگ وقتی از ۱ مگابایت بیشتر شود"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"app_logs_{timestamp}.txt"

            # تغییر نام فایل فعلی
            os.rename(LOG_FILE, backup_file)

            self.log(f"📦 Log file rotated: {backup_file}")

            # حذف فایل‌های بایگانی قدیمی (نگه داشتن ۵ فایل آخر)
            log_files = [f for f in os.listdir('.') if f.startswith("app_logs_") and f.endswith(".txt")]
            log_files.sort(reverse=True)

            for old_file in log_files[5:]:
                try:
                    os.remove(old_file)
                    print(f"Deleted old log: {old_file}")
                except Exception as e:
                    print(f"Error deleting old log {old_file}: {e}")

        except Exception as e:
            print(f"Error rotating log file: {e}")

    def toggle_token_visibility(self):
        if self.show_token:
            self.entry_bot_token.configure(show="*")
            self.btn_toggle_token.configure(text="👁️")
            self.show_token = False
        else:
            self.entry_bot_token.configure(show="")
            self.btn_toggle_token.configure(text="🙈")
            self.show_token = True

    def toggle_chat_id_visibility(self):
        if self.show_chat_id:
            self.entry_chat_id.configure(show="*")
            self.btn_toggle_chat_id.configure(text="👁️")
            self.show_chat_id = False
        else:
            self.entry_chat_id.configure(show="")
            self.btn_toggle_chat_id.configure(text="🙈")
            self.show_chat_id = True

    # ============================================
    # مدیریت کارت‌های شبکه
    # ============================================
    def get_network_adapters(self):
        adapters = []
        try:
            stats = psutil.net_if_stats()
            adapters = list(stats.keys())
        except Exception as e:
            self.log(f"Error fetching adapters: {e}")
        return adapters

    def refresh_adapters(self):
        adapters = self.get_network_adapters()
        self.combo_adapters.configure(values=adapters)
        if adapters:
            default_index = 0
            for idx, name in enumerate(adapters):
                if any(k in name.lower() for k in ["tap", "openvpn", "wintun", "tun"]):
                    default_index = idx
                    break
            self.combo_adapters.set(adapters[default_index])
        self.log("Network adapters list refreshed.")

    # ============================================
    # ذخیره و بارگذاری تنظیمات
    # ============================================
    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            fields = {
                "adapter": (self.combo_adapters, "set"),
                "interval": (self.entry_interval, "entry"),
                "proxy_ip": (self.entry_proxy_ip, "entry"),
                "proxy_port": (self.entry_proxy_port, "entry"),
                "bot_token": (self.entry_bot_token, "entry"),
                "chat_id": (self.entry_chat_id, "entry"),
                "ping_enabled": (self.ping_enabled, "bool"),
                "ping_ip": (self.entry_ping_ip, "entry"),
                "local_cidr_enabled": (self.local_cidr_enabled, "bool"),  # جدید
                "local_cidr": (self.entry_local_cidr, "entry"),
                "public_ip_enabled": (self.public_ip_enabled, "bool"),  # جدید
                "public_ip": (self.entry_public_ip, "entry"),
            }

            for key, (widget, wtype) in fields.items():
                if key in data:
                    if wtype == "entry":
                        widget.delete(0, "end")
                        widget.insert(0, str(data[key]))
                    elif wtype == "set":
                        if data[key] in widget.cget("values"):
                            widget.set(data[key])
                    elif wtype == "bool":
                        widget.set(data[key])

            self.log("Settings loaded from config.json.")
        except Exception as e:
            self.log(f"Error loading settings: {e}")

    def save_settings(self):
        data = {
            "adapter": self.combo_adapters.get(),
            "interval": self.entry_interval.get().strip(),
            "proxy_ip": self.entry_proxy_ip.get().strip(),
            "proxy_port": self.entry_proxy_port.get().strip(),
            "bot_token": self.entry_bot_token.get().strip(),
            "chat_id": self.entry_chat_id.get().strip(),
            "ping_enabled": self.ping_enabled.get(),
            "ping_ip": self.entry_ping_ip.get().strip(),
            "local_cidr_enabled": self.local_cidr_enabled.get(),  # جدید
            "local_cidr": self.entry_local_cidr.get().strip(),
            "public_ip_enabled": self.public_ip_enabled.get(),  # جدید
            "public_ip": self.entry_public_ip.get().strip(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.log("✅ Settings saved to config.json.")
        except Exception as e:
            self.log(f"Error saving settings: {e}")

    # ============================================
    # System Tray
    # ============================================
    def create_tray_image(self):
        image = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.rectangle([2, 2, 22, 22], fill="#181824", outline="#3b82f6", width=2)
        dc.ellipse([6, 6, 18, 18], fill="#3b82f6")
        return image

    def setup_tray(self):
        menu = (
            item('Show Window', self.show_window, default=True),
            item('Exit Application', self.exit_application)
        )
        self.tray_icon = pystray.Icon("TUNChecker", self.create_tray_image(),
                                      "TUN Checker", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.root.withdraw()
        self.log("TUN Checker minimized to system tray.")

    def show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
        self.log("Application window restored.")

    def exit_application(self, icon=None, item=None):
        self.is_running = False
        self.save_settings()
        self.log("Application shutting down.")
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    # ============================================
    # توابع شبکه و بررسی اتصال
    # ============================================
    def is_openvpn_connected(self):
        selected_adapter = self.combo_adapters.get()
        if not selected_adapter:
            return False
        try:
            stats = psutil.net_if_stats()
            if selected_adapter in stats:
                return stats[selected_adapter].isup
            return False
        except Exception:
            return False

    def get_adapter_ipv4(self, adapter_name):
        try:
            addrs = psutil.net_if_addrs().get(adapter_name, [])
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    return addr.address
            return None
        except Exception:
            return None

    def is_ip_in_cidr(self, ip_str, cidr_str):
        try:
            if not ip_str or not cidr_str:
                return False
            ip = ipaddress.IPv4Address(ip_str)
            network = ipaddress.IPv4Network(cidr_str, strict=False)
            return ip in network
        except Exception:
            return False

    def get_public_ip(self):
        try:
            response = requests.get("https://api.ipify.org", timeout=5)
            if response.status_code == 200:
                return response.text.strip()
            return None
        except Exception:
            return None

    def perform_ping(self, target_ip):
        """اجرای پینگ و برگرداندن (موفقیت, latency_ms)"""
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", target_ip],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=3
            )
            output = result.stdout.decode('utf-8', errors='ignore').lower()

            if result.returncode != 0:
                return False, None

            error_keywords = ["ttl expired", "unreachable", "failed",
                              "منقضی شد", "غیرقابل دسترسی"]
            if any(k in output for k in error_keywords):
                return False, None

            # استخراج latency از خروجی پینگ ویندوز
            match = re.search(r'time[=<](\d+)ms', output) or \
                    re.search(r'زمان[=<](\d+)', output)
            if match:
                return True, int(match.group(1))
            return True, None
        except Exception:
            return False, None

    # ============================================
    # گزارش وضعیت جامع
    # ============================================
    def get_full_status_report(self):
        selected_adapter = self.combo_adapters.get()

        # 1. OpenVPN
        vpn_connected = self.is_openvpn_connected()

        # 2. Ping - فقط وقتی VPN وصل است
        ping_ok = True
        ping_latency = None
        target_ip = self.entry_ping_ip.get().strip()
        if self.ping_enabled.get() and target_ip and vpn_connected:
            ping_ok, ping_latency = self.perform_ping(target_ip)

        # 3. Local IP - فقط وقتی VPN وصل است
        current_local_ip = self.get_adapter_ipv4(selected_adapter)
        expected_cidr = self.entry_local_cidr.get().strip()
        local_ok = True
        if self.local_cidr_enabled.get() and expected_cidr and vpn_connected:  # ✅ vpn_connected اضافه شد
            if current_local_ip and not current_local_ip.startswith("169.254"):
                local_ok = self.is_ip_in_cidr(current_local_ip, expected_cidr)
            else:
                local_ok = False

        # 4. Public IP - فقط وقتی VPN وصل است
        expected_public = self.entry_public_ip.get().strip()
        public_ok = True
        current_public = None
        if self.public_ip_enabled.get() and expected_public and vpn_connected:  # ✅ vpn_connected اضافه شد
            current_public = self.get_public_ip()
            public_ok = (current_public == expected_public)

        return {
            "vpn_connected": vpn_connected,
            "ping_ok": ping_ok,
            "ping_latency": ping_latency,
            "ping_target": target_ip,
            "local_ok": local_ok,
            "local_ip": current_local_ip,
            "local_cidr": expected_cidr,
            "public_ok": public_ok,
            "public_current": current_public,
            "public_expected": expected_public,
            "adapter": selected_adapter,
            "overall_ok": vpn_connected and ping_ok and local_ok and public_ok
        }

    # ============================================
    # تلگرام
    # ============================================
    def send_telegram_alert(self, message):
        token = self.entry_bot_token.get().strip()
        chat_id = self.entry_chat_id.get().strip()
        if not token or not chat_id:
            self.log("Telegram alert skipped: Token or Chat ID missing.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

        proxies = None
        proxy_ip = self.entry_proxy_ip.get().strip()
        proxy_port = self.entry_proxy_port.get().strip()
        if proxy_ip and proxy_port:
            proxy_url = f"http://{proxy_ip}:{proxy_port}"
            proxies = {"http": proxy_url, "https": proxy_url}

        try:
            response = requests.post(url, data=payload, proxies=proxies, timeout=10)
            if response.status_code == 200:
                self.log("Telegram alert sent successfully.")
                return True
            else:
                self.log(f"Failed to send alert. HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log(f"Error sending Telegram alert: {e}")
            return False

    def test_telegram(self):
        token = self.entry_bot_token.get().strip()
        chat_id = self.entry_chat_id.get().strip()
        if not token or not chat_id:
            self.lbl_status.configure(text="❌ Token and Chat ID required!",
                                      text_color=COLORS["accent_red"])
            return

        def run_test():
            self.root.after(0, lambda: self.lbl_status.configure(
                text="Testing Telegram...", text_color=COLORS["accent_blue"]))
            self.log("Testing Telegram connection...")
            success = self.send_telegram_alert("🔔 Test message from TUN Checker!")
            if success:
                self.root.after(0, lambda: self.lbl_status.configure(
                    text="✅ Test message sent!", text_color=COLORS["accent_green"]))
            else:
                self.root.after(0, lambda: self.lbl_status.configure(
                    text="❌ Failed to send test message", text_color=COLORS["accent_red"]))

        threading.Thread(target=run_test, daemon=True).start()

    def should_send_alert(self, is_recovery=False):
        """بررسی اینکه آیا می‌توان هشدار ارسال کرد (Rate Limiting)"""
        # ✅ هشدارهای Recovery همیشه ارسال می‌شوند
        if is_recovery:
            self.log("🟢 Recovery alert - bypassing rate limit")
            return True

        current_time = time.time()
        time_since_last = current_time - self.last_alert_time

        if time_since_last < self.alert_cooldown:
            remaining = int(self.alert_cooldown - time_since_last)
            self.log(f"⏳ Critical alert rate limited. Next alert available in {remaining}s")
            return False

        return True

    def send_comprehensive_alert(self, trigger_reason, is_recovery=False):
        # ✅ بررسی Rate Limiting قبل از ارسال
        if not self.should_send_alert(is_recovery):
            return

        status = self.get_full_status_report()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        overall = "🟢 <b>HEALTHY</b>" if status["overall_ok"] else "🔴 <b>CRITICAL</b>"

        ping_line = f"🔹 Ping: {'✅ ' + str(status['ping_latency']) + 'ms' if status['ping_ok'] else '❌ Unreachable'}"
        local_line = f"🔹 Local IP: {'✅ ' + str(status['local_ip']) if status['local_ok'] else '❌ ' + str(status['local_ip'] or 'No IP')}"
        public_line = f"🔹 Public IP: {'✅ ' + str(status['public_current']) if status['public_ok'] else '❌ ' + str(status['public_current'] or 'Unknown')}"

        message = (
            f"🚨 <b>TUN Checker Alert</b>\n\n"
            f"{overall}\n\n"
            f"📊 <b>Detailed Checks:</b>\n"
            f"🔹 Adapter: {'✅ Connected' if status['vpn_connected'] else '❌ Disconnected'}\n"
            f"{ping_line}\n"
            f"{local_line}\n"
            f"{public_line}\n\n"
            f"⚠️ <b>Trigger:</b> {trigger_reason}\n"
            f"🕒 <b>Time:</b> <code>{now}</code>"
        )

        self.log(f"Sending comprehensive alert. Trigger: {trigger_reason}")
        success = self.send_telegram_alert(message)

        if success:
            self.last_alert_time = time.time()  # ✅ به‌روزرسانی زمان آخرین هشدار

    # ============================================
    # حلقه مانیتورینگ
    # ============================================
    def monitor_loop(self):
        was_connected = True
        initial_status = self.get_full_status_report()
        self.last_overall_status = initial_status["overall_ok"]

        if not self.last_overall_status:
            self.send_comprehensive_alert("Initial Check Failed (Already Critical)")

        while self.is_running:
            try:
                try:
                    interval = int(self.entry_interval.get().strip())
                    if interval < 1:
                        interval = 5
                except ValueError:
                    interval = 10

                status = self.get_full_status_report()
                self.root.after(0, lambda s=status: self.update_live_ui(s))

                connected = status["vpn_connected"]
                selected_adapter = status["adapter"]

                if connected:
                    self.root.after(0, lambda a=selected_adapter: self.lbl_status.configure(
                        text=f"🟢 {a} Connected", text_color=COLORS["accent_green"]))
                    if not was_connected:
                        self.log(f"Adapter {selected_adapter} is now Connected.")
                    was_connected = True
                else:
                    self.root.after(0, lambda a=selected_adapter: self.lbl_status.configure(
                        text=f"🔴 {a} Disconnected!", text_color=COLORS["accent_red"]))
                    if was_connected:
                        self.log(f"WARNING: Adapter ({selected_adapter}) disconnected!")
                    was_connected = False

                current_overall = status["overall_ok"]

                if not current_overall and self.last_overall_status:
                    # ❌ Critical alert - rate limited می‌شود
                    reasons = []
                    if not status["vpn_connected"]:
                        reasons.append("Adapter Down")
                    if not status["ping_ok"]:
                        reasons.append("Ping Failed")
                    if not status["local_ok"]:
                        reasons.append("Local IP Mismatch")
                    if not status["public_ok"]:
                        reasons.append("Public IP Mismatch")
                    trigger = " | ".join(reasons) if reasons else "Unknown"
                    self.send_comprehensive_alert(trigger, is_recovery=False)  # ✅ پارامتر اضافه شد

                elif current_overall and not self.last_overall_status:
                    # ✅ Recovery alert - همیشه ارسال می‌شود
                    self.send_comprehensive_alert("✅ System Recovered", is_recovery=True)  # ✅ پارامتر اضافه شد

                self.last_overall_status = current_overall

                for _ in range(interval):
                    if not self.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                self.log(f"CRITICAL ERROR in monitor loop: {e}")
                time.sleep(5)

    def update_live_ui(self, status):
        """بروزرسانی کارت‌های وضعیت زنده"""
        # بج کلی
        if status["overall_ok"]:
            self.badge_overall.update_status("Active", COLORS["accent_green"])
        else:
            self.badge_overall.update_status("Critical", COLORS["accent_red"])

        # کارت Ping
        target = status["ping_target"] or "Not set"
        self.lbl_ping_target.configure(text=f"Target: {target}")
        if self.ping_enabled.get() and target:
            if status["ping_ok"]:
                latency = f"{status['ping_latency']} ms" if status['ping_latency'] else "< 1 ms"
                self.lbl_ping_latency.configure(text=latency, text_color=COLORS["accent_green"])
                self.badge_ping.update_status("Reachable", COLORS["accent_green"])
            else:
                self.lbl_ping_latency.configure(text="-- ms", text_color=COLORS["accent_red"])
                self.badge_ping.update_status("Unreachable", COLORS["accent_red"])
        else:
            self.lbl_ping_latency.configure(text="-- ms", text_color=COLORS["text_secondary"])
            self.badge_ping.update_status("Disabled", COLORS["text_secondary"])

        # کارت Local
        local_ip = status["local_ip"] or "No IP"
        self.lbl_local_ip.configure(text=f"IP: {local_ip}")
        self.lbl_local_cidr.configure(text=f"CIDR: {status['local_cidr'] or '--'}")

        # تغییر: بررسی تیک فعال‌سازی Local CIDR
        if self.local_cidr_enabled.get() and status["local_cidr"]:
            if status["local_ok"]:
                self.badge_local.update_status("Match ✓", COLORS["accent_green"])
            else:
                self.badge_local.update_status("Mismatch ✗", COLORS["accent_red"])
        else:
            self.badge_local.update_status("Disabled", COLORS["text_secondary"])

        # کارت Public
        self.lbl_public_current.configure(text=f"Current: {status['public_current'] or 'Unknown'}")
        self.lbl_public_expected.configure(text=f"Expected: {status['public_expected'] or '--'}")

        # تغییر: بررسی تیک فعال‌سازی Public IP
        if self.public_ip_enabled.get() and status["public_expected"]:
            if status["public_ok"]:
                self.badge_public.update_status("Match ✓", COLORS["accent_green"])
            else:
                self.badge_public.update_status("Mismatch ✗", COLORS["accent_red"])
        else:
            self.badge_public.update_status("Disabled", COLORS["text_secondary"])

    # ============================================
    # کنترل مانیتورینگ
    # ============================================
    def toggle_monitoring(self):
        if not self.is_running:
            if not self.combo_adapters.get():
                self.lbl_status.configure(text="❌ No adapter selected",
                                          text_color=COLORS["accent_red"])
                return

            self.save_settings()
            self.is_running = True
            self.btn_toggle.configure(
                text="■ Stop Monitoring",
                fg_color=COLORS["accent_red"], hover_color="#dc2626"
            )
            self.toggle_inputs(state="disabled")
            self.tabview.set("📊 Monitor")

            selected = self.combo_adapters.get()
            self.log(f"Monitoring started for: {selected}")
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
        else:
            self.is_running = False
            self.btn_toggle.configure(
                text="▶ Start Monitoring",
                fg_color=COLORS["accent_green"], hover_color="#059669"
            )
            self.lbl_status.configure(text="Status: Inactive",
                                      text_color=COLORS["text_secondary"])
            self.badge_overall.update_status("Inactive", COLORS["text_secondary"])
            self.toggle_inputs(state="normal")
            self.log("Monitoring stopped.")

    def toggle_inputs(self, state):
        disabled = (state == "disabled")
        self.combo_adapters.configure(state="disabled" if disabled else "normal")
        self.entry_interval.configure(state="disabled" if disabled else "normal")
        self.entry_proxy_ip.configure(state="disabled" if disabled else "normal")
        self.entry_proxy_port.configure(state="disabled" if disabled else "normal")
        self.entry_bot_token.configure(state="disabled" if disabled else "normal")
        self.entry_chat_id.configure(state="disabled" if disabled else "normal")
        self.entry_ping_ip.configure(state="disabled" if disabled else "normal")

        # تغییر: اضافه شدن چک‌باکس‌ها و فیلدهای جدید به لیست قفل شدن
        self.chk_local_cidr.configure(state="disabled" if disabled else "normal")
        self.entry_local_cidr.configure(state="disabled" if disabled else "normal")
        self.chk_public_ip.configure(state="disabled" if disabled else "normal")
        self.entry_public_ip.configure(state="disabled" if disabled else "normal")
        self.chk_ping.configure(state="disabled" if disabled else "normal")
        self.btn_toggle_token.configure(state="disabled" if disabled else "normal")
        self.btn_toggle_chat_id.configure(state="disabled" if disabled else "normal")
        self.btn_test_telegram.configure(state="disabled" if disabled else "normal")
        self.btn_save_settings.configure(state="disabled" if disabled else "normal")
        try:
            self.tabview._segmented_button.configure(
                state="disabled" if disabled else "normal"
            )
        except AttributeError:
            pass


# ============================================
# نقطه شروع
# ============================================
if __name__ == "__main__":
    root = ctk.CTk()
    app = VPNMonitorApp(root)
    root.mainloop()