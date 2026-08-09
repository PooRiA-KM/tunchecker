import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import requests


class VPNMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VPN Monitor & Telegram Notifier")
        self.root.geometry("460x540")
        self.root.resizable(False, False)

        # متغیرهای وضعیت
        self.is_running = False
        self.monitor_thread = None

        # متغیرهای نمایش/مخفی‌سازی پسورد
        self.show_token = False
        self.show_chat_id = False

        self.setup_ui()
        self.refresh_adapters()

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Tahoma", 9))
        style.configure("TButton", font=("Tahoma", 9))

        # فریم انتخاب کارت شبکه
        frame_adapter = ttk.LabelFrame(self.root, text=" انتخاب کارت شبکه ", padding=10)
        frame_adapter.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_adapter, text="کارت شبکه:").grid(row=0, column=0, sticky="w", pady=5)

        # منوی کشویی برای لیست آداپتورها
        self.combo_adapters = ttk.Combobox(frame_adapter, state="readonly", width=28)
        self.combo_adapters.grid(row=0, column=1, padx=5, pady=5)

        # دکمه بروزرسانی لیست آداپتورها
        btn_refresh = ttk.Button(frame_adapter, text="🔄", width=3, command=self.refresh_adapters)
        btn_refresh.grid(row=0, column=2, padx=2)

        # فریم تنظیمات زمان‌بندی
        frame_interval = ttk.LabelFrame(self.root, text=" تنظیمات زمان‌بندی ", padding=10)
        frame_interval.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_interval, text="فاصله بررسی (ثانیه):").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_interval = ttk.Entry(frame_interval, width=10)
        self.entry_interval.insert(0, "10")
        self.entry_interval.grid(row=0, column=1, sticky="e", padx=5)

        # فریم پروکسی
        frame_proxy = ttk.LabelFrame(self.root, text=" تنظیمات پروکسی تلگرام (اختیاری) ", padding=10)
        frame_proxy.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_proxy, text="آدرس آی‌پی (IP):").grid(row=0, column=0, sticky="w", pady=2)
        self.entry_proxy_ip = ttk.Entry(frame_proxy, width=20)
        self.entry_proxy_ip.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(frame_proxy, text="پورت (Port):").grid(row=1, column=0, sticky="w", pady=2)
        self.entry_proxy_port = ttk.Entry(frame_proxy, width=20)
        self.entry_proxy_port.grid(row=1, column=1, padx=5, pady=2)

        # فریم تلگرام
        frame_telegram = ttk.LabelFrame(self.root, text=" تنظیمات ربات تلگرام ", padding=10)
        frame_telegram.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_telegram, text="توکن ربات (Bot Token):").grid(row=0, column=0, sticky="w", pady=2)
        # افزودن show="*" برای مخفی‌سازی توکن
        self.entry_bot_token = ttk.Entry(frame_telegram, width=23, show="*")
        self.entry_bot_token.grid(row=0, column=1, padx=2, pady=2)

        #self.btn_toggle_token = ttk.Button(frame_telegram, text="👁️", width=3, command=self.toggle_token_visibility)
        #self.btn_toggle_token.grid(row=0, column=2, padx=2)

        ttk.Label(frame_telegram, text="چت آیدی (Chat ID):").grid(row=1, column=0, sticky="w", pady=2)
        # افزودن show="*" برای مخفی‌سازی چت آیدی
        self.entry_chat_id = ttk.Entry(frame_telegram, width=23, show="*")
        self.entry_chat_id.grid(row=1, column=1, padx=2, pady=2)

        #self.btn_toggle_chat_id = ttk.Button(frame_telegram, text="👁️", width=3, command=self.toggle_chat_id_visibility)
        #self.btn_toggle_chat_id.grid(row=1, column=2, padx=2)

        # وضعیت و دکمه‌ها
        frame_actions = ttk.Frame(self.root, padding=10)
        frame_actions.pack(fill="x", padx=10, pady=5)

        self.lbl_status = ttk.Label(frame_actions, text="وضعیت: غیرفعال", font=("Tahoma", 10, "bold"),
                                    foreground="gray")
        self.lbl_status.pack(pady=5)

        self.btn_toggle = ttk.Button(frame_actions, text="شروع مانیتورینگ", command=self.toggle_monitoring)
        self.btn_toggle.pack(fill="x", pady=5)

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
        دریافت نام تمام کارت‌های شبکه سیستم‌عامل
        """
        adapters = []
        try:
            output = subprocess.check_output(
                ["netsh", "interface", "show", "interface"],
                creationflags=subprocess.CREATE_NO_WINDOW
            ).decode('utf-8', errors='ignore')

            lines = output.splitlines()
            for line in lines:
                parts = line.split()
                # خروجی netsh شامل Admin State, State, Type, Interface Name است
                # نام کارت شبکه معمولا بخش آخر سطر است
                if len(parts) >= 4 and parts[0] in ["Enabled", "Disabled"]:
                    adapter_name = " ".join(parts[3:])
                    adapters.append(adapter_name)
        except Exception as e:
            print(f"خطا در دریافت کارت‌های شبکه: {e}")
        return adapters

    def refresh_adapters(self):
        """
        بروزرسانی لیست منوی کشویی کارت‌های شبکه
        """
        adapters = self.get_network_adapters()
        self.combo_adapters['values'] = adapters
        if adapters:
            # سعی می‌کند پیش‌فرض کارت شبکه‌ای که کلمه TAP یا OpenVPN دارد را انتخاب کند
            default_index = 0
            for idx, name in enumerate(adapters):
                if any(k in name.lower() for k in ["tap", "openvpn", "wintun", "tun"]):
                    default_index = idx
                    break
            self.combo_adapters.current(default_index)

    def is_openvpn_connected(self):
        """
        بررسی وضعیت کارت شبکه انتخاب‌شده در منوی کشویی
        """
        selected_adapter = self.combo_adapters.get()
        if not selected_adapter:
            return False

        try:
            output = subprocess.check_output(
                ["netsh", "interface", "show", "interface"],
                creationflags=subprocess.CREATE_NO_WINDOW
            ).decode('utf-8', errors='ignore')

            for line in output.splitlines():
                if selected_adapter in line:
                    line_lower = line.lower()
                    # بررسی اتصال بر اساس کلیدواژه Connected
                    if "connected" in line_lower and "disconnected" not in line_lower:
                        return True
            return False
        except Exception:
            return False

    def send_telegram_alert(self, message):
        token = self.entry_bot_token.get().strip()
        chat_id = self.entry_chat_id.get().strip()

        if not token or not chat_id:
            return

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
            requests.post(url, data=payload, proxies=proxies, timeout=10)
        except Exception as e:
            print(f"خطا در ارسال پیام تلگرام: {e}")

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
                self.lbl_status.config(text=f"وضعیت: {selected_adapter} متصل است", foreground="green")
                was_connected = True
            else:
                self.lbl_status.config(text=f"وضعیت: {selected_adapter} قطع شد!", foreground="red")
                if was_connected:
                    self.send_telegram_alert(f"⚠️ هشدار: اتصال کارت شبکه ({selected_adapter}) قطع شد!")
                    was_connected = False

            for _ in range(interval):
                if not self.is_running:
                    break
                time.sleep(1)

    def toggle_monitoring(self):
        if not self.is_running:
            if not self.combo_adapters.get():
                self.lbl_status.config(text="خطا: هیچ کارت شبکه‌ای انتخاب نشده است", foreground="red")
                return

            self.is_running = True
            self.btn_toggle.config(text="توقف مانیتورینگ")
            self.toggle_inputs(state="disabled")

            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
        else:
            self.is_running = False
            self.btn_toggle.config(text="شروع مانیتورینگ")
            self.lbl_status.config(text="وضعیت: غیرفعال", foreground="gray")
            self.toggle_inputs(state="normal")

    def toggle_inputs(self, state):
        self.combo_adapters.config(state="disabled" if state == "disabled" else "readonly")
        self.entry_interval.config(state=state)
        self.entry_proxy_ip.config(state=state)
        self.entry_proxy_port.config(state=state)
        self.entry_bot_token.config(state=state)
        self.entry_chat_id.config(state=state)
        self.btn_toggle_token.config(state=state)
        self.btn_toggle_chat_id.config(state=state)


if __name__ == "__main__":
    root = tk.Tk()
    app = VPNMonitorApp(root)
    root.mainloop()