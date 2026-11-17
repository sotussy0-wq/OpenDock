"""
OpenDock - free, open-source widget dock for Windows 10/11.
An original project (MIT). Not affiliated with any commercial product.
"""
import atexit
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import date, datetime
from tkinter import filedialog, simpledialog

import psutil

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

HOME = os.path.expanduser("~")
CONFIG = os.path.join(HOME, ".opendock.json")
USAGE = os.path.join(HOME, ".opendock_usage.json")

THEMES = {
    "Black":    dict(bg="#0b0b0d", fg="#f2f2f3", dim="#8d8d94", accent="#4da3ff", chip="#1b1b20", alpha=1.0),
    "White":    dict(bg="#f4f5f7", fg="#16181d", dim="#6b7280", accent="#0a64d6", chip="#e2e5ea", alpha=1.0),
    "Midnight": dict(bg="#0d1530", fg="#e6ecff", dim="#8c9bd1", accent="#7aa2ff", chip="#18224a", alpha=1.0),
    "Glass":    dict(bg="#20283a", fg="#ffffff", dim="#b6c0d6", accent="#8fd0ff", chip="#34405a", alpha=0.82),
}
SIZES = {"Small": (44, 7, 10), "Medium": (56, 8, 12), "Large": (72, 9, 14)}
ORDER = [("clock", "TIME"), ("world", "WORLD CLOCK"), ("weather", "WEATHER"), ("cpu", "CPU"),
         ("ram", "RAM"), ("net", "NETWORK"), ("bat", "BATTERY"), ("screen", "SCREEN TIME"),
         ("pomo", "POMODORO"), ("notes", "NOTES"), ("media", "MEDIA")]
DEFAULTS = {"edge": "bottom", "theme": "Black", "size": "Medium", "apps": [], "notes": "",
            "city": "", "tz2": "UTC", "hide_taskbar": False, "show_windows": True,
            "widgets": {k: True for k, _ in ORDER}}


def load():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            d = json.load(f)
        c = {**DEFAULTS, **d}
        c["widgets"] = {**DEFAULTS["widgets"], **d.get("widgets", {})}
        return c
    except Exception:
        return json.loads(json.dumps(DEFAULTS))


def save():
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


cfg = load()

# ------------------------------------------------------------ Win32 setup
user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32
HWND = wintypes.HWND
user32.GetParent.restype = HWND
user32.GetForegroundWindow.restype = HWND
user32.FindWindowW.restype = HWND
user32.SetForegroundWindow.argtypes = [HWND]
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.IsIconic.argtypes = [HWND]
shell32.SHAppBarMessage.restype = ctypes.c_size_t

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

# single instance
_mutex = kernel32.CreateMutexW(None, False, "OpenDockSingleInstance")
if kernel32.GetLastError() == 183:
    sys.exit(0)

ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS, ABM_GETSTATE, ABM_SETSTATE = 0, 1, 2, 3, 4, 10
ABE_TOP, ABE_BOTTOM = 1, 3


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


def _abd(hwnd):
    a = APPBARDATA()
    a.cbSize, a.hWnd = ctypes.sizeof(a), hwnd
    return a


root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.update_idletasks()
MY_HWND = user32.GetParent(root.winfo_id()) or root.winfo_id()
registered = False
HEIGHT = SIZES[cfg["size"]][0]


def dock():
    global registered, HEIGHT
    HEIGHT = SIZES[cfg["size"]][0]
    a = _abd(MY_HWND)
    if not registered:
        shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(a))
        registered = True
    top = cfg["edge"] == "top"
    a.uEdge = ABE_TOP if top else ABE_BOTTOM
    a.rc = wintypes.RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(a))
    if top:
        a.rc.bottom = a.rc.top + HEIGHT
    else:
        a.rc.top = a.rc.bottom - HEIGHT
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(a))
    r = a.rc
    root.geometry(f"{r.right - r.left}x{r.bottom - r.top}+{r.left}+{r.top}")


