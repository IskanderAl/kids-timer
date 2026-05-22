import sys
import os
import subprocess

# Отвязываемся от родительского процесса (PowerShell / cmd)
if os.environ.get("TIMER_DETACHED") != "1":
    env = os.environ.copy()
    env["TIMER_DETACHED"] = "1"
    subprocess.Popen(
        [sys.executable] + sys.argv,
        env=env,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "timer_err.log"), "w"),
    )
    sys.exit(0)

import tkinter as tk
from PIL import Image, ImageTk
import winsound
import ctypes
import threading
import socket

# Один экземпляр — блокировка через сокет
_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _lock_socket.bind(("127.0.0.1", 47321))
except OSError:
    import sys
    sys.exit(0)

BASE = os.path.dirname(os.path.abspath(__file__))
BG_PATH = os.path.join(BASE, "bg.jpg")
ICO_PATH = os.path.join(BASE, "icon.ico")

WIN_W, WIN_H = 320, 210
MINI_W, MINI_H = 90, 36
DARK = "#1a1a1a"


class MiniWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        orig = Image.open(BG_PATH)
        bg = orig.resize((MINI_W, MINI_H), Image.LANCZOS)
        self._bg = ImageTk.PhotoImage(bg)

        c = tk.Canvas(self, width=MINI_W, height=MINI_H,
                      highlightthickness=0, bd=0)
        c.pack()
        c.create_image(0, 0, anchor="nw", image=self._bg)
        c.create_rectangle(0, 0, MINI_W, MINI_H,
                           fill="black", stipple="gray50", outline="")
        self._time_lbl = c.create_text(
            MINI_W // 2, MINI_H // 2,
            text="00:00", font=("Segoe UI", 14, "bold"), fill="white"
        )
        self._canvas = c

        c.bind("<ButtonPress-1>", self._drag_start)
        c.bind("<B1-Motion>", self._drag_move)

    def set_time(self, txt):
        self._canvas.itemconfig(self._time_lbl, text=txt)

    def set_color(self, color):
        self._canvas.itemconfig(self._time_lbl, fill=color)

    def bind_click(self, callback):
        self._canvas.bind("<ButtonPress-1>", lambda e: callback())

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.winfo_x() + e.x - self._dx
        y = self.winfo_y() + e.y - self._dy
        self.geometry(f"+{x}+{y}")


class Timer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Таймер")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._try_close)
        self.iconbitmap(ICO_PATH)

        self._running = False
        self._remaining = 0
        self._total = 0
        self._job = None
        self._mini = None

        self._build_ui()
        self._center()

    def _build_ui(self):
        orig = Image.open(BG_PATH)
        bg = orig.resize((WIN_W, WIN_H), Image.LANCZOS)
        self._bg_full = ImageTk.PhotoImage(bg)

        c = tk.Canvas(self, width=WIN_W, height=WIN_H,
                      highlightthickness=0, bd=0)
        c.pack()
        c.create_image(0, 0, anchor="nw", image=self._bg_full)
        c.create_rectangle(0, 0, WIN_W, WIN_H,
                           fill="black", stipple="gray50", outline="")

        self._time_full = c.create_text(
            WIN_W // 2, 50,
            text="00:00", font=("Segoe UI", 52, "bold"), fill="white"
        )
        c.create_text(WIN_W // 2, 125, text=":",
                      font=("Segoe UI", 22, "bold"), fill="#aaa")

        spin_cfg = dict(width=3, font=("Segoe UI", 16, "bold"),
                        bg=DARK, fg="white", relief="flat",
                        buttonbackground="#333", insertbackground="white",
                        justify="center", highlightthickness=0, bd=0)

        self._hours = tk.IntVar(value=0)
        self._mins = tk.IntVar(value=5)

        h_spin = tk.Spinbox(c, from_=0, to=23, textvariable=self._hours, **spin_cfg)
        m_spin = tk.Spinbox(c, from_=0, to=59, textvariable=self._mins, **spin_cfg)
        c.create_window(WIN_W // 2 - 42, 125, window=h_spin)
        c.create_window(WIN_W // 2 + 42, 125, window=m_spin)

        self._btn = tk.Button(c, text="▶  Старт",
                              font=("Segoe UI", 12, "bold"),
                              bg="#e94560", fg="white", relief="flat",
                              activebackground="#c73652", activeforeground="white",
                              padx=20, pady=5, cursor="hand2",
                              command=self._start, bd=0)
        c.create_window(WIN_W // 2, 183, window=self._btn)
        self._canvas = c

    def _try_close(self):
        if not self._running:
            self.destroy()

    def _start(self):
        total = self._hours.get() * 3600 + self._mins.get() * 60
        if total <= 0:
            return
        self._remaining = total
        self._total = total
        self._running = True

        self._mini = MiniWindow(self)
        # Позиция: где сейчас главное окно
        x, y = self.winfo_x(), self.winfo_y()
        self._mini.geometry(f"{MINI_W}x{MINI_H}+{x}+{y}")
        self.withdraw()
        self._tick()

    def _tick(self):
        if not self._running:
            return
        h = self._remaining // 3600
        m = (self._remaining % 3600) // 60
        s = self._remaining % 60
        txt = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        if self._mini:
            self._mini.set_time(txt)

        if self._remaining <= 0:
            self._finish()
            return

        if self._remaining == 120 and self._total > 120:
            threading.Thread(target=self._warn_beep, daemon=True).start()

        self._remaining -= 1
        self._job = self.after(1000, self._tick)

    def _finish(self):
        self._running = False
        # Показываем галку в мини-окне, клик по нему вернёт настройки
        if self._mini:
            self._mini.set_time("✓")
            self._mini.set_color("#00ff88")
            self._mini.bind_click(self._reset_to_full)
        threading.Thread(target=self._alarm, daemon=True).start()

    def _reset_to_full(self):
        if self._mini:
            self._mini.destroy()
            self._mini = None
        self._canvas.itemconfig(self._time_full, text="00:00", fill="white")
        self._btn.config(state="normal", text="▶  Старт")
        self.deiconify()

    def _warn_beep(self):
        for _ in range(2):
            winsound.Beep(800, 300)

    def _alarm(self):
        for _ in range(5):
            winsound.Beep(1000, 400)
            winsound.Beep(800, 300)
        ctypes.windll.user32.LockWorkStation()

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{WIN_W}x{WIN_H}+{(sw-WIN_W)//2}+{(sh-WIN_H)//2}")


if __name__ == "__main__":
    Timer().mainloop()
