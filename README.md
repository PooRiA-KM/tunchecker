```markdown
# VPN Connection Monitor & Telegram Notifier

A lightweight Python desktop application built with `tkinter` to monitor the real-time status of your specific network interface (such as OpenVPN TAP/TUN/Wintun adapters). If the selected network adapter disconnects, the app immediately sends an alert notification to your Telegram channel or chat via a Telegram Bot, with optional proxy support.

## Features

- **Interface Selection:** Automatically detects and lets you choose any network interface from a dropdown menu.
- **Customizable Interval:** Dynamically adjust how often (in seconds) the application checks the interface status.
- **Telegram Integration:** Sends instant alerts whenever the network adapter changes from a connected state to a disconnected state.
- **Proxy Support:** Includes fields to route Telegram API requests through a custom HTTP/SOCKS proxy server if the network environment restricts direct Telegram access.
- **Multi-threaded Execution:** The monitoring loop runs on a background thread, ensuring the GUI remains perfectly responsive.

## Prerequisites

Before running the application, make sure you have Python installed, along with the required `requests` library.

Install the dependency using pip:
```bash
pip install requests