def taskbar_state(new=None):
    a = _abd(user32.FindWindowW("Shell_TrayWnd", None))
    if new is None:
        return shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(a))
    a.lParam = new
    shell32.SHAppBarMessage(ABM_SETSTATE, ctypes.byref(a))


ORIGINAL_TASKBAR = taskbar_state()


def apply_taskbar():
    taskbar_state(1 if cfg["hide_taskbar"] else ORIGINAL_TASKBAR)


def shutdown():
    global registered
    try:
        taskbar_state(ORIGINAL_TASKBAR)
    except Exception:
        pass
    if registered:
        shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(_abd(MY_HWND)))
        registered = False
    save_usage()


atexit.register(shutdown)

# ------------------------------------------------------------ autostart
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "OpenDock")
            return True
    except Exception:
        return False


def set_autostart(on):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
                winreg.SetValueEx(k, "OpenDock", 0, winreg.REG_SZ, exe)
            else:
                winreg.DeleteValue(k, "OpenDock")
    except Exception:
        pass


# ------------------------------------------------------------ screen time
try:
    with open(USAGE, encoding="utf-8") as f:
        usage = json.load(f)
except Exception:
    usage = {}


def save_usage():
    try:
        with open(USAGE, "w", encoding="utf-8") as f:
            json.dump(usage, f)
    except Exception:
        pass


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    user32.GetLastInputInfo(ctypes.byref(li))
    return (kernel32.GetTickCount() - li.dwTime) / 1000.0


def window_process(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name().replace(".exe", "")
    except Exception:
        return None


def track_screen_time():
    if idle_seconds() > 60:
        return
    name = window_process(user32.GetForegroundWindow())
    if not name:
        return
    day = usage.setdefault(date.today().isoformat(), {})
    day[name] = day.get(name, 0) + 1


def today_total():
    return sum(usage.get(date.today().isoformat(), {}).values())


def fmt_hm(s):
    s = int(s)
    return f"{s // 3600}h {s % 3600 // 60:02d}m"


# ------------------------------------------------------------ open windows
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)


def list_windows():
    out = []

    def cb(hwnd, _):
        if hwnd == MY_HWND or not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowLongW(hwnd, -20) & 0x80:  # tool window
            return True
        cloaked = ctypes.c_int(0)
        try:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
        except Exception:
            pass
        if cloaked.value:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value in ("Program Manager", "Settings"):
            return True
        out.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out[:10]


def focus_window(hwnd):
    h = HWND(hwnd)
    if user32.IsIconic(h):
        user32.ShowWindow(h, 9)
    user32.SetForegroundWindow(h)


# ------------------------------------------------------------ media keys
def key(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


# ------------------------------------------------------------ weather
WX = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog",
      51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 61: "Rain", 63: "Rain", 65: "Heavy rain",
      71: "Snow", 73: "Snow", 75: "Snow", 80: "Showers", 81: "Showers", 82: "Showers",
      95: "Storm", 96: "Storm", 99: "Storm"}
weather_text = {"v": "Set city"}


