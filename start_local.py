"""Local Windows launcher for the read-only Verdigo Kash Alerts beta.

Secrets are entered in masked widgets, stored only in process memory and passed
to the bot as environment variables. No credentials are printed or saved.
"""
import os
import pathlib
import re
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

ROOT = pathlib.Path(__file__).resolve().parent


def credentials_dialog():
    root = tk.Tk()
    root.title("Verdigo Kash Alerts — Connect")
    root.geometry("590x375")
    root.resizable(False, False)
    root.configure(padx=25, pady=20)
    root.attributes("-topmost", True)

    tk.Label(root, text="Verdigo Kash Alerts", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(
        root, text="Local test: nothing is saved or sent anywhere except Kash and Telegram.",
        font=("Segoe UI", 9), fg="#444444", wraplength=535, justify="left"
    ).pack(anchor="w", pady=(0, 16))

    credentials = {}
    fields = {}

    def make_field(title, hint):
        tk.Label(root, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = tk.Frame(root)
        row.pack(fill="x", pady=(5, 2))
        entry = ttk.Entry(row, show="*", font=("Consolas", 11))
        entry.pack(side="left", fill="x", expand=True)

        def paste():
            try:
                value = root.clipboard_get().strip()
            except tk.TclError:
                messagebox.showwarning(
                    "Clipboard is empty", "Copy the secret first, then click Paste from clipboard.",
                    parent=root,
                )
                return
            if not value:
                messagebox.showwarning(
                    "Clipboard is empty", "Copy the secret first, then click Paste from clipboard.",
                    parent=root,
                )
                return
            entry.delete(0, tk.END)
            entry.insert(0, value)
            update_status()
            entry.focus_set()

        ttk.Button(row, text="Paste from clipboard", command=paste).pack(
            side="left", padx=(8, 0)
        )
        tk.Label(root, text=hint, font=("Segoe UI", 9), fg="#555555").pack(
            anchor="w", pady=(0, 12)
        )
        entry.bind("<KeyRelease>", lambda _event: update_status())
        fields[title] = entry
        return entry

    token = make_field(
        "1. Telegram BotFather token",
        "From @BotFather. It contains digits, a colon (:), and letters. Not your bot's @username.",
    )
    kash = make_field(
        "2. Kash API key (markets:read only)",
        "The read-only key begins with kash_live_. Never use trades:write here.",
    )

    status = tk.StringVar(value="Copy each secret and press Paste from clipboard beside its field.")
    tk.Label(root, textvariable=status, wraplength=540, justify="left",
             font=("Segoe UI", 9), fg="#333333").pack(anchor="w", pady=(3, 11))

    def update_status():
        t = token.get().strip()
        k = kash.get().strip()
        status.set(
            f"Telegram token: {'received (' + str(len(t)) + ' characters)' if t else 'empty'}"
            f"   |   Kash key: {'received (' + str(len(k)) + ' characters)' if k else 'empty'}"
        )

    def start():
        t = token.get().strip()
        k = kash.get().strip()
        if not re.fullmatch(r"[0-9]{5,}:[A-Za-z0-9_-]{20,}", t):
            messagebox.showerror(
                "Telegram token is missing or invalid",
                "Paste the complete BotFather token into the FIRST field. "
                "It must have digits, a colon, and a long secret. "
                "Click the Paste from clipboard button and check the character count.",
                parent=root,
            )
            token.focus_set()
            return
        if not k.startswith("kash_live_") or len(k) < 20:
            messagebox.showerror(
                "Kash key is missing or invalid",
                "Paste your read-only Kash key into the SECOND field. "
                "It should begin with kash_live_.",
                parent=root,
            )
            kash.focus_set()
            return
        credentials["telegram"] = t
        credentials["kash"] = k
        root.destroy()

    ttk.Button(root, text="Start Telegram bot", command=start).pack(
        anchor="e", pady=(2, 0)
    )
    token.focus_set()
    root.mainloop()
    return credentials


def main():
    secrets = credentials_dialog()
    if not secrets:
        print("Launch cancelled: no tokens have been saved.")
        return

    env = os.environ.copy()
    env["TELEGRAM_BOT_TOKEN"] = secrets["telegram"]
    env["KASH_API_KEY"] = secrets["kash"]
    secrets.clear()

    print("Verdigo Kash Alerts is starting (read-only monitoring).", flush=True)
    print("Credentials are not saved. Leave this command window open.", flush=True)
    print("In Telegram, open @VerdigoKashAlertsBot and send /start.", flush=True)
    print("To stop the bot press Ctrl+C in this window.", flush=True)
    try:
        subprocess.run([sys.executable, "-u", str(ROOT / "bot.py")],
                       cwd=ROOT, env=env, check=False)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
