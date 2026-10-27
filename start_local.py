"""Local launch helper. Secrets stay in process memory, never in GitHub or files."""
import os
import pathlib
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

ROOT = pathlib.Path(__file__).resolve().parent

def main():
    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        telegram_key = simpledialog.askstring(
            "Verdigo Kash Alerts",
            "Paste the TELEGRAM BOT token from BotFather:",
            parent=window, show="*",
        )
        if not telegram_key:
            return
        kash_key = simpledialog.askstring(
            "Verdigo Kash Alerts",
            "Paste your READ-ONLY Kash API key:",
            parent=window, show="*",
        )
        if not kash_key:
            return
        kash_key = kash_key.strip()
        if not kash_key.startswith("kash_live_"):
            messagebox.showerror(
                "Kash API key", "The key must begin with kash_live_. Please check what you copied.",
                parent=window,
            )
            return
    finally:
        window.destroy()

    env = os.environ.copy()
    env["TELEGRAM_BOT_TOKEN"] = telegram_key.strip()
    env["KASH_API_KEY"] = kash_key
    print("Starting Verdigo Kash Alerts in read-only monitoring mode.")
    print("Tokens will not be printed or saved. Leave this window open during local testing.")
    print("Use Ctrl+C to stop. Telegram: send /start to your bot.")
    try:
        subprocess.run([sys.executable, "-u", str(ROOT / "bot.py")],
                       cwd=ROOT, env=env, check=False)
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