def fetch_weather():
    while True:
        city = cfg.get("city", "").strip()
        if city:
            try:
                q = urllib.parse.quote(city)
                with urllib.request.urlopen(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1", timeout=10) as r:
                    g = json.load(r)["results"][0]
                url = (f"https://api.open-meteo.com/v1/forecast?latitude={g['latitude']}&longitude={g['longitude']}"
                       "&current=temperature_2m,weather_code")
                with urllib.request.urlopen(url, timeout=10) as r:
                    c = json.load(r)["current"]
                weather_text["v"] = f"{c['temperature_2m']:.0f}°C {WX.get(c['weather_code'], '')}"
            except Exception:
                weather_text["v"] = "offline"
        else:
            weather_text["v"] = "Set city"
        time.sleep(900)


# ------------------------------------------------------------ UI
W = {}
T = THEMES[cfg["theme"]]
pomo = {"running": False, "end": 0, "length": 25 * 60}
chips_sig = {"v": None}
menu_vars = {}


def fonts():
    _, small, big = SIZES[cfg["size"]]
    return ("Segoe UI", small), ("Segoe UI Semibold", big)


def launch(path):
    try:
        os.startfile(path)
    except Exception:
        try:
            subprocess.Popen(path, shell=True)
        except Exception:
            pass


def add_app():
    p = filedialog.askopenfilename(title="Pin an app", filetypes=[("Programs", "*.exe *.lnk *.bat"), ("All", "*.*")])
    if p and p not in cfg["apps"]:
        cfg["apps"].append(p)
        save()
        build_ui()


def remove_app(p):
    cfg["apps"].remove(p)
    save()
    build_ui()
    return "break"


def chip(parent, text, command, right=None):
    b = tk.Label(parent, text=text, bg=T["chip"], fg=T["fg"], padx=10, pady=5,
                 font=fonts()[0], cursor="hand2")
    b.pack(side="left", padx=2, pady=(HEIGHT - 30) // 2)
    b.bind("<Button-1>", lambda e: command())
    if right:
        b.bind("<Button-3>", lambda e: right())
    return b


def make_widget(parent, key_, title):
    small, big = fonts()
    f = tk.Frame(parent, bg=T["bg"], padx=9)
    t = tk.Label(f, text=title, bg=T["bg"], fg=T["dim"], font=small)
    v = tk.Label(f, text="--", bg=T["bg"], fg=T["fg"], font=big)
    t.pack(anchor="w", pady=(max(2, HEIGHT // 10), 0))
    v.pack(anchor="w")
    W[key_] = v
    return f, v


def build_ui():
    global T
    T = THEMES[cfg["theme"]]
    for c in list(root.winfo_children()):
        if isinstance(c, tk.Frame):
            c.destroy()
    W.clear()
    chips_sig["v"] = None
    root.configure(bg=T["bg"])
    root.attributes("-alpha", T["alpha"])
    bar = tk.Frame(root, bg=T["bg"])
    bar.pack(fill="both", expand=True, padx=10)

    left = tk.Frame(bar, bg=T["bg"])
    left.pack(side="left", fill="y")
    W["left"] = left
    W["pins"] = tk.Frame(left, bg=T["bg"])
    W["pins"].pack(side="left", fill="y")
    W["wins"] = tk.Frame(left, bg=T["bg"])
    W["wins"].pack(side="left", fill="y", padx=(8, 0))
    for p in cfg["apps"]:
        name = os.path.splitext(os.path.basename(p))[0][:10] or "App"
        chip(W["pins"], name, lambda p=p: launch(p), right=lambda p=p: remove_app(p))

    right = tk.Frame(bar, bg=T["bg"])
    right.pack(side="right", fill="y")
    small, big = fonts()
    for k, title in reversed(ORDER):
        if not cfg["widgets"].get(k, True):
            continue
        if k == "media":
            f = tk.Frame(right, bg=T["bg"], padx=6)
            row = tk.Frame(f, bg=T["bg"])
            row.pack(expand=True)
            for sym, vk in (("⏮", 0xB1), ("⏯", 0xB3), ("⏭", 0xB0), ("🔉", 0xAE), ("🔊", 0xAF)):
                l = tk.Label(row, text=sym, bg=T["bg"], fg=T["fg"], font=("Segoe UI Symbol", big[1]), cursor="hand2", padx=3)
                l.pack(side="left")
                l.bind("<Button-1>", lambda e, vk=vk: key(vk))
        else:
            f, v = make_widget(right, k, title)
            if k == "pomo":
                for w in (f, v):
                    w.bind("<Button-1>", lambda e: pomo_toggle())
            elif k == "notes":
                for w in (f, v):
                    w.bind("<Button-1>", lambda e: open_notes())
            elif k == "screen":
                for w in (f, v):
                    w.bind("<Button-1>", lambda e: show_screen_time())
            elif k == "weather":
                for w in (f, v):
                    w.bind("<Button-1>", lambda e: set_city())
            f.configure(cursor="hand2" if k in ("pomo", "notes", "screen", "weather") else "")
        f.pack(side="right", fill="y")
    refresh_notes()


def pomo_toggle():
    pomo["running"] = not pomo["running"]
    if pomo["running"]:
        pomo["end"] = time.time() + pomo["length"]


def open_notes():
    win = tk.Toplevel(root)
    win.title("OpenDock notes")
    win.attributes("-topmost", True)
    win.geometry("380x280+80+80")
    txt = tk.Text(win, bg=T["chip"], fg=T["fg"], insertbackground=T["fg"], wrap="word",
                  font=("Segoe UI", 11), bd=0, padx=10, pady=10)
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", cfg["notes"])

    def close():
        cfg["notes"] = txt.get("1.0", "end-1c")
        save()
        win.destroy()
        refresh_notes()

    win.protocol("WM_DELETE_WINDOW", close)


def refresh_notes():
    if "notes" in W:
        s = cfg["notes"].strip()
        W["notes"].config(text=(s.split("\n")[0][:16] if s else "empty"))


def show_screen_time():
    win = tk.Toplevel(root)
    win.title("Screen time today")
    win.attributes("-topmost", True)
    win.configure(bg=T["bg"])
    win.geometry("300x340+80+80")
    day = usage.get(date.today().isoformat(), {})
    tk.Label(win, text=f"Today: {fmt_hm(sum(day.values()))}", bg=T["bg"], fg=T["fg"],
             font=("Segoe UI Semibold", 14)).pack(pady=10)
    for name, secs in sorted(day.items(), key=lambda x: -x[1])[:12]:
        tk.Label(win, text=f"{name:<22} {fmt_hm(secs)}", bg=T["bg"], fg=T["dim"],
                 font=("Consolas", 10), anchor="w").pack(fill="x", padx=16)


def set_city():
    c = simpledialog.askstring("Weather", "City name:", initialvalue=cfg.get("city", ""), parent=root)
    if c is not None:
        cfg["city"] = c
        save()
        weather_text["v"] = "…"


def set_tz():
    c = simpledialog.askstring("World clock", "Time zone (e.g. Europe/London, America/New_York, Asia/Tokyo):",
                               initialvalue=cfg["tz2"], parent=root)
    if c:
        cfg["tz2"] = c
        save()


def fmt_speed(b):
    for u in ("B/s", "KB/s", "MB/s"):
        if b < 1024:
            return f"{b:.0f}{u}"
        b /= 1024
    return f"{b:.1f}GB/s"


last_net = {"t": time.time(), "b": psutil.net_io_counters()}
psutil.cpu_percent()
tick_n = {"n": 0}


def refresh_windows():
    if not cfg["show_windows"] or "wins" not in W:
        return
    wins = list_windows()
    sig = tuple(wins)
    if sig == chips_sig["v"]:
        return
    chips_sig["v"] = sig
    for c in W["wins"].winfo_children():
        c.destroy()
    for hwnd, title in wins:
        chip(W["wins"], title[:14], lambda h=hwnd: focus_window(h))


def tick():
    tick_n["n"] += 1
    try:
        track_screen_time()
        if tick_n["n"] % 30 == 0:
            save_usage()
        if tick_n["n"] % 2 == 0:
            refresh_windows()
        now = datetime.now()
        if "clock" in W:
            W["clock"].config(text=now.strftime("%H:%M  %a %d %b"))
        if "world" in W:
            try:
                W["world"].config(text=datetime.now(ZoneInfo(cfg["tz2"])).strftime("%H:%M ") + cfg["tz2"].split("/")[-1][:10])
            except Exception:
                W["world"].config(text="set zone")
        if "weather" in W:
            W["weather"].config(text=weather_text["v"])
        if "cpu" in W:
            W["cpu"].config(text=f"{psutil.cpu_percent():.0f}%")
        if "ram" in W:
            W["ram"].config(text=f"{psutil.virtual_memory().percent:.0f}%")
        n = psutil.net_io_counters()
        dt = max(time.time() - last_net["t"], 0.001)
        d = (n.bytes_recv - last_net["b"].bytes_recv) / dt
        u = (n.bytes_sent - last_net["b"].bytes_sent) / dt
        last_net.update(t=time.time(), b=n)
        if "net" in W:
            W["net"].config(text=f"↓{fmt_speed(d)} ↑{fmt_speed(u)}")
        if "bat" in W:
            b = psutil.sensors_battery()
            W["bat"].config(text="AC" if b is None else f"{b.percent:.0f}%{' ⚡' if b.power_plugged else ''}")
        if "screen" in W:
            W["screen"].config(text=fmt_hm(today_total()))
        if "pomo" in W:
            if pomo["running"]:
                left = int(pomo["end"] - time.time())
                if left <= 0:
                    pomo["running"] = False
                    W["pomo"].config(text="Done!", fg=T["accent"])
                    root.bell()
                else:
                    W["pomo"].config(text=f"{left // 60:02d}:{left % 60:02d}", fg=T["accent"])
            elif W["pomo"].cget("text") != "Done!":
                W["pomo"].config(text="25:00", fg=T["fg"])
    except Exception:
        pass
    root.after(1000, tick)


# ------------------------------------------------------------ right-click menu
menu = tk.Menu(root, tearoff=0)


def rebuild():
    save()
    build_ui()
    dock()


def build_menu():
    menu.add_command(label="Pin an app…", command=add_app)
    th = tk.Menu(menu, tearoff=0)
    menu_vars["theme"] = tk.StringVar(value=cfg["theme"])
    for n in THEMES:
        th.add_radiobutton(label=n, variable=menu_vars["theme"], value=n,
                           command=lambda: (cfg.update(theme=menu_vars["theme"].get()), rebuild()))
    menu.add_cascade(label="Style", menu=th)
    sz = tk.Menu(menu, tearoff=0)
    menu_vars["size"] = tk.StringVar(value=cfg["size"])
    for n in SIZES:
        sz.add_radiobutton(label=n, variable=menu_vars["size"], value=n,
                           command=lambda: (cfg.update(size=menu_vars["size"].get()), rebuild()))
    menu.add_cascade(label="Size", menu=sz)
    ed = tk.Menu(menu, tearoff=0)
    menu_vars["edge"] = tk.StringVar(value=cfg["edge"])
    for n in ("top", "bottom"):
        ed.add_radiobutton(label=n.capitalize(), variable=menu_vars["edge"], value=n,
                           command=lambda: (cfg.update(edge=menu_vars["edge"].get()), rebuild()))
    menu.add_cascade(label="Position", menu=ed)
    wm = tk.Menu(menu, tearoff=0)
    for k, title in ORDER:
        v = tk.BooleanVar(value=cfg["widgets"].get(k, True))
        menu_vars[k] = v
        wm.add_checkbutton(label=title.title(), variable=v,
                           command=lambda k=k: (cfg["widgets"].__setitem__(k, menu_vars[k].get()), rebuild()))
    menu.add_cascade(label="Widgets", menu=wm)
    menu.add_separator()
    menu_vars["wins"] = tk.BooleanVar(value=cfg["show_windows"])
    menu.add_checkbutton(label="Show open windows", variable=menu_vars["wins"],
                         command=lambda: (cfg.update(show_windows=menu_vars["wins"].get()), rebuild()))
    menu_vars["hide"] = tk.BooleanVar(value=cfg["hide_taskbar"])
    menu.add_checkbutton(label="Auto-hide Windows taskbar", variable=menu_vars["hide"],
                         command=lambda: (cfg.update(hide_taskbar=menu_vars["hide"].get()), apply_taskbar(), save()))
    menu_vars["auto"] = tk.BooleanVar(value=autostart_enabled())
    menu.add_checkbutton(label="Start with Windows", variable=menu_vars["auto"],
                         command=lambda: set_autostart(menu_vars["auto"].get()))
    menu.add_command(label="Weather city…", command=set_city)
    menu.add_command(label="World clock zone…", command=set_tz)
    menu.add_separator()
    menu.add_command(label="Quit OpenDock", command=quit_app)


def quit_app():
    shutdown()
    root.destroy()


root.bind_all("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
root.protocol("WM_DELETE_WINDOW", quit_app)

build_menu()
build_ui()
dock()
apply_taskbar()
threading.Thread(target=fetch_weather, daemon=True).start()
tick()
root.mainloop()
