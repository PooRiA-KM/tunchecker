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
        self.root.geometry("420x450")
        self.root.resizable(False, False)

        # متغیرهای وضعیت
        self.is_running = False
        self.monitor_thread = None

        self.setup_ui()

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Tahoma", 9))
        style.configure("TButton", font=("Tahoma", 9))

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
        self.entry_bot_token = ttk.Entry(frame_telegram, width=25)
        self.entry_bot_token.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(frame_telegram, text="چت آیدی (Chat ID):").grid(row=1, column=0, sticky="w", pady=2)
        self.entry_chat_id = ttk.Entry(frame_telegram, width=25)
        self.entry_chat_id.grid(row=1, column=1, padx=5, pady=2)

        # وضعیت و دکمه‌ها
        frame_actions = ttk.Frame(self.root, padding=10)
        frame_actions.pack(fill="x", padx=10, pady=5)

        self.lbl_status = ttk.Label(frame_actions, text="وضعیت: غیرفعال", font=("Tahoma", 10, "bold"),
                                    foreground="gray")
        self.lbl_status.pack(pady=5)

        self.btn_toggle = ttk.Button(frame_actions, text="شروع مانیتورینگ", command=self.toggle_monitoring)
        self.btn_toggle.pack(fill="x", pady=5)

    def is_openvpn_connected(self):
        """
        بررسی وضعیت کارت شبکه OpenVPN (TAP / TUN / Wintun) در ویندوز
        """
        try:
            # اجرا دستور netsh برای بررسی وضعیت آداپتورهای شبکه
            output = subprocess.check_output(
                ["netsh", "interface", "show", "interface"],
                creationflags=subprocess.CREATE_NO_WINDOW
            ).decode('utf-8', errors='ignore')

            # بررسی خط به خط آداپتورها
            for line in output.splitlines():
                line_lower = line.lower()
                # کارت شبکه‌های مربوط به OpenVPN معمولا TAP، TUN یا OpenVPN نام دارند
                if any(k in line_lower for k in ["Local Area Connection"]):
                    # چک کردن اینکه وضعیت کارت شبکه Connected است یا خیر
                    if "Connected" in line_lower and "Disconnected" not in line_lower:
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

            if connected:
                self.lbl_status.config(text="وضعیت: کارت شبکه OpenVPN متصل است", foreground="green")
                was_connected = True
            else:
                self.lbl_status.config(text="وضعیت: کارت شبکه OpenVPN قطع شد!", foreground="red")
                if was_connected:
                    self.send_telegram_alert("⚠️ هشدار: اتصال شبکه OpenVPN سیستم شما قطع شد!")
                    was_connected = False

            for _ in range(interval):
                if not self.is_running:
                    break
                time.sleep(1)

    def toggle_monitoring(self):
        if not self.is_running:
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
        self.entry_interval.config(state=state)
        self.entry_proxy_ip.config(state=state)
        self.entry_proxy_port.config(state=state)
        self.entry_bot_token.config(state=state)
        self.entry_chat_id.config(state=state)


if __name__ == "__main__":
    root = tk.Tk()
    app = VPNMonitorApp(root)
    root.mainloop()