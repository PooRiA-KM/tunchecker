import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import requests
import json
import os
from datetime import datetime
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import psutil

CONFIG_FILE = "config.json"
LOG_FILE = "app_logs.txt"


class VPNMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VPN Monitor & Telegram Notifier")
        self.root.geometry("460x760")
        self.root.resizable(False, False)

        # متغیرهای وضعیت
        self.is_running = False
        self.monitor_thread = None
        self.tray_icon = None

        # متغیرهای نمایش/مخفی‌سازی پسورد
        self.show_token = False
        self.show_chat_id = False

        self.setup_ui()
        self.refresh_adapters()
        self.load_settings()

        self.log("Application initialized successfully.")

        # تغییر رفتار دکمه ضربدر پنجره به پنهان شدن در Tray
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # راه‌اندازی آیکون تری در یک ترد مجزا
        self.setup_tray()

    def setup_ui(self):
        # تنظیم فونت Comic Sans MS برای تمام کامپوننت‌های ttk
        style = ttk.Style()
        style.configure("TLabel", font=("Comic Sans MS", 10))
        style.configure("TButton", font=("Comic Sans MS", 10))
        style.configure("TLabelframe.Label", font=("Comic Sans MS", 10, "bold"))

        # تنظیم فونت برای منوی کشویی و فیلدهای متنی استاندارد تکینتر
        self.root.option_add("*TCombobox*Listbox.font", ("Comic Sans MS", 10))
        font_entry = ("Comic Sans MS", 10)

        # فریم انتخاب کارت شبکه
        frame_adapter = ttk.LabelFrame(self.root, text=" Network Adapter Selection ", padding=10)
        frame_adapter.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_adapter, text="Adapter:").grid(row=0, column=0, sticky="w", pady=5)

        # منوی کشویی برای لیست آداپتورها
        self.combo_adapters = ttk.Combobox(frame_adapter, state="readonly", width=28, font=font_entry)
        self.combo_adapters.grid(row=0, column=1, padx=5, pady=5)

        # دکمه بروزرسانی لیست آداپتورها
        btn_refresh = ttk.Button(frame_adapter, text="🔄", width=3, command=self.refresh_adapters)
        btn_refresh.grid(row=0, column=2, padx=2)

        # فریم تنظیمات زمان‌بندی
        frame_interval = ttk.LabelFrame(self.root, text=" Interval Settings ", padding=10)
        frame_interval.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_interval, text="Check Interval (sec):").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_interval = ttk.Entry(frame_interval, width=10, font=font_entry)
        self.entry_interval.insert(0, "10")
        self.entry_interval.grid(row=0, column=1, sticky="e", padx=5)

        # فریم بررسی اتصال واقعی (پینگ)
        frame_ping = ttk.LabelFrame(self.root, text=" Connectivity Check (Optional Ping) ", padding=10)
        frame_ping.pack(fill="x", padx=10, pady=5)

        self.ping_enabled = tk.BooleanVar(value=False)
        self.chk_ping = ttk.Checkbutton(frame_ping, text="Enable Ping Check", variable=self.ping_enabled)
        self.chk_ping.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(frame_ping, text="Target IP:").grid(row=1, column=0, sticky="w", pady=2)
        self.entry_ping_ip = ttk.Entry(frame_ping, width=20, font=font_entry)
        self.entry_ping_ip.grid(row=1, column=1, padx=5, pady=2)

        # فریم پروکسی
        frame_proxy = ttk.LabelFrame(self.root, text=" Telegram Proxy Settings (Optional) ", padding=10)
        frame_proxy.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_proxy, text="IP Address:").grid(row=0, column=0, sticky="w", pady=2)
        self.entry_proxy_ip = ttk.Entry(frame_proxy, width=20, font=font_entry)
        self.entry_proxy_ip.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(frame_proxy, text="Port:").grid(row=1, column=0, sticky="w", pady=2)
        self.entry_proxy_port = ttk.Entry(frame_proxy, width=20, font=font_entry)
        self.entry_proxy_port.grid(row=1, column=1, padx=5, pady=2)

        # فریم تلگرام
        frame_telegram = ttk.LabelFrame(self.root, text=" Telegram Bot Settings ", padding=10)
        frame_telegram.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_telegram, text="Bot Token:").grid(row=0, column=0, sticky="w", pady=2)
        # افزودن show="*" برای مخفی‌سازی توکن
        self.entry_bot_token = ttk.Entry(frame_telegram, width=23, show="*", font=font_entry)
        self.entry_bot_token.grid(row=0, column=1, padx=2, pady=2)

        self.btn_toggle_token = ttk.Button(frame_telegram, text="👁️", width=3, command=self.toggle_token_visibility)
        self.btn_toggle_token.grid(row=0, column=2, padx=2)

        ttk.Label(frame_telegram, text="Chat ID:").grid(row=1, column=0, sticky="w", pady=2)
        # افزودن show="*" برای مخفی‌سازی چت آیدی
        self.entry_chat_id = ttk.Entry(frame_telegram, width=23, show="*", font=font_entry)
        self.entry_chat_id.grid(row=1, column=1, padx=2, pady=2)

        self.btn_toggle_chat_id = ttk.Button(frame_telegram, text="👁️", width=3, command=self.toggle_chat_id_visibility)
        self.btn_toggle_chat_id.grid(row=1, column=2, padx=2)

        # دکمه تست تلگرام
        self.btn_test_telegram = ttk.Button(frame_telegram, text="Test Bot Connection", command=self.test_telegram)
        self.btn_test_telegram.grid(row=2, column=0, columnspan=3, sticky="we", pady=(8, 2))

        # وضعیت و دکمه‌ها
        frame_actions = ttk.Frame(self.root, padding=10)
        frame_actions.pack(fill="x", padx=10, pady=2)

        self.lbl_status = ttk.Label(frame_actions, text="Status: Inactive", font=("Comic Sans MS", 11, "bold"),
                                    foreground="gray")
        self.lbl_status.pack(pady=2)

        self.btn_toggle = ttk.Button(frame_actions, text="Start Monitoring", command=self.toggle_monitoring)
        self.btn_toggle.pack(fill="x", pady=2)

        # فریم نمایش لاگ‌ها
        frame_logs = ttk.LabelFrame(self.root, text=" Event Logs ", padding=10)
        frame_logs.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_logs = tk.Text(frame_logs, height=8, font=("Comic Sans MS", 8), state="disabled", wrap="word")
        scrollbar_y = ttk.Scrollbar(frame_logs, orient="vertical", command=self.txt_logs.yview)
        self.txt_logs.configure(yscrollcommand=scrollbar_y.set)

        scrollbar_y.pack(side="right", fill="y")
        self.txt_logs.pack(side="left", fill="both", expand=True)

    def log(self, message):
        """ثبت همزمان لاگ با تاریخ و ساعت در باکس برنامه و فایل متنی"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{now}] {message}\n"

        # تعریف یک تابع داخلی برای آپدیت کردن باکس متن
        def _update_ui():
            try:
                self.txt_logs.config(state="normal")
                self.txt_logs.insert(tk.END, formatted_message)
                self.txt_logs.see(tk.END)
                self.txt_logs.config(state="disabled")
            except Exception:
                pass

        # انتقال آپدیت UI به ترد اصلی (MainThread)
        self.root.after(0, _update_ui)

        # ذخیره همزمان در فایل تکست کنار برنامه (این بخش نیازی به ترد اصلی نداره)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(formatted_message)
        except Exception as e:
            print(f"خطا در نوشتن لاگ روی فایل: {e}")

    def create_tray_image(self):
        """ساخت یک آیکون ساده داینامیک برای تری سیستم"""
        image = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.rectangle([2, 2, 22, 22], fill="#1f232a", outline="#4f5b66", width=2)
        dc.ellipse([6, 6, 18, 18], fill="#007acc")
        return image

    def setup_tray(self):
        """راه‌اندازی سیستم تری"""
        menu = (
            item('Show Window', self.show_window, default=True),
            item('Exit Application', self.exit_application)
        )
        self.tray_icon = pystray.Icon("VPNMonitor", self.create_tray_image(), "VPN Monitor", menu)

        # اجرای آیکون تری در ترد بک‌گراند تا اصلی فریز نشود
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        """پنهان کردن پنجره اصلی و انتقال به تری"""
        self.root.withdraw()
        self.log("Application minimized to system tray.")

    def show_window(self):
        """نمایش مجدد پنجره اصلی"""
        self.root.deiconify()
        self.root.lift()
        self.log("Application window restored.")

    def exit_application(self):
        """خروج کامل و نهایی از برنامه از طریق مکرر منوی تری"""
        self.is_running = False
        self.save_settings()
        self.log("Application shutting down completely via Tray.")

        # بستن آیکون تری
        if self.tray_icon:
            self.tray_icon.stop()

        # بستن نهایی پنجره تکینتر
        self.root.after(0, self.root.destroy)

    def load_settings(self):
        """بارگذاری تنظیمات از فایل JSON"""
        if not os.path.exists(CONFIG_FILE):
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "adapter" in data and data["adapter"] in self.combo_adapters['values']:
                self.combo_adapters.set(data["adapter"])

            if "interval" in data:
                self.entry_interval.delete(0, tk.END)
                self.entry_interval.insert(0, str(data["interval"]))

            if "proxy_ip" in data:
                self.entry_proxy_ip.delete(0, tk.END)
                self.entry_proxy_ip.insert(0, data["proxy_ip"])

            if "proxy_port" in data:
                self.entry_proxy_port.delete(0, tk.END)
                self.entry_proxy_port.insert(0, data["proxy_port"])

            if "bot_token" in data:
                self.entry_bot_token.delete(0, tk.END)
                self.entry_bot_token.insert(0, data["bot_token"])

            if "chat_id" in data:
                self.entry_chat_id.delete(0, tk.END)
                self.entry_chat_id.insert(0, data["chat_id"])

            if "ping_enabled" in data:
                self.ping_enabled.set(data["ping_enabled"])
            if "ping_ip" in data:
                self.entry_ping_ip.delete(0, tk.END)
                self.entry_ping_ip.insert(0, data["ping_ip"])

            self.log("Settings loaded from config.json.")
        except Exception as e:
            print(f"خطا در بارگذاری تنظیمات: {e}")
            self.log(f"Error loading settings: {e}")

    def save_settings(self):
        """ذخیره تنظیمات در فایل JSON"""
        data = {
            "adapter": self.combo_adapters.get(),
            "interval": self.entry_interval.get().strip(),
            "proxy_ip": self.entry_proxy_ip.get().strip(),
            "proxy_port": self.entry_proxy_port.get().strip(),
            "bot_token": self.entry_bot_token.get().strip(),
            "chat_id": self.entry_chat_id.get().strip(),
            "ping_enabled": self.ping_enabled.get(),
            "ping_ip": self.entry_ping_ip.get().strip()
        }

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.log("Settings saved to config.json.")
        except Exception as e:
            print(f"خطا در ذخیره تنظیمات: {e}")
            self.log(f"Error saving settings: {e}")

    def toggle_token_visibility(self):
        """نمایش یا مخفی کردن توکن ربات"""
        if self.show_token:
            self.entry_bot_token.config(show="*")
            self.show_token = False
        else:
            self.entry_bot_token.config(show="")
            self.show_token = True

    def toggle_chat_id_visibility(self):
        """نمایش یا مخفی کردن چت آیدی"""
        if self.show_chat_id:
            self.entry_chat_id.config(show="*")
            self.show_chat_id = False
        else:
            self.entry_chat_id.config(show="")
            self.show_chat_id = True

    def get_network_adapters(self):
        """
        دریافت نام تمام کارت‌های شبکه سیستم‌عامل با استفاده از psutil (بهینه‌تر و سریع‌تر)
        """
        adapters = []
        try:
            # دریافت مستقیم وضعیت تمام اینترفیس‌ها بدون نیاز به اجرای دستور خارجی
            stats = psutil.net_if_stats()
            adapters = list(stats.keys())
        except Exception as e:
            print(f"خطا در دریافت کارت‌های شبکه: {e}")
            self.log(f"Error fetching network adapters: {e}")
        return adapters

    def refresh_adapters(self):
        """
        بروزرسانی لیست منوی کشویی کارت‌های شبکه
        """
        adapters = self.get_network_adapters()
        self.combo_adapters['values'] = adapters
        if adapters:
            default_index = 0
            for idx, name in enumerate(adapters):
                if any(k in name.lower() for k in ["tap", "openvpn", "wintun", "tun"]):
                    default_index = idx
                    break
            self.combo_adapters.current(default_index)
        self.log("Network adapters list refreshed.")

    def is_openvpn_connected(self):
        """
        بررسی وضعیت کارت شبکه و در صورت فعال بودن، بررسی اتصال واقعی با پینگ
        """
        selected_adapter = self.combo_adapters.get()
        if not selected_adapter:
            return False

        # 1. بررسی وضعیت آداپتور با psutil (سریع و بدون سربار)
        try:
            stats = psutil.net_if_stats()
            if selected_adapter not in stats or not stats[selected_adapter].isup:
                return False
        except Exception:
            return False

        # 2. بررسی پینگ (فقط در صورتی که کاربر تیک آن را فعال کرده باشد)
        if self.ping_enabled.get():
            target_ip = self.entry_ping_ip.get().strip()
            if not target_ip:
                return False  # اگر تیک خورده ولی آیپی خالیه، اتصال رو رد می‌کنیم

            try:
                # اجرای دستور پینگ و دریافت خروجی استاندارد (stdout) به جای DEVNULL
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "1000", target_ip],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                # اگر کد خروج غیر از 0 باشد (مثل Request timed out)، یعنی قطعی است
                if result.returncode != 0:
                    return False

                # اگر کد خروج 0 باشد، باید خروجی متن را چک کنیم.
                # چون ویندوز گاهی برای خطاهایی مثل TTL expired هم کد 0 (موفقیت) برمی‌گرداند!
                output_text = result.stdout.decode('utf-8', errors='ignore').lower()

                # بررسی کلمات کلیدی خطا (هم انگلیسی و هم فارسی برای اطمینان کامل در هر زبانی)
                error_keywords = [
                    "ttl expired", "unreachable", "failed",
                ]
                if any(keyword in output_text for keyword in error_keywords):
                    return False

            except Exception:
                return False

        return True

    def send_telegram_alert(self, message):
        token = self.entry_bot_token.get().strip()
        chat_id = self.entry_chat_id.get().strip()

        if not token or not chat_id:
            self.log("Telegram alert skipped: Token or Chat ID is missing.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}

        proxies = None
        proxy_ip = self.entry_proxy_ip.get().strip()
        proxy_port = self.entry_proxy_port.get().strip()

        if proxy_ip and proxy_port:
            proxy_url = f"http://{proxy_ip}:{proxy_port}"
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }

        try:
            response = requests.post(url, data=payload, proxies=proxies, timeout=10)
            if response.status_code == 200:
                self.log("Telegram alert sent successfully.")
                return True
            else:
                self.log(f"Failed to send Telegram alert. HTTP Status: {response.status_code}")
                return False
        except Exception as e:
            print(f"خطا در ارسال پیام تلگرام: {e}")
            self.log(f"Error sending Telegram alert: {e}")
            return False

    def test_telegram(self):
        """تست ارسال پیام به تلگرام در ترد مجزا"""
        token = self.entry_bot_token.get().strip()
        chat_id = self.entry_chat_id.get().strip()
        if not token or not chat_id:
            self.lbl_status.config(text="Error: Token and Chat ID required!", foreground="red")
            self.log("Test failed: Token or Chat ID missing.")
            return

        def run_test():
            # آپدیت‌های امن UI
            self.root.after(0, lambda: self.lbl_status.config(text="Status: Testing Telegram...", foreground="blue"))
            self.log("Testing Telegram connection...")

            success = self.send_telegram_alert("🔔 Test message from VPN Monitor!")

            if success:
                self.root.after(0, lambda: self.lbl_status.config(text="Status: Test message sent!", foreground="green"))
            else:
                self.root.after(0, lambda: self.lbl_status.config(text="Error: Failed to send test message", foreground="red"))

        threading.Thread(target=run_test, daemon=True).start()

    def monitor_loop(self):
        was_connected = True
        while self.is_running:
            try:
                interval = int(self.entry_interval.get().strip())
                if interval < 1:
                    interval = 5
            except ValueError:
                interval = 10

            connected = self.is_openvpn_connected()
            selected_adapter = self.combo_adapters.get()

            if connected:
                # آپدیت امن UI
                self.root.after(0, lambda adapter=selected_adapter: self.lbl_status.config(
                    text=f"Status: {adapter} Connected", foreground="green"))
                if not was_connected:
                    self.log(f"Adapter state changed: {selected_adapter} is now Connected.")
                was_connected = True
            else:
                # آپدیت امن UI
                self.root.after(0, lambda adapter=selected_adapter: self.lbl_status.config(
                    text=f"Status: {adapter} Disconnected!", foreground="red"))
                if was_connected:
                    self.log(f"WARNING: Network adapter ({selected_adapter}) disconnected!")
                    self.send_telegram_alert(f"⚠️ Warning: Network adapter ({selected_adapter}) disconnected!")
                    was_connected = False

            for _ in range(interval):
                if not self.is_running:
                    break
                time.sleep(1)

    def toggle_monitoring(self):
        if not self.is_running:
            if not self.combo_adapters.get():
                self.lbl_status.config(text="Error: No network adapter selected", foreground="red")
                self.log("Cannot start monitoring: No network adapter selected.")
                return

            self.save_settings()
            self.is_running = True
            self.btn_toggle.config(text="Stop Monitoring")
            self.toggle_inputs(state="disabled")

            selected_adapter = self.combo_adapters.get()
            self.log(f"Monitoring started for adapter: {selected_adapter}")

            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
        else:
            self.is_running = False
            self.btn_toggle.config(text="Start Monitoring")
            self.lbl_status.config(text="Status: Inactive", foreground="gray")
            self.toggle_inputs(state="normal")
            self.log("Monitoring stopped.")

    def toggle_inputs(self, state):
        self.combo_adapters.config(state="disabled" if state == "disabled" else "readonly")
        self.entry_interval.config(state=state)
        self.entry_proxy_ip.config(state=state)
        self.entry_proxy_port.config(state=state)
        self.entry_bot_token.config(state=state)
        self.entry_chat_id.config(state=state)
        self.btn_toggle_token.config(state=state)
        self.btn_toggle_chat_id.config(state=state)
        self.btn_test_telegram.config(state=state)
        # مدیریت وضعیت چک‌باکس و فیلد پینگ
        if state == "disabled":
            self.chk_ping.config(state="disabled")
            self.entry_ping_ip.config(state="disabled")
        else:
            self.chk_ping.config(state="normal")
            self.entry_ping_ip.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = VPNMonitorApp(root)
    root.mainloop()