# =============================================================================
# neko.pyw — Minimal Automation Companion 
# =============================================================================

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as filedialog
import threading
import sys
import time
import random
import os
import json
import datetime
import subprocess
import webbrowser
import ctypes
import pygame
import keyboard
import psutil
try:
    import pyperclip
except ImportError:
    pyperclip = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if getattr(sys, 'frozen', False):
    current_dir = os.path.dirname(sys.executable)
else:
    _self = os.path.abspath(__file__)
    _self_dir = os.path.dirname(_self)
    if os.path.basename(_self_dir).lower() == "neko_utils":
        current_dir = os.path.dirname(_self_dir)
    else:
        current_dir = _self_dir

UTILS_DIR = os.path.join(current_dir, "neko_utils")
AUTOMATIONS_FILE = os.path.join(UTILS_DIR, "automations.json")
HISTORY_FILE      = os.path.join(UTILS_DIR, "history.json")
CALC_HIST_FILE    = os.path.join(UTILS_DIR, "calc_history.json")

pygame.mixer.init()
meow      = pygame.mixer.Sound(os.path.join(UTILS_DIR, "meow.mp3"))
meow_low  = pygame.mixer.Sound(os.path.join(UTILS_DIR, "meow_low.wav"))
meow_high = pygame.mixer.Sound(os.path.join(UTILS_DIR, "meow_high.wav"))
purr      = pygame.mixer.Sound(os.path.join(UTILS_DIR, "purr.mp3"))

def sound_meow():
    random.choice([meow, meow_low, meow_high]).play()

# ---------------------------------------------------------------------------
# Data model helpers
# ---------------------------------------------------------------------------
def _migrate(data):
    for a in data:
        t = a.get("trigger", {})
        if t.get("type") == "neko_click":
            t["type"] = "neko_left_click"
    return data

def load_automations():
    if os.path.exists(AUTOMATIONS_FILE):
        try:
            with open(AUTOMATIONS_FILE, "r", encoding="utf-8") as f:
                return _migrate(json.load(f))
        except Exception:
            pass
    return []

def save_automations(data):
    os.makedirs(UTILS_DIR, exist_ok=True)
    with open(AUTOMATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

automations = load_automations()

# ---------------------------------------------------------------------------
# Clipboard history tracking
# ---------------------------------------------------------------------------
clipboard_history = []
_clip_last = ""

def _track_clipboard():
    global clipboard_history, _clip_last
    while True:
        time.sleep(0.5)
        if pyperclip is None:
            continue
        try:
            text = pyperclip.paste()
        except Exception:
            continue
        if text and text != _clip_last:
            _clip_last = text
            if text in clipboard_history:
                clipboard_history.remove(text)
            clipboard_history.append(text)
            if len(clipboard_history) > 10:
                clipboard_history.pop(0)

threading.Thread(target=_track_clipboard, daemon=True).start()


def get_trigger_types(auto):
    t = auto.get("trigger", {})
    if t.get("type") == "multi":
        return t.get("types", [])
    return [t.get("type", "")]

def get_trigger_value(auto):
    return auto.get("trigger", {}).get("value", "")

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def log_history(name, trigger_type):
    os.makedirs(UTILS_DIR, exist_ok=True)
    entry = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "name": name, "trigger": trigger_type}
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(entry)
    history = history[-200:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------
def _find_window_by_exe(exe_name):
    """Return hwnd of a window matching exe name, or None."""
    import ctypes
    found = [None]
    exe_lower = exe_name.lower().replace(".exe", "")
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible

    def callback(hwnd, lParam):
        if IsWindowVisible(hwnd):
            pid = ctypes.c_ulong()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                p = psutil.Process(pid.value)
                if exe_lower in p.name().lower():
                    found[0] = hwnd
                    return False
            except Exception:
                pass
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return found[0]

def run_action(action):
    atype  = action.get("type")
    avalue = action.get("value", "")
    try:
        if atype == "open_url":
            webbrowser.open(avalue)

        elif atype == "search_google":
            webbrowser.open(f"https://www.google.com/search?q={avalue.replace(' ', '+')}")

        elif atype == "open_app":
            subprocess.Popen(f'start "" "{avalue}"', shell=True)

        elif atype == "set_volume":
            vol = max(0, min(100, int(avalue)))
            set_ok = False
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                cast(iface, POINTER(IAudioEndpointVolume)).SetMasterVolumeLevelScalar(vol/100.0, None)
                set_ok = True
            except Exception:
                pass
            if not set_ok:
                nircmd = os.path.join(current_dir, "nircmd.exe")
                if os.path.exists(nircmd):
                    subprocess.Popen([nircmd, "setsysvolume", str(int(vol/100*65535))])
                    set_ok = True
            if not set_ok:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     f"$w=New-Object -ComObject WScript.Shell;"
                     f"1..50|%{{$w.SendKeys([char]174)}};"
                     f"1..[math]::Round({vol}/2)|%{{$w.SendKeys([char]175)}}"],
                    shell=False)

        elif atype == "run_shell":
            subprocess.Popen(avalue, shell=True)

        elif atype == "wait":
            secs = max(0, float(avalue))
            time.sleep(secs)

        elif atype == "close_app":
            # Resolve .lnk shortcuts to the real exe name
            exe = os.path.basename(avalue)
            if exe.lower().endswith(".lnk"):
                try:
                    import winshell
                    lnk = winshell.shortcut(avalue)
                    exe = os.path.basename(lnk.path)
                except Exception:
                    # fallback: strip .lnk and try taskkill by window title via powershell
                    exe = exe[:-4] + ".exe"
            # Try graceful WM_CLOSE first
            hwnd = _find_window_by_exe(exe)
            if hwnd:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            else:
                # taskkill without /F — graceful
                subprocess.Popen(["taskkill", "/IM", exe], shell=False)

        elif atype == "notification":
            # Show a neko-styled notification window on the main thread
            root.after(0, lambda msg=avalue: show_notification(msg))

        elif atype == "close_tab":
            # Close a browser tab at a given position (0 = first tab)
            try:
                pos = int(avalue)
            except Exception:
                pos = 0
            pos = max(0, pos)
            # Jump to the target tab: Ctrl+1..Ctrl+8 select tabs 1-8,
            # Ctrl+9 selects the last tab. Then close it with Ctrl+W.
            jump_num = min(pos + 1, 9)
            keyboard.send(f"ctrl+{jump_num}")
            time.sleep(0.1)
            keyboard.send("ctrl+w")

        elif atype == "toggle_neko":
            root.after(0, hotkey_toggle)

    except Exception as e:
        print(f"[neko] action error ({atype}): {e}")

def run_automation(automation, trigger_type="manual"):
    def _run():
        log_history(automation.get("name", "?"), trigger_type)
        has_toggle = any(a.get("type") == "toggle_neko"
                                for a in automation.get("actions", []))
        if trigger_type not in ("manual", "neko_left_click",
                                        "neko_right_click", "neko_hold_pick") and not has_toggle:
                    root.after(0, sound_meow)
        for action in automation.get("actions", []):
            run_action(action)
    threading.Thread(target=_run, daemon=True).start()

# ---------------------------------------------------------------------------
# Keybind registry
# ---------------------------------------------------------------------------
_registered_hotkeys: list = []

def register_keybind_triggers():
    global _registered_hotkeys
    for hk in _registered_hotkeys:
        try:
            keyboard.remove_hotkey(hk)
        except Exception:
            pass
    _registered_hotkeys = []
    for auto in automations:
        if "keybind" in get_trigger_types(auto):
            hk = get_trigger_value(auto)
            if hk:
                try:
                    keyboard.add_hotkey(hk, lambda a=auto: run_automation(a, "keybind"))
                    _registered_hotkeys.append(hk)
                except Exception as e:
                    print(f"[neko] keybind error ({hk}): {e}")

register_keybind_triggers()

# ---------------------------------------------------------------------------
# Time trigger
# ---------------------------------------------------------------------------
def time_trigger_loop():
    fired: set = set()
    while True:
        time.sleep(15)
        now = datetime.datetime.now().strftime("%H:%M")
        for i, auto in enumerate(automations):
            if "time_of_day" in get_trigger_types(auto):
                if get_trigger_value(auto) == now:
                    key = (i, now)
                    if key not in fired:
                        fired.add(key)
                        run_automation(auto, "time_of_day")
        fired = {k for k in fired if k[1] == now}

threading.Thread(target=time_trigger_loop, daemon=True).start()

# ---------------------------------------------------------------------------
# App-opened / app-closed trigger watcher
# ---------------------------------------------------------------------------
_prev_procs: set = set()

def app_watch_loop():
    global _prev_procs
    _prev_procs = {p.name().lower() for p in psutil.process_iter(['name'])}
    while True:
        time.sleep(3)
        try:
            cur_procs = {p.name().lower() for p in psutil.process_iter(['name'])}
        except Exception:
            continue
        opened = cur_procs - _prev_procs
        closed = _prev_procs - cur_procs
        for auto in automations:
            trig_types = get_trigger_types(auto)
            val = get_trigger_value(auto).lower()
            if "app_opened" in trig_types:
                if any(val in name for name in opened):
                    run_automation(auto, "app_opened")
            if "app_closed" in trig_types:
                if any(val in name for name in closed):
                    run_automation(auto, "app_closed")
        _prev_procs = cur_procs

threading.Thread(target=app_watch_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Cat sprites
# ---------------------------------------------------------------------------
facing_right           = True
mouse_tracking_enabled = True
last_interaction_time  = time.time()

_last_wake_time = time.time()
_mouse_over_window = False

def _wake():
    """Restore full opacity and reset interaction timer."""
    global last_interaction_time, _last_wake_time
    last_interaction_time = time.time()
    _last_wake_time = time.time()
    root.attributes("-alpha", 1.0)

hop_counter = hop_dx = hop_dy = 0

normal_cat_l  = "╱|    \n(˚˕ 。7\n|、˜〵\n    じしˍ,)ノ"
sleepy_cat_l  = "     zZ\n╱|    \n(-ㅅ- 7\n       (ˍ,     ˜ˍ,)ノ"
hover_cat_l   = "╱|    \n(`˕ 。7\n|、˜〵\n    じしˍ,)ノ"
pressed_cat_l = "╱|    \n(`ˎ - 7\n|、˜〵\n    じしˍ,)ノ"
looking_cat_l = "╱|  ?\n(˚˕ 。7\n|、˜〵\n    じしˍ,)ノ"
pet_cat_l    = "╱|  ♡\n(-ㅅ- 7\n|、˜〵\n    じしˍ,)ノ"

normal_cat_r  = "    |╲\n< 。˕˚)\n/ ˜     |\nヽ(,ˍりり    "
sleepy_cat_r  = "     zZ\n╱|    \n(-ㅅ- 7\n       (ˍ,     ˜ˍ,)ノ"
hover_cat_r   = "    |╲\n< 。˕´)\n/ ˜     |\nヽ(,ˍりり    "
pressed_cat_r = "    |╲\n< - ˎ´)\n/ ˜     |\nヽ(,ˍりり    "
looking_cat_r = "╱|  ?\n(˚˕ 。7\n|、˜〵\n    じしˍ,)ノ"
pet_cat_r     = "♡   |╲\n< -ㅅ-)\n/ ˜     |\nヽ(,ˍりり    "

def get_cat_sprite(state):
    sprites = {
        "normal":  (normal_cat_r,  normal_cat_l),
        "sleepy":  (sleepy_cat_r,  sleepy_cat_l),
        "hover":   (hover_cat_r,   hover_cat_l),
        "pressed": (pressed_cat_r, pressed_cat_l),
        "looking": (looking_cat_r, looking_cat_l),
        "pet":     (pet_cat_r,     pet_cat_l),
    }
    r, l = sprites.get(state, sprites["normal"])
    return r if facing_right else l

# ---------------------------------------------------------------------------
# Root window
# ---------------------------------------------------------------------------
root = tk.Tk()
root.title("")
root.geometry("200x148")
root.attributes("-topmost", True)
root.resizable(False, False)
root.configure(bg="#202020")

CAT_W   = 200
CAT_H   = 148
PANEL_H = 240

screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()

# ---------------------------------------------------------------------------
# Notification window
# ---------------------------------------------------------------------------
def show_notification(message):
    sound_meow()
    n = tk.Toplevel(root)
    n.title("")
    n.configure(bg="#202020")
    n.attributes("-topmost", True)
    n.resizable(False, False)
    try:
        n.iconbitmap(os.path.join(UTILS_DIR, "icon.ico"))
    except Exception:
        pass
    # Position top-right of screen
    n.update_idletasks()
    w, h = 280, 110
    n.geometry(f"{w}x{h}+{screen_w - w - 20}+{40}")

    tk.Label(n, text=message, bg="#202020", fg="white",
             font=("Arial", 11), wraplength=250, justify="center",
             padx=14, pady=14).pack(expand=True)
    tk.Button(n, text="Close", command=n.destroy,
              bg="white", fg="black", bd=0, font=("Arial", 10), padx=10,
              activebackground="#ddd", cursor="hand2").pack(pady=(0, 10))

# ---------------------------------------------------------------------------
# Styled dialog helpers
# ---------------------------------------------------------------------------
def _style_win(win):
    win.title("")
    win.configure(bg="#202020")
    win.attributes("-topmost", True)
    win.resizable(False, False)
    try:
        win.iconbitmap(os.path.join(UTILS_DIR, "icon.ico"))
    except Exception:
        pass

def neko_confirm(message):
    result = [False]
    d = tk.Toplevel(root)
    _style_win(d)
    d.grab_set()
    tk.Label(d, text=message, bg="#202020", fg="white",
             font=("Arial", 11), wraplength=220, justify="center",
             padx=14, pady=10).pack()
    r = tk.Frame(d, bg="#202020")
    r.pack(pady=(0, 10))
    def _yes():
        result[0] = True
        d.destroy()
    tk.Button(r, text="Yes", command=_yes,
              bg="white", fg="black", bd=0, font=("Arial", 11), padx=12,
              activebackground="#ddd", cursor="hand2").pack(side="left", padx=6)
    tk.Button(r, text="No", command=d.destroy,
              bg="#444", fg="white", bd=0, font=("Arial", 11), padx=10,
              activebackground="#666", cursor="hand2").pack(side="left", padx=6)
    d.wait_window()
    return result[0]

def neko_warn(message, parent=None):
    d = tk.Toplevel(parent or root)
    _style_win(d)
    d.grab_set()
    tk.Label(d, text=message, bg="#202020", fg="white",
             font=("Arial", 11), wraplength=220, justify="center",
             padx=14, pady=10).pack()
    tk.Button(d, text="OK", command=d.destroy,
              bg="white", fg="black", bd=0, font=("Arial", 11), padx=14,
              activebackground="#ddd", cursor="hand2").pack(pady=(0, 10))
    d.wait_window()

# ---------------------------------------------------------------------------
# Automation editor  (defined BEFORE build_panel)
# ---------------------------------------------------------------------------
TRIGGER_LABELS = {
    "neko_left_click":  "🖱  Left click",
    "neko_right_click": "🖱  Right click",
    "keybind":          "⌨  Keyboard shortcut",
    "app_opened":       "📂  Application opened",
    "app_closed":       "📂  Application closed",
    "time_of_day":      "🕐  Time of day (HH:MM)",
}
ACTION_LABELS = {
    "open_url":      "🌐  Open URL",
    "search_google":  "🔍  Search Google",
    "open_app":      "📂  Open application",
    "close_app":     "✖  Close app",
    "close_tab":     "🗙  Close browser tab",
    "set_volume":    "🔊  Set volume (0-100)",
    "run_shell":     "⚡  Run shell command",
    "wait":          "⏳  Wait X seconds",
    "notification":  "🔔  Show notification",
    "toggle_neko":   "🐱  Show/hide neko",
}
_d2a = {v: k for k, v in ACTION_LABELS.items()}

# Which triggers need a value field
TRIG_NEEDS_VALUE = {"keybind", "app_opened", "app_closed", "time_of_day"}
# Which actions need a value field (fullscreen_focused needs none)
ACTION_NO_VALUE  = {"toggle_neko"}
ACTION_NEEDS_APP = {"open_app", "close_app"}

def open_editor(edit_idx, on_done):
    existing = automations[edit_idx] if edit_idx is not None else None

    win = tk.Toplevel(root)
    _style_win(win)
    win.grab_set()

    pad = {"padx": 8, "pady": 3}

    def lbl(parent, txt):
        return tk.Label(parent, text=txt, bg="#202020", fg="#666",
                        font=("Arial", 9), anchor="w")

    def ent(parent, default="", width=28):
        e = tk.Entry(parent, font=("Arial", 11), width=width,
                     bg="#2B2B2B", fg="white",
                     insertbackground="white", bd=0, relief="flat",
                     highlightthickness=1, highlightcolor="#444",
                     highlightbackground="#333")
        e.insert(0, default)
        return e

    # ── Name ──────────────────────────────────────────────────────────────
    lbl(win, "NAME").pack(fill="x", **pad)
    name_ent = ent(win, existing["name"] if existing else "")
    name_ent.pack(fill="x", **pad)

    # ── WHEN — listbox + add row ──────────────────────────────────────────
    _d2t_local = {v: k for k, v in TRIGGER_LABELS.items()}

    # Rebuild initial trigger list from existing
    if existing:
        trig = existing["trigger"]
        if trig.get("type") == "multi":
            # Each type shares the same value (keybind/time/app value)
            ex_trig_list = [{"type": t, "value": trig.get("value", "")}
                            for t in trig.get("types", [])]
        else:
            ex_trig_list = [{"type": trig["type"], "value": trig.get("value", "")}]
    else:
        ex_trig_list = []
    triggers_data = list(ex_trig_list)

    lbl(win, "WHEN  (double-click to remove)").pack(fill="x", **pad)
    trigs_lb = tk.Listbox(win, height=2,
                          bg="#2B2B2B", fg="white", font=("Arial", 10),
                          selectbackground="#444", bd=0,
                          highlightthickness=0, activestyle="none")
    trigs_lb.pack(fill="x", padx=8, pady=2)

    def refresh_trigs():
        trigs_lb.delete(0, tk.END)
        for t in triggers_data:
            label = TRIGGER_LABELS.get(t["type"], t["type"])
            val   = f": {t['value']}" if t.get("value") else ""
            trigs_lb.insert(tk.END, f"  {label}{val}")

    refresh_trigs()
    trigs_lb.bind("<Double-Button-1>",
                  lambda e: (triggers_data.pop(trigs_lb.curselection()[0]),
                             refresh_trigs()) if trigs_lb.curselection() else None)

    trig_add_row = tk.Frame(win, bg="#202020")
    trig_add_row.pack(fill="x", padx=8, pady=(2, 4))

    trig_cb = ttk.Combobox(trig_add_row, values=list(TRIGGER_LABELS.values()),
                            state="readonly", width=18, font=("Arial", 10))
    trig_cb.set(list(TRIGGER_LABELS.values())[0])
    trig_cb.pack(side="left", padx=(0, 4))

    # Order: [value] [+] [folder]  — same as DO row
    trig_val_ent = ent(trig_add_row, "", width=12)

    def _trig_strip_path(event=None):
        key = _d2t_local.get(trig_cb.get(), "")
        if key in ("app_opened", "app_closed"):
            val = trig_val_ent.get()
            base = os.path.basename(val.strip().strip('"').strip("'"))
            if base != val:
                trig_val_ent.delete(0, tk.END)
                trig_val_ent.insert(0, base)

    trig_val_ent.bind("<<Paste>>", lambda e: trig_val_ent.after(10, _trig_strip_path))
    trig_val_ent.bind("<FocusOut>", lambda e: _trig_strip_path())

    def do_add_trig():
        key = _d2t_local.get(trig_cb.get(), "")
        if not key:
            return
        val = trig_val_ent.get().strip() if key in TRIG_NEEDS_VALUE else ""
        if key in TRIG_NEEDS_VALUE and not val:
            neko_warn(f"Enter a value for {TRIGGER_LABELS[key]}.", parent=win)
            return
        if any(t["type"] == key for t in triggers_data):
            neko_warn("That trigger is already added.", parent=win)
            return
        triggers_data.append({"type": key, "value": val})
        trig_val_ent.delete(0, tk.END)
        refresh_trigs()

    trig_add_btn = tk.Button(trig_add_row, text="＋", command=do_add_trig,
                             bg="#333", fg="white", bd=0, font=("Arial", 13), padx=6,
                             activebackground="#555", cursor="hand2")

    def browse_trig_app():
        fd = tk.Toplevel(win)
        _style_win(fd)
        fd.withdraw()
        path = filedialog.askopenfilename(
            parent=fd, title="",
            filetypes=[("Applications", "*.exe *.bat *.cmd"), ("All files", "*.*")])
        fd.destroy()
        if path:
            trig_val_ent.delete(0, tk.END)
            trig_val_ent.insert(0, os.path.basename(path))

    trig_browse_btn = tk.Button(trig_add_row, text="\U0001f4c1", bd=0,
                                bg="#202020", fg="#aaa", font=("Arial", 12),
                                activebackground="#333", cursor="hand2",
                                command=browse_trig_app)

    def record_keybind():
        """Listen for the next key combo pressed and fill it into the value field."""
        record_btn.config(text="...", state="disabled")
        trig_val_ent.delete(0, tk.END)

        def _on_combo():
            try:
                combo = keyboard.read_hotkey(suppress=False)
            except Exception:
                combo = ""
            def _apply():
                trig_val_ent.delete(0, tk.END)
                if combo:
                    trig_val_ent.insert(0, combo)
                record_btn.config(text="⏺ Record", state="normal")
            win.after(0, _apply)

        threading.Thread(target=_on_combo, daemon=True).start()

    record_btn = tk.Button(trig_add_row, text="⏺ Record", bd=0,
                           bg="#202020", fg="#aaa", font=("Arial", 10),
                           activebackground="#333", cursor="hand2",
                           command=record_keybind)

    def _on_trig_cb_change(event=None):
        trig_val_ent.pack_forget()
        trig_add_btn.pack_forget()
        trig_browse_btn.pack_forget()
        record_btn.pack_forget()
        key = _d2t_local.get(trig_cb.get(), "")
        if key in TRIG_NEEDS_VALUE:
            trig_val_ent.pack(side="left", padx=(0, 2))
        if key == "keybind":
            record_btn.pack(side="left", padx=(0, 2))
        trig_add_btn.pack(side="left", padx=(0, 2))
        if key in ("app_opened", "app_closed"):
            trig_browse_btn.pack(side="left")

    trig_cb.bind("<<ComboboxSelected>>", _on_trig_cb_change)
    _on_trig_cb_change()

    # ── DO — actions listbox ──────────────────────────────────────────────
    lbl(win, "DO  (double-click row to remove)").pack(fill="x", **pad)
    actions_data = list(existing["actions"]) if existing else []

    acts_lb = tk.Listbox(win, height=3,
                         bg="#2B2B2B", fg="white", font=("Arial", 10),
                         selectbackground="#444", bd=0,
                         highlightthickness=0, activestyle="none")
    acts_lb.pack(fill="x", padx=8, pady=2)

    def refresh_acts():
        acts_lb.delete(0, tk.END)
        for a in actions_data:
            label = ACTION_LABELS.get(a["type"], a["type"])
            val   = f": {a['value']}" if a.get("value") else ""
            acts_lb.insert(tk.END, f"  {label}{val}")

    refresh_acts()
    acts_lb.bind("<Double-Button-1>",
                 lambda e: (actions_data.pop(acts_lb.curselection()[0]),
                            refresh_acts()) if acts_lb.curselection() else None)

    act_add_row = tk.Frame(win, bg="#202020")
    act_add_row.pack(fill="x", padx=8, pady=(2, 6))

    act_cb = ttk.Combobox(act_add_row, values=list(ACTION_LABELS.values()),
                          state="readonly", width=18, font=("Arial", 10))
    act_cb.set(list(ACTION_LABELS.values())[0])
    act_cb.pack(side="left", padx=(0, 4))

    act_val_ent = ent(act_add_row, "", width=9)
    act_val_ent.pack(side="left")

    def _act_strip_path(event=None):
        """Strip full path to basename for close_app (matched against running processes)."""
        key = _d2a.get(act_cb.get(), act_cb.get())
        if key == "close_app":
            val = act_val_ent.get()
            base = os.path.basename(val.strip().strip('"').strip("'"))
            if base != val:
                act_val_ent.delete(0, tk.END)
                act_val_ent.insert(0, base)

    act_val_ent.bind("<<Paste>>", lambda e: act_val_ent.after(10, _act_strip_path))
    act_val_ent.bind("<FocusOut>", lambda e: _act_strip_path())

    # 📁 browse button — for open_app / try_close / kill
    def browse_app():
        fd = tk.Toplevel(win)
        _style_win(fd)
        fd.withdraw()
        path = filedialog.askopenfilename(
            parent=fd, title="",
            filetypes=[("Applications", "*.exe *.bat *.cmd *.lnk"),
                       ("All files", "*.*")])
        fd.destroy()
        if path:
            key = _d2a.get(act_cb.get(), act_cb.get())
            act_val_ent.delete(0, tk.END)
            act_val_ent.insert(0, os.path.basename(path) if key == "close_app" else path)

    browse_btn = tk.Button(act_add_row, text="📁", bd=0,
                           bg="#202020", fg="#aaa", font=("Arial", 12),
                           activebackground="#333", cursor="hand2",
                           command=browse_app)

    def _update_act_row(event=None):
        key = _d2a.get(act_cb.get(), act_cb.get())
        if key in ACTION_NO_VALUE:
            act_val_ent.delete(0, tk.END)
            act_val_ent.pack_forget()
            browse_btn.pack_forget()
        else:
            act_val_ent.pack(side="left")
            if key in ACTION_NEEDS_APP:
                browse_btn.pack(side="left", padx=2)
            else:
                browse_btn.pack_forget()

    act_cb.bind("<<ComboboxSelected>>", _update_act_row)
    _update_act_row()

    def do_add_act():
        key = _d2a.get(act_cb.get(), act_cb.get())
        if key in ACTION_NO_VALUE:
            actions_data.append({"type": key, "value": ""})
            refresh_acts()
            return
        val = act_val_ent.get().strip()
        if not val:
            neko_warn("Enter a value.", parent=win)
            return
        actions_data.append({"type": key, "value": val})
        act_val_ent.delete(0, tk.END)
        refresh_acts()

    tk.Button(act_add_row, text="＋", command=do_add_act,
              bg="#333", fg="white", bd=0, font=("Arial", 13), padx=6,
              activebackground="#555", cursor="hand2").pack(side="left", padx=4)

    # ── Save / Cancel ──────────────────────────────────────────────────────
    tk.Frame(win, bg="#333", height=1).pack(fill="x", padx=8, pady=6)
    bot_row = tk.Frame(win, bg="#202020")
    bot_row.pack(fill="x", padx=8, pady=(0, 8))

    def do_save():
        name = name_ent.get().strip()
        if not name:
            neko_warn("Enter a name.", parent=win)
            return
        if not triggers_data:
            neko_warn("Add at least one trigger.", parent=win)
            return
        types = [t["type"] for t in triggers_data]
        val   = next((t["value"] for t in triggers_data if t.get("value")), "")
        trigger = ({"type": types[0], "value": val}
                   if len(types) == 1
                   else {"type": "multi", "types": types, "value": val})
        auto = {"name": name, "trigger": trigger, "actions": list(actions_data)}
        if edit_idx is not None:
            automations[edit_idx] = auto
        else:
            automations.append(auto)
        save_automations(automations)
        register_keybind_triggers()
        win.destroy()
        on_done()

    tk.Button(bot_row, text="Save", command=do_save,
              bg="white", fg="black", bd=0, font=("Arial", 11), padx=14,
              activebackground="#ddd", cursor="hand2").pack(side="right", padx=2)
    tk.Button(bot_row, text="Cancel", command=win.destroy,
              bg="#444", fg="white", bd=0, font=("Arial", 11), padx=8,
              activebackground="#666", cursor="hand2").pack(side="right", padx=2)

    win.wait_window()


# ---------------------------------------------------------------------------
# Overlay modes: clipboard & calculator
# ---------------------------------------------------------------------------
_mode_open   = None   # None | "clip" | "calc"
_mode_frame  = None
_clip_refresh_id = None

MINI_CAT = "        |╲\n  <( 。˕˚)\n    / ˜    |\nヽ( りり "

def close_mode():
    global _mode_open, _mode_frame, _clip_refresh_id
    if _clip_refresh_id is not None:
        root.after_cancel(_clip_refresh_id)
        _clip_refresh_id = None
    _mode_open = None
    if _mode_frame:
        _mode_frame.destroy()
        _mode_frame = None
    btn.pack(pady=(5, 0))
    _bar.pack(fill="x", padx=6, pady=0)
    root.geometry(f"{CAT_W}x{CAT_H}")

def open_mode(mode):
    global _mode_open, _mode_frame
    if _mode_open == mode:
        close_mode()
        return
    # Collapse panel if open
    if panel_open:
        collapse_panel()
    # Close any existing mode first
    if _mode_open is not None:
        close_mode()

    _mode_open = mode
    btn.pack_forget()
    _bar.pack_forget()
    if mode == "clip":
        root.geometry("200x360")
    elif mode == "ms":
        root.geometry("200x290")
    elif mode == "stopwatch":
        root.geometry("200x340")
    else:
        root.geometry("200x320")

    _mode_frame = tk.Frame(root, bg="#202020")
    _mode_frame.pack(fill="both", expand=True)

    if mode == "clip":
        _build_clip_ui(_mode_frame)
    elif mode == "ms":
        _build_ms_ui(_mode_frame)
    elif mode == "stopwatch":
        _build_stopwatch_ui(_mode_frame)
    else:
        _build_calc_ui(_mode_frame)

def _mini_neko_exit(parent, sprite):
    """Small neko at top-left that closes the mode on click."""
    lbl = tk.Label(parent, text=sprite, bg="#202020", fg="white",
                   font=("Arial", 10), justify="left", cursor="hand2")
    lbl.bind("<Button-1>", lambda e: (sound_meow(), close_mode()))
    return lbl

def _build_clip_ui(frame):
    global _clip_refresh_id
    top = tk.Frame(frame, bg="#202020")
    top.pack(fill="x", padx=6, pady=(6, 2))
    _mini_neko_exit(top, MINI_CAT).pack(side="left")
    tk.Label(top, text="clipboard", bg="#202020", fg="#555",
             font=("Arial", 9)).pack(side="left", padx=6)

    container = tk.Frame(frame, bg="#202020")
    container.pack(fill="both", expand=True, padx=6, pady=4)

    _last_clip_snapshot = [None]

    def build_rows():
        for w in container.winfo_children():
            w.destroy()
        for item in reversed(clipboard_history):
            row = tk.Frame(container, bg="#2B2B2B", pady=3)
            row.pack(fill="x", padx=2, pady=2)
            tk.Button(row, text="📋", bd=0, bg="#2B2B2B", fg="white",
                      font=("Arial", 12), activebackground="#333",
                      cursor="hand2",
                      command=lambda t=item: (pyperclip.copy(t) if pyperclip else None)
                      ).pack(side="right", padx=2)
            preview = " ".join(item.splitlines())
            if len(preview) > 22:
                preview = preview[:22] + "..."
            tk.Label(row, text=preview, bg="#2B2B2B", fg="white",
                     font=("Arial", 13), anchor="w"
                     ).pack(side="left", fill="x", expand=True, padx=4)

    def refresh():
        global _clip_refresh_id
        if _mode_open != "clip":
            return
        snapshot = list(clipboard_history)
        if snapshot != _last_clip_snapshot[0]:
            _last_clip_snapshot[0] = snapshot
            build_rows()
        _clip_refresh_id = root.after(1000, refresh)

    build_rows()
    refresh()

# ---------------------------------------------------------------------------
# Calc history persistence
# ---------------------------------------------------------------------------
def load_calc_history():
    if os.path.exists(CALC_HIST_FILE):
        try:
            with open(CALC_HIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_calc_history(hist):
    os.makedirs(UTILS_DIR, exist_ok=True)
    with open(CALC_HIST_FILE, "w", encoding="utf-8") as f:
        json.dump(hist[-7:], f, ensure_ascii=False)

calc_history = load_calc_history()

# Unit conversion table: (label, from_unit, to_unit, factor_or_fn)
UNIT_CATS = {
    "Length": [
        ("km → mi",   lambda x: x * 0.621371),
        ("mi → km",   lambda x: x * 1.60934),
        ("m → ft",    lambda x: x * 3.28084),
        ("ft → m",    lambda x: x * 0.3048),
        ("cm → in",   lambda x: x * 0.393701),
        ("in → cm",   lambda x: x * 2.54),
    ],
    "Weight": [
        ("kg → lb",   lambda x: x * 2.20462),
        ("lb → kg",   lambda x: x * 0.453592),
        ("g → oz",    lambda x: x * 0.035274),
        ("oz → g",    lambda x: x * 28.3495),
    ],
    "Temp": [
        ("°C → °F",   lambda x: x * 9/5 + 32),
        ("°F → °C",   lambda x: (x - 32) * 5/9),
        ("°C → K",    lambda x: x + 273.15),
        ("K → °C",    lambda x: x - 273.15),
    ],
    "Speed": [
        ("km/h → mph", lambda x: x * 0.621371),
        ("mph → km/h", lambda x: x * 1.60934),
        ("m/s → km/h", lambda x: x * 3.6),
        ("km/h → m/s", lambda x: x / 3.6),
    ],
    "Area": [
        ("m² → ft²",  lambda x: x * 10.7639),
        ("ft² → m²",  lambda x: x * 0.092903),
        ("km² → mi²", lambda x: x * 0.386102),
        ("mi² → km²", lambda x: x * 2.58999),
    ],
    "Data": [
        ("MB → GB",   lambda x: x / 1024),
        ("GB → MB",   lambda x: x * 1024),
        ("GB → TB",   lambda x: x / 1024),
        ("TB → GB",   lambda x: x * 1024),
    ],
}

def _build_ms_ui(frame):
    import random as _rnd

    ROWS, COLS, MINES = 8, 8, 10  # 8x8 grid, 10 mines — classic beginner ratio

    # State: each cell = {"mine":bool, "revealed":bool, "flagged":bool, "adj":int}
    board   = [[None]*COLS for _ in range(ROWS)]
    cells   = [[None]*COLS for _ in range(ROWS)]  # tk Button refs
    game_over = [False]
    first_click = [True]

    # ── Header ────────────────────────────────────────────────────────────────
    top = tk.Frame(frame, bg="#202020")
    top.pack(fill="x", padx=6, pady=(4, 0))
    _mini_neko_exit(top, MINI_CAT).pack(side="left")
    mine_lbl = tk.Label(top, text="💣7", bg="#202020", fg="#aaa",
                        font=("Arial", 9))
    mine_lbl.pack(side="left", padx=(2,0))
    status_lbl = tk.Label(top, text="", bg="#202020", fg="#aaa",
                          font=("Arial", 9))
    status_lbl.pack(side="left", padx=2)
    restart_btn = tk.Button(top, text="🔄", command=lambda: new_game(),
                            bg="#202020", fg="#aaa", bd=0, font=("Arial", 11),
                            activebackground="#333", cursor="hand2")
    restart_btn.pack(side="right")

    grid_frame = tk.Frame(frame, bg="#202020")
    grid_frame.pack(padx=4, pady=4)

    def count_flags():
        return sum(board[r][c]["flagged"] for r in range(ROWS) for c in range(COLS))

    def update_mine_label():
        mine_lbl.config(text=f"💣 {MINES - count_flags()}")

    def _compute_adj():
        for r in range(ROWS):
            for c in range(COLS):
                if not board[r][c]["mine"]:
                    board[r][c]["adj"] = sum(
                        board[r+dr][c+dc]["mine"]
                        for dr in range(-1, 2) for dc in range(-1, 2)
                        if 0 <= r+dr < ROWS and 0 <= c+dc < COLS
                    )

    def _has_5050():
        """Detect obvious 50/50: two unrevealed cells share ALL their
        constraining numbered neighbours, meaning either could be the mine
        with no logical way to distinguish. We check for pairs of adjacent
        unrevealed non-mine cells that are the *only* unknown neighbours of
        every numbered cell that sees them."""
        for r in range(ROWS):
            for c in range(COLS):
                if board[r][c]["mine"] or board[r][c]["adj"] == 0:
                    continue
                adj_val = board[r][c]["adj"]
                # Unrevealed neighbours of this numbered cell
                unknowns = [(r+dr, c+dc)
                            for dr in range(-1, 2) for dc in range(-1, 2)
                            if (dr, dc) != (0, 0)
                            and 0 <= r+dr < ROWS and 0 <= c+dc < COLS
                            and board[r+dr][c+dc]["mine"] is False
                            and board[r+dr][c+dc]["adj"] >= 0]
                mines_here = [(r+dr, c+dc)
                              for dr in range(-1, 2) for dc in range(-1, 2)
                              if (dr, dc) != (0, 0)
                              and 0 <= r+dr < ROWS and 0 <= c+dc < COLS
                              and board[r+dr][c+dc]["mine"]]
                remaining = adj_val - len(mines_here)
                non_mine_unknowns = [
                    (nr, nc) for nr, nc in unknowns
                    if not board[nr][nc]["mine"]
                ]
                # If exactly 2 unknown non-mine neighbours and 1 mine remaining
                # and those 2 share identical constraint sets → 50/50
                if remaining == 1 and len(non_mine_unknowns) == 2:
                    (r1,c1), (r2,c2) = non_mine_unknowns
                    # Check they share the same set of constraining cells
                    def constraints(tr, tc):
                        return frozenset(
                            (r+dr, c+dc)
                            for dr in range(-1,2) for dc in range(-1,2)
                            if (dr,dc)!=(0,0)
                            and 0<=r+dr<ROWS and 0<=c+dc<COLS
                            and board[r+dr][c+dc]["adj"] > 0
                            and not board[r+dr][c+dc]["mine"]
                        )
                    if constraints(r1,c1) == constraints(r2,c2):
                        return True
        return False

    def init_board(safe_r, safe_c):
        """Place mines after first click, retry up to 20 times to avoid 50/50s."""
        safe = {(safe_r+dr, safe_c+dc)
                for dr in range(-1, 2) for dc in range(-1, 2)}
        candidates = [(r, c) for r in range(ROWS) for c in range(COLS)
                      if (r, c) not in safe]
        for _attempt in range(20):
            # Reset board
            for r in range(ROWS):
                for c in range(COLS):
                    board[r][c] = {"mine": False, "revealed": False,
                                   "flagged": False, "adj": 0}
            for r, c in _rnd.sample(candidates, min(MINES, len(candidates))):
                board[r][c]["mine"] = True
            _compute_adj()
            if not _has_5050():
                break
        # Use last attempt regardless — best effort

    ADJ_COLORS = ["", "#2196F3", "#4CAF50", "#f44336",
                  "#9C27B0", "#FF5722", "#00BCD4", "#2196F3", "#666"]

    def render_cell(r, c):
        cell = board[r][c]
        btn  = cells[r][c]
        if cell["revealed"]:
            if cell["mine"]:
                btn.config(text="💣", bg="#cc3333", fg="white",
                           font=("Arial", 8), relief="sunken")
            elif cell["adj"] > 0:
                btn.config(text=str(cell["adj"]),
                           fg=ADJ_COLORS[cell["adj"]],
                           bg="#2B2B2B", font=("Arial", 9, "bold"),
                           relief="sunken")
            else:
                btn.config(text="", bg="#333", relief="sunken")
        elif cell["flagged"]:
            btn.config(text="🚩", fg = "white", bg="#202020", relief="raised",
                       font=("Arial", 8))
        else:
            btn.config(text="", bg="#3a3a3a", relief="raised", font=("Arial", 9))

    def reveal(r, c):
        cell = board[r][c]
        if cell["revealed"] or cell["flagged"]:
            return
        cell["revealed"] = True
        render_cell(r, c)
        if cell["adj"] == 0 and not cell["mine"]:
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < ROWS and 0 <= nc < COLS:
                        reveal(nr, nc)

    def check_win():
        for r in range(ROWS):
            for c in range(COLS):
                if not board[r][c]["mine"] and not board[r][c]["revealed"]:
                    return False
        return True

    def on_left(r, c):
        if game_over[0]:
            return
        if board[r][c]["flagged"]:
            return
        if first_click[0]:
            first_click[0] = False
            init_board(r, c)
            render_all()
        if board[r][c]["mine"]:
            board[r][c]["revealed"] = True
            render_cell(r, c)
            game_over[0] = True
            # Reveal all mines
            for rr in range(ROWS):
                for cc in range(COLS):
                    if board[rr][cc]["mine"]:
                        board[rr][cc]["revealed"] = True
                        render_cell(rr, cc)
            status_lbl.config(text="BOOM 💥", fg="#cc3333")
            sound_meow()
        else:
            reveal(r, c)
            if check_win():
                game_over[0] = True
                status_lbl.config(text="NICE 🎉", fg="#4CAF50")
                sound_meow()

    def on_right(r, c):
        if game_over[0] or board[r][c]["revealed"]:
            return
        board[r][c]["flagged"] = not board[r][c]["flagged"]
        render_cell(r, c)
        update_mine_label()

    def render_all():
        for r in range(ROWS):
            for c in range(COLS):
                render_cell(r, c)

    def new_game():
        game_over[0]   = False
        first_click[0] = True
        # Reset board state
        for r in range(ROWS):
            for c in range(COLS):
                board[r][c] = {"mine": False, "revealed": False,
                               "flagged": False, "adj": 0}
        render_all()
        status_lbl.config(text="")
        mine_lbl.config(text=f"💣 {MINES}")
        update_mine_label()

    # ── Build grid buttons ────────────────────────────────────────────────────
    for r in range(ROWS):
        for c in range(COLS):
            b = tk.Button(grid_frame, text="", width=2, height=1,
                          bg="#3a3a3a", fg="white", bd=1,
                          font=("Arial", 9, "bold"), relief="raised",
                          cursor="hand2", activebackground="#555")
            b.grid(row=r, column=c, padx=1, pady=1)
            b.bind("<Button-1>", lambda e, r=r, c=c: on_left(r, c))
            b.bind("<Button-3>", lambda e, r=r, c=c: on_right(r, c))
            cells[r][c] = b



    new_game()

def _build_calc_ui(frame):
    # ── Sub-page state: "calc" | "history" | "convert" ──
    page = ["calc"]
    pages = {}

    top = tk.Frame(frame, bg="#202020")
    top.pack(fill="x", padx=6, pady=(6, 2))
    _mini_neko_exit(top, MINI_CAT).pack(side="left")

    # Nav buttons top-right
    nav = tk.Frame(top, bg="#202020")
    nav.pack(side="right")

    def _nav_btn(parent, txt, cmd):
        return tk.Button(parent, text=txt, command=cmd,
                         bg="#333", fg="white", bd=0, font=("Arial", 8, "bold"),
                         activebackground="#555", cursor="hand2", padx=4, pady=1)

    content = tk.Frame(frame, bg="#202020")
    content.pack(fill="both", expand=True)

    def show_page(name):
        page[0] = name
        for p in pages.values():
            p.pack_forget()
        pages[name].pack(fill="both", expand=True)

    # ── CALC PAGE ─────────────────────────────────────────────────────────────
    calc_page = tk.Frame(content, bg="#202020")
    pages["calc"] = calc_page

    disp_var = tk.StringVar(value="0")
    disp = tk.Entry(calc_page, textvariable=disp_var,
                    font=("Arial", 20, "bold"), bg="#2B2B2B", fg="white",
                    insertbackground="white", bd=0, justify="right",
                    highlightthickness=0)
    disp.pack(fill="x", padx=8, pady=(4, 2), ipady=8)
    disp.focus_set()

    expr = [""]

    def _sync_from_entry(event=None):
        expr[0] = disp_var.get()

    disp.bind("<KeyRelease>", _sync_from_entry)
    disp.bind("<Return>", lambda e: press("="))

    def copy_result():
        val = disp_var.get()
        if pyperclip:
            pyperclip.copy(val)
        sound_meow()

    meta_row = tk.Frame(calc_page, bg="#202020")
    meta_row.pack(fill="x", padx=8, pady=(0, 2))
    tk.Button(meta_row, text="copy", command=copy_result,
              bg="#333", fg="#aaa", bd=0, font=("Arial", 8),
              activebackground="#444", cursor="hand2").pack(side="right")

    def press(val):
        cur = expr[0]
        if val == "C":
            expr[0] = ""
            disp_var.set("0")
            return
        if val == "⌫":
            expr[0] = cur[:-1]
            disp_var.set(expr[0] if expr[0] else "0")
            return
        if val == "=":
            raw_expr = expr[0]
            try:
                import math as _m
                result = eval(
                    raw_expr
                    .replace("^", "**")
                    .replace("√(", "_m.sqrt(")
                    .replace("√", "_m.sqrt"),
                    {"__builtins__": {}, "_m": _m, "pi": _m.pi, "e": _m.e}
                )
                if isinstance(result, float) and result == int(result):
                    result = int(result)
                result_str = str(result)
                # Save to history
                entry = f"{raw_expr} = {result_str}"
                calc_history.append(entry)
                if len(calc_history) > 7:
                    calc_history[:] = calc_history[-7:]
                save_calc_history(calc_history)
                expr[0] = result_str
                disp_var.set(result_str)
            except Exception:
                disp_var.set("error")
                expr[0] = ""
            return
        if val == "±":
            if expr[0].startswith("-"):
                expr[0] = expr[0][1:]
            elif expr[0]:
                expr[0] = "-" + expr[0]
            disp_var.set(expr[0] if expr[0] else "0")
            return
        if val == "%":
            try:
                expr[0] = str(eval(expr[0]) / 100)
                disp_var.set(expr[0])
            except Exception:
                pass
            return
        expr[0] = cur + val
        disp_var.set(expr[0])
        disp.icursor(tk.END)

    btn_frame = tk.Frame(calc_page, bg="#202020")
    btn_frame.pack(fill="both", expand=True, padx=6, pady=2)

    BUTTONS = [
        ["C",   "±",  "%",   "÷" ],
        ["7",   "8",  "9",   "×" ],
        ["4",   "5",  "6",   "−" ],
        ["1",   "2",  "3",   "+" ],
        [".",   "0",  "⌫",   "=" ],
        ["√",  "x²", "(",   ")" ],
    ]
    OP_MAP = {"÷": "/", "×": "*", "−": "-", "+": "+", "x²": "**2"}

    for r, row_btns in enumerate(BUTTONS):
        btn_frame.rowconfigure(r, weight=1)
        for c, label in enumerate(row_btns):
            btn_frame.columnconfigure(c, weight=1)
            is_eq  = (label == "=")
            is_op  = label in OP_MAP or label in ("C", "±", "%", "√", "⌫", "(", ")")
            bg  = "white"  if is_eq else ("#333" if is_op else "#2B2B2B")
            fg  = "black"  if is_eq else "white"
            abg = "#ddd"   if is_eq else "#444"
            raw = OP_MAP.get(label, label)
            tk.Button(btn_frame, text=label, command=lambda v=raw: press(v),
                      bg=bg, fg=fg, bd=0, font=("Arial", 12, "bold"),
                      activebackground=abg, cursor="hand2", relief="flat"
                      ).grid(row=r, column=c, sticky="nsew", padx=2, pady=2)

    # ── HISTORY PAGE ──────────────────────────────────────────────────────────
    hist_page = tk.Frame(content, bg="#202020")
    pages["history"] = hist_page

    tk.Label(hist_page, text="history", bg="#202020", fg="#555",
             font=("Arial", 9)).pack(anchor="w", padx=8, pady=(4, 2))

    hist_container = tk.Frame(hist_page, bg="#202020")
    hist_container.pack(fill="both", expand=True, padx=6)

    def refresh_hist():
        for w in hist_container.winfo_children():
            w.destroy()
        if not calc_history:
            tk.Label(hist_container, text="no history yet", bg="#202020",
                     fg="#555", font=("Arial", 10)).pack(pady=10)
            return
        for entry in reversed(calc_history):
            row = tk.Frame(hist_container, bg="#2B2B2B", pady=3)
            row.pack(fill="x", padx=2, pady=2)
            tk.Button(row, text="📋", bd=0, bg="#2B2B2B", fg="white",
                      font=("Arial", 11), activebackground="#333", cursor="hand2",
                      command=lambda v=entry.split(" = ")[-1]: (
                          pyperclip.copy(v) if pyperclip else None)
                      ).pack(side="right", padx=2)
            preview = entry if len(entry) <= 24 else entry[:24] + "..."
            tk.Label(row, text=preview, bg="#2B2B2B", fg="white",
                     font=("Arial", 10), anchor="w"
                     ).pack(side="left", fill="x", expand=True, padx=4)

    def show_hist():
        refresh_hist()
        show_page("history")

    # ── CONVERT PAGE ──────────────────────────────────────────────────────────
    conv_page = tk.Frame(content, bg="#202020")
    pages["convert"] = conv_page

    tk.Label(conv_page, text="unit converter", bg="#202020", fg="#555",
             font=("Arial", 9)).pack(anchor="w", padx=8, pady=(4, 2))

    conv_cat_var  = tk.StringVar(value=list(UNIT_CATS.keys())[0])
    conv_conv_var = tk.StringVar()
    conv_in_var   = tk.StringVar()
    conv_out_var  = tk.StringVar(value="—")

    cat_row = tk.Frame(conv_page, bg="#202020")
    cat_row.pack(fill="x", padx=8, pady=2)

    cat_cb = ttk.Combobox(cat_row, textvariable=conv_cat_var,
                          values=list(UNIT_CATS.keys()),
                          state="readonly", width=10, font=("Arial", 10))
    cat_cb.pack(side="left", padx=(0, 4))

    conv_cb = ttk.Combobox(cat_row, textvariable=conv_conv_var,
                           state="readonly", width=11, font=("Arial", 10))
    conv_cb.pack(side="left")

    in_row = tk.Frame(conv_page, bg="#202020")
    in_row.pack(fill="x", padx=8, pady=4)

    conv_entry = tk.Entry(in_row, textvariable=conv_in_var,
                          font=("Arial", 16, "bold"), bg="#2B2B2B", fg="white",
                          insertbackground="white", bd=0, justify="right",
                          highlightthickness=0, width=10)
    conv_entry.pack(fill="x", ipady=6)

    conv_result_lbl = tk.Label(conv_page, textvariable=conv_out_var,
                               bg="#202020", fg="white",
                               font=("Arial", 18, "bold"), anchor="e")
    conv_result_lbl.pack(fill="x", padx=10, pady=2)

    def _do_convert(event=None):
        cat   = conv_cat_var.get()
        label = conv_conv_var.get()
        fn    = next((c[1] for c in UNIT_CATS[cat] if c[0] == label), None)
        if fn is None:
            conv_out_var.set("—")
            return
        try:
            val    = float(conv_in_var.get())
            result = fn(val)
            if isinstance(result, float) and result == int(result):
                result = int(result)
            to_unit = label.split("→")[-1].strip()
            conv_out_var.set(f"{result} {to_unit}")
        except Exception:
            conv_out_var.set("—")

    def _update_conv_list(event=None):
        cat = conv_cat_var.get()
        labels = [c[0] for c in UNIT_CATS[cat]]
        conv_cb["values"] = labels
        conv_conv_var.set(labels[0])
        _do_convert()

    cat_cb.bind("<<ComboboxSelected>>", _update_conv_list)
    conv_cb.bind("<<ComboboxSelected>>", lambda e: _do_convert())
    conv_entry.bind("<KeyRelease>", lambda e: _do_convert())
    _update_conv_list()

    def copy_conv():
        val = conv_out_var.get()
        if val == "—":
            return
        if pyperclip:
            pyperclip.copy(val)
        sound_meow()
        # Save to shared history: "label: input → result"
        label = conv_conv_var.get()
        raw   = conv_in_var.get().strip()
        entry = f"{label}: {raw} → {val}"
        calc_history.append(entry)
        if len(calc_history) > 7:
            calc_history[:] = calc_history[-7:]
        save_calc_history(calc_history)

    tk.Button(conv_page, text="copy", command=copy_conv,
              bg="#333", fg="#aaa", bd=0, font=("Arial", 8),
              activebackground="#444", cursor="hand2"
              ).pack(anchor="e", padx=10, pady=2)

    # ── Wire up nav buttons ───────────────────────────────────────────────────
    _nav_btn(nav, "H", show_hist).pack(side="left", padx=1)
    _nav_btn(nav, "↔", lambda: show_page("convert")).pack(side="left", padx=1)
    _nav_btn(nav, "✕", lambda: show_page("calc")).pack(side="left", padx=1)

    show_page("calc")

# ---------------------------------------------------------------------------
# Stopwatch / Timer tool
# ---------------------------------------------------------------------------
active_timers   = []      # running/paused countdown timers: {"id","label","total","remaining","running"}
_timer_id_ctr   = [0]
_sw_refresh_cb  = [None]  # set while the stopwatch mode UI is open
sw_state        = {"running": False, "elapsed": 0}  # the plain count-up stopwatch

def _play_meow_burst(times=3, gap_ms=650):
    """Plays the finished-timer alarm as separated meows: 'meow! ... meow! ... meow!'"""
    def _step(i):
        if i >= times:
            return
        sound_meow()
        root.after(gap_ms, lambda: _step(i + 1))
    _step(0)

def _timers_tick():
    finished = []
    for t in list(active_timers):
        if t["running"]:
            t["remaining"] -= 1
            if t["remaining"] <= 0:
                t["remaining"] = 0
                finished.append(t)
    for t in finished:
        if t in active_timers:
            active_timers.remove(t)
        _play_meow_burst()
    if sw_state["running"]:
        sw_state["elapsed"] += 1
    if _sw_refresh_cb[0] is not None:
        try:
            _sw_refresh_cb[0]()
        except Exception:
            _sw_refresh_cb[0] = None
    root.after(1000, _timers_tick)

root.after(1000, _timers_tick)

def _fmt_timer(secs):
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def _build_stopwatch_ui(frame):
    tab = ["timer"]
    tabs = {}

    top = tk.Frame(frame, bg="#202020")
    top.pack(fill="x", padx=6, pady=(6, 2))
    _mini_neko_exit(top, MINI_CAT).pack(side="left")

    tabbar = tk.Frame(top, bg="#202020")
    tabbar.pack(side="right")

    def _tab_btn(parent, txt, cmd):
        return tk.Button(parent, text=txt, command=cmd,
                         bg="#333", fg="white", bd=0, font=("Arial", 8, "bold"),
                         activebackground="#555", cursor="hand2", padx=4, pady=1)

    content = tk.Frame(frame, bg="#202020")
    content.pack(fill="both", expand=True)

    def show_tab(name):
        tab[0] = name
        for t in tabs.values():
            t.pack_forget()
        tabs[name].pack(fill="both", expand=True)

    # ── TIMER TAB — running countdown timers, Apple-Timer style ─────────────
    timer_tab = tk.Frame(content, bg="#202020")
    tabs["timer"] = timer_tab

    add_row = tk.Frame(timer_tab, bg="#202020")
    add_row.pack(fill="x", padx=8, pady=(6, 2))

    def _mk_time_row(parent, label_text):
        row = tk.Frame(parent, bg="#202020")
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label_text, bg="#202020", fg="#666",
                 font=("Arial", 8)).pack(side="left")
        ent = tk.Entry(row, width=4, font=("Arial", 10), bg="#2B2B2B", fg="white",
                       insertbackground="white", bd=0, justify="center",
                       highlightthickness=0)
        ent.pack(side="right", ipady=2)
        return ent

    h_ent = _mk_time_row(add_row, "hours")
    m_ent = _mk_time_row(add_row, "minutes")
    s_ent = _mk_time_row(add_row, "seconds")

    def _parse_field(entry):
        v = entry.get().strip()
        if not v:
            return 0
        try:
            return max(0, int(float(v)))
        except Exception:
            return 0

    def add_timer():
        secs = _parse_field(h_ent) * 3600 + _parse_field(m_ent) * 60 + _parse_field(s_ent)
        if secs <= 0:
            return
        _timer_id_ctr[0] += 1
        active_timers.append({"id": _timer_id_ctr[0], "label": f"Timer {_timer_id_ctr[0]}",
                              "total": secs, "remaining": secs, "running": True})
        sound_meow()
        refresh_timers()

    start_row = tk.Frame(timer_tab, bg="#202020")
    start_row.pack(fill="x", padx=8, pady=(2, 4))

    tk.Button(start_row, text="start timer", command=add_timer,
              bg="white", fg="black", bd=0, font=("Arial", 9, "bold"),
              activebackground="#ddd", cursor="hand2", pady=3
              ).pack(fill="x")

    list_container = tk.Frame(timer_tab, bg="#202020")
    list_container.pack(fill="both", expand=True, padx=6, pady=(2, 4))

    def toggle_running(t):
        t["running"] = not t["running"]
        refresh_timers()

    def delete_timer(t):
        if t in active_timers:
            active_timers.remove(t)
        refresh_timers()

    def refresh_timers():
        for w in list_container.winfo_children():
            w.destroy()
        if not active_timers:
            tk.Label(list_container, text="no timers running", bg="#202020",
                     fg="#555", font=("Arial", 9)).pack(pady=10)
            return
        for t in active_timers:
            row = tk.Frame(list_container, bg="#2B2B2B", pady=3)
            row.pack(fill="x", padx=2, pady=2)
            tk.Button(row, text="✕", command=lambda t=t: delete_timer(t),
                      bd=0, bg="#2B2B2B", fg="#aaa", font=("Arial", 9),
                      activebackground="#333", cursor="hand2").pack(side="right", padx=2)
            tk.Button(row, text=("⏸" if t["running"] else "▶"),
                      command=lambda t=t: toggle_running(t),
                      bd=0, bg="#2B2B2B", fg="white", font=("Arial", 9),
                      activebackground="#333", cursor="hand2").pack(side="right", padx=2)
            tk.Label(row, text=_fmt_timer(t["remaining"]), bg="#2B2B2B", fg="white",
                     font=("Arial", 11, "bold"), anchor="w"
                     ).pack(side="left", fill="x", expand=True, padx=4)

    # ── STOPWATCH TAB — plain count-up stopwatch ─────────────────────────────
    sw_tab = tk.Frame(content, bg="#202020")
    tabs["stopwatch"] = sw_tab

    sw_disp = tk.Label(sw_tab, text=_fmt_timer(sw_state["elapsed"]),
                       bg="#202020", fg="white", font=("Arial", 26, "bold"))
    sw_disp.pack(pady=(20, 10))

    sw_btn_row = tk.Frame(sw_tab, bg="#202020")
    sw_btn_row.pack(pady=4)

    def sw_toggle():
        sw_state["running"] = not sw_state["running"]
        sw_start_btn.config(text=("pause" if sw_state["running"] else "start"))

    def sw_reset():
        sw_state["running"] = False
        sw_state["elapsed"] = 0
        sw_start_btn.config(text="start")
        sw_disp.config(text=_fmt_timer(0))

    sw_start_btn = tk.Button(sw_btn_row, text=("pause" if sw_state["running"] else "start"),
                             command=sw_toggle,
                             bg="white", fg="black", bd=0, font=("Arial", 10, "bold"),
                             activebackground="#ddd", cursor="hand2", padx=10, pady=3)
    sw_start_btn.pack(side="left", padx=4)

    tk.Button(sw_btn_row, text="reset", command=sw_reset,
              bg="#333", fg="#aaa", bd=0, font=("Arial", 10),
              activebackground="#444", cursor="hand2", padx=10, pady=3
              ).pack(side="left", padx=4)

    # ── Wire up tab buttons ──────────────────────────────────────────────────
    _tab_btn(tabbar, "⏳", lambda: show_tab("timer")).pack(side="left", padx=1)
    _tab_btn(tabbar, "⏱", lambda: show_tab("stopwatch")).pack(side="left", padx=1)

    def _refresh_cb():
        refresh_timers()
        sw_disp.config(text=_fmt_timer(sw_state["elapsed"]))

    _sw_refresh_cb[0] = _refresh_cb

    refresh_timers()
    show_tab("timer")

# ---------------------------------------------------------------------------
# Notepad tool (separate popup window, like the automation editor)
# ---------------------------------------------------------------------------
_notepad_win = [None]

def open_notepad():
    if _notepad_win[0] is not None:
        try:
            if _notepad_win[0].winfo_exists():
                _notepad_win[0].deiconify()
                _notepad_win[0].lift()
                _notepad_win[0].focus_force()
                return
        except Exception:
            pass

    win = tk.Toplevel(root)
    _style_win(win)
    size = 240
    win.geometry(f"{size}x{size}")
    _notepad_win[0] = win

    def _on_close():
        _notepad_win[0] = None
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", _on_close)

    top = tk.Frame(win, bg="#202020")
    top.pack(fill="x", padx=6, pady=(6, 2))
    tk.Label(top, text="notepad", bg="#202020", fg="#555",
             font=("Arial", 9)).pack(side="left")

    text = tk.Text(win, bg="#101010", fg="white", insertbackground="white",
                   bd=0, highlightthickness=0, font=("Arial", 11), wrap="word",
                   padx=6, pady=4)
    text.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    tk.Button(top, text="clear", command=lambda: text.delete("1.0", tk.END),
              bg="#333", fg="#aaa", bd=0, font=("Arial", 8),
              activebackground="#444", cursor="hand2").pack(side="right")

    text.focus_set()

# ---------------------------------------------------------------------------
# Hold-to-pick popup
# ---------------------------------------------------------------------------
HOLD_MS = 500

def show_click_picker(autos, trigger_type):
    """Show selection popup when multiple automations share the same click trigger."""
    popup = tk.Toplevel(root)
    popup.overrideredirect(True)
    popup.attributes("-topmost", True)
    popup.configure(bg="#1a1a1a")
    popup.geometry(f"+{root.winfo_x()}+{root.winfo_y() + root.winfo_height()}")

    tk.Label(popup, text="  choose automation",
             bg="#1a1a1a", fg="#555", font=("Arial", 9),
             anchor="w").pack(fill="x", padx=6, pady=(6, 2))

    for auto in autos:
        row = tk.Frame(popup, bg="#1a1a1a")
        row.pack(fill="x", padx=6, pady=1)

        def _pick(a=auto):
            popup.destroy()
            run_automation(a, trigger_type)

        tk.Button(row, text=auto["name"], bg="#1a1a1a", fg="white", bd=0,
                  font=("Arial", 11), anchor="w",
                  activebackground="#2a2a2a", cursor="hand2",
                  command=_pick).pack(side="left", fill="x", expand=True)

    popup.bind("<FocusOut>", lambda e: popup.destroy())
    popup.focus_force()

def show_neko_picker():
    neko_autos = [a for a in automations
                  if any(t in ("neko_left_click", "neko_right_click")
                         for t in get_trigger_types(a))]
    if not neko_autos:
        return

    popup = tk.Toplevel(root)
    popup.overrideredirect(True)
    popup.attributes("-topmost", True)
    popup.configure(bg="#1a1a1a")
    popup.geometry(f"+{root.winfo_x()}+{root.winfo_y() + root.winfo_height()}")

    tk.Label(popup, text="  choose automation",
             bg="#1a1a1a", fg="#555", font=("Arial", 9),
             anchor="w").pack(fill="x", padx=6, pady=(6, 2))

    for auto in neko_autos:
        types = get_trigger_types(auto)
        if "neko_left_click" in types and "neko_right_click" in types:
            badge, badge_bg = "LR", "#555"
        elif "neko_left_click" in types:
            badge, badge_bg = "L",  "#444"
        else:
            badge, badge_bg = "R",  "#444"

        row = tk.Frame(popup, bg="#1a1a1a")
        row.pack(fill="x", padx=6, pady=1)
        tk.Label(row, text=badge, bg=badge_bg, fg="white",
                 font=("Arial", 8, "bold"), width=2).pack(side="left", padx=(0, 5))

        def _pick(a=auto):
            popup.destroy()
            sound_meow()
            run_automation(a, "neko_hold_pick")

        tk.Button(row, text=auto["name"], bg="#1a1a1a", fg="white", bd=0,
                  font=("Arial", 11), anchor="w",
                  activebackground="#2a2a2a", cursor="hand2",
                  command=_pick).pack(side="left", fill="x", expand=True)

    popup.bind("<FocusOut>", lambda e: popup.destroy())
    popup.focus_force()

# ---------------------------------------------------------------------------
# Panel expand / collapse
# ---------------------------------------------------------------------------
panel_open  = False
panel_frame = None

def toggle_panel():
    global panel_open
    collapse_panel() if panel_open else expand_panel()

def collapse_panel():
    global panel_open, panel_frame
    panel_open = False
    if panel_frame:
        panel_frame.pack_forget()
    root.geometry(f"{CAT_W}x{CAT_H}")
    arrow_btn.config(text="▼")

def expand_panel():
    global panel_open
    panel_open = True
    root.geometry(f"{CAT_W}x{CAT_H + PANEL_H}")
    arrow_btn.config(text="▲")
    build_panel()

# ---------------------------------------------------------------------------
# Panel UI
# ---------------------------------------------------------------------------
# Badge: white square, grey letter — no colors
def get_badge(auto):
    types = get_trigger_types(auto)
    LETTERS = {
        "neko_left_click":  "L",
        "neko_right_click": "R",
        "keybind":          "K",
        "time_of_day":      "T",
        "app_opened":       "A",
        "app_closed":       "C",
    }
    if len(types) > 1:
        return "M"
    return LETTERS.get(types[0], "?") if types else "?"

def build_panel():
    global panel_frame
    if panel_frame:
        panel_frame.destroy()

    panel_frame = tk.Frame(root, bg="#202020")
    panel_frame.pack(fill="both", expand=True)

    bot = tk.Frame(panel_frame, bg="#202020")
    bot.pack(side="bottom", fill="x", padx=6, pady=4)

    canvas = tk.Canvas(panel_frame, bg="#202020", bd=0, highlightthickness=0)
    sb = tk.Scrollbar(panel_frame, orient="vertical",
                      command=canvas.yview, bg="#202020")
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    rows_frame = tk.Frame(canvas, bg="#202020")
    cwin = canvas.create_window((0, 0), window=rows_frame, anchor="nw")

    def _resize(e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(cwin, width=canvas.winfo_width())

    rows_frame.bind("<Configure>", _resize)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(cwin, width=e.width))
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def build_rows():
        for w in rows_frame.winfo_children():
            w.destroy()

        if not automations:
            tk.Label(rows_frame, text="  no automations yet",
                     bg="#202020", fg="#555",
                     font=("Arial", 10)).pack(anchor="w", padx=8, pady=8)
            return

        for i, auto in enumerate(automations):
            letter = get_badge(auto)
            row = tk.Frame(rows_frame, bg="#2B2B2B", pady=4)
            row.pack(fill="x", padx=4, pady=2)

            # Badge — white square, dark letter
            tk.Label(row, text=letter, bg="white", fg="#222",
                     font=("Arial", 8, "bold"), width=2,
                     ).pack(side="left", padx=(4, 0))

            # Name — truncated to 11 chars, fixed width
            raw  = auto["name"]
            disp = raw if len(raw) <= 11 else raw[:11] + "…"
            name_lbl = tk.Label(
                row, text=f"  {disp}",
                bg="#2B2B2B", fg="white",
                font=("Arial", 11), anchor="w", cursor="hand2", width=11,
            )
            name_lbl.pack(side="left")
            name_lbl.bind("<Button-1>",
                          lambda e, a=auto: (sound_meow(),
                                             run_automation(a, "manual")))

            # 🗑 delete — white
            def _del(idx=i):
                if neko_confirm(f'Delete "{automations[idx]["name"]}"?'):
                    automations.pop(idx)
                    save_automations(automations)
                    register_keybind_triggers()
                    build_rows()

            tk.Button(row, text="🗑", bd=0, bg="#2B2B2B", fg="white",
                      font=("Arial", 12), activebackground="#333",
                      cursor="hand2", command=_del,
                      ).pack(side="right", padx=(0, 3))

            # 📓 edit — white
            def _edit(idx=i):
                open_editor(idx, build_rows)

            tk.Button(row, text="📓", bd=0, bg="#2B2B2B", fg="white",
                      font=("Arial", 12), activebackground="#333",
                      cursor="hand2", command=_edit,
                      ).pack(side="right", padx=(0, 2))

    build_rows()

    tk.Button(bot, text="＋  New automation",
              command=lambda: open_editor(None, build_rows),
              bg="#2B2B2B", fg="white", bd=0, font=("Arial", 11), pady=4,
              activebackground="#3a3a3a", cursor="hand2",
              ).pack(fill="x")

# ---------------------------------------------------------------------------
# Cat button
# ---------------------------------------------------------------------------
_hold_timer = None
_hold_fired = False

def _cancel_hold():
    global _hold_timer
    if _hold_timer is not None:
        root.after_cancel(_hold_timer)
        _hold_timer = None

def on_cat_press_left(event=None):
    global _hold_timer, _hold_fired, last_interaction_time, mouse_tracking_enabled
    _wake()
    _hold_fired            = False
    mouse_tracking_enabled = False
    btn.config(text=get_cat_sprite("pressed"))

    def _held():
        global _hold_fired
        _hold_fired = True
        btn.config(text=get_cat_sprite("normal"))
        root.after(0, show_neko_picker)

    _hold_timer = root.after(HOLD_MS, _held)

def on_cat_release_left(event=None):
    global mouse_tracking_enabled
    mouse_tracking_enabled = True
    _cancel_hold()
    if _pet_after_id is None:
        btn.config(text=get_cat_sprite("normal"))
    if _hold_fired:
        return
    sound_meow()
    left_autos = [a for a in automations if "neko_left_click" in get_trigger_types(a)]
    if len(left_autos) > 1:
        show_click_picker(left_autos, "neko_left_click")
    elif left_autos:
        run_automation(left_autos[0], "neko_left_click")

def on_cat_press_right(event=None):
    global last_interaction_time
    _wake()
    sound_meow()
    btn.config(text=get_cat_sprite("pressed"))
    root.after(120, lambda: btn.config(text=get_cat_sprite("normal")))
    right_autos = [a for a in automations if "neko_right_click" in get_trigger_types(a)]
    if len(right_autos) > 1:
        show_click_picker(right_autos, "neko_right_click")
    elif right_autos:
        run_automation(right_autos[0], "neko_right_click")

def on_hover(event):
    if _pet_after_id is not None:
        return
    btn.config(text=get_cat_sprite("hover"))

def off_hover(event):
    global last_interaction_time
    _wake()
    if _pet_after_id is not None:
        return
    btn.config(text=get_cat_sprite("normal"))

btn = tk.Label(root, text=get_cat_sprite("normal"),
               font=("Arial", 14), bg="#202020", fg="white",
               width=7, height=5, cursor="hand2")
btn.pack(pady=(5, 0))
btn.bind("<ButtonPress-1>",   on_cat_press_left)
btn.bind("<ButtonRelease-1>", on_cat_release_left)
btn.bind("<Button-3>",        on_cat_press_right)
btn.bind("<Enter>",  on_hover)
btn.bind("<Leave>",  off_hover)

# Bottom bar: ▼ on left, 📋 🧮 on right
_bar = tk.Frame(root, bg="#202020")
_bar.pack(fill="x", padx=6, pady=0)

arrow_btn = tk.Button(_bar, text="▼", command=toggle_panel,
                      bg="#202020", fg="#555", bd=0, font=("Arial", 8),
                      activebackground="#202020", activeforeground="#aaa",
                      cursor="hand2", pady=0, padx=0)
arrow_btn.pack(side="left")

ms_btn = tk.Button(_bar, text="🚩", command=lambda: open_mode("ms"),
                   bg="#202020", fg="#aaa", bd=0, font=("Arial", 13, "bold"),
                   activebackground="#202020", cursor="hand2", pady=0, padx=2)
ms_btn.pack(side="right")

note_btn = tk.Button(_bar, text="🖊", command=lambda: open_notepad(),
                    bg="#202020", fg="#aaa", bd=0, font=("Arial", 13, "bold"),
                    activebackground="#202020", cursor="hand2", pady=0, padx=2)
note_btn.pack(side="right")

clock_btn = tk.Button(_bar, text="🕐", command=lambda: open_mode("stopwatch"),
                      bg="#202020", fg="#aaa", bd=0, font=("Arial", 13, "bold"),
                      activebackground="#202020", cursor="hand2", pady=0, padx=2)
clock_btn.pack(side="right")

calc_btn = tk.Button(_bar, text="÷", command=lambda: open_mode("calc"),
                     bg="#202020", fg="#aaa", bd=0, font=("Arial", 13, "bold"),
                     activebackground="#202020", cursor="hand2", pady=0, padx=2)
calc_btn.pack(side="right")

clip_btn = tk.Button(_bar, text="📋", command=lambda: open_mode("clip"),
                     bg="#202020", fg="#aaa", bd=0, font=("Arial", 13, "bold"),
                     activebackground="#202020", cursor="hand2", pady=0, padx=2)
clip_btn.pack(side="right")

# ---------------------------------------------------------------------------
# Drag with momentum
# ---------------------------------------------------------------------------
drag = {"active": False, "last_x": 0, "last_y": 0, "vx": 0, "vy": 0}
window_width  = CAT_W
window_height = CAT_H

def _over(event, widget):
    wx1, wy1 = widget.winfo_x(), widget.winfo_y()
    return wx1 <= event.x <= wx1+widget.winfo_width() and \
           wy1 <= event.y <= wy1+widget.winfo_height()

def start_drag(event):
    global mouse_tracking_enabled
    _wake()
    if _over(event, btn) or _over(event, arrow_btn) or _over(event, clip_btn) or _over(event, calc_btn) or _over(event, ms_btn) or _over(event, clock_btn) or _over(event, note_btn):
        return
    drag["active"] = True
    mouse_tracking_enabled = False
    drag["last_x"] = event.x_root
    drag["last_y"] = event.y_root
    drag["vx"] = drag["vy"] = 0

def during_drag(event):
    if not drag["active"]:
        return
    dx = event.x_root - drag["last_x"]
    dy = event.y_root - drag["last_y"]
    drag["vx"] = dx;  drag["vy"] = dy
    drag["last_x"] = event.x_root;  drag["last_y"] = event.y_root
    nx = max(0, min(screen_w - window_width,  root.winfo_x() + dx))
    ny = max(0, min(screen_h - window_height, root.winfo_y() + dy))
    root.geometry(f"+{nx}+{ny}")

def release_drag(event):
    global mouse_tracking_enabled
    if drag["active"]:
        drag["active"] = False
        move_window()
        mouse_tracking_enabled = True

def move_window():
    def step():
        nx = root.winfo_x() + drag["vx"]
        ny = root.winfo_y() + drag["vy"]
        if nx < 0:                          nx = 0;                         drag["vx"] = -drag["vx"]
        elif nx > screen_w - window_width:  nx = screen_w - window_width;  drag["vx"] = -drag["vx"]
        if ny < 0:                          ny = 0;                         drag["vy"] = -drag["vy"]
        elif ny > screen_h - window_height: ny = screen_h - window_height; drag["vy"] = -drag["vy"]
        root.geometry(f"+{int(nx)}+{int(ny)}")
        drag["vx"] *= 0.92;  drag["vy"] *= 0.92
        if abs(drag["vx"]) > 0.1 or abs(drag["vy"]) > 0.1:
            root.after(16, step)
    step()

root.bind("<Button-1>",        start_drag)
root.bind("<B1-Motion>",       during_drag)
root.bind("<ButtonRelease-1>", release_drag)

# ---------------------------------------------------------------------------
# Hop animation
# ---------------------------------------------------------------------------
def hop_animation():
    global hop_counter, hop_dx, hop_dy
    if _mouse_over_window:
        hop_counter = 0
        return
    if hop_counter == 0:
        hop_dx = random.choice([10, -10])
        hop_dy = random.choice([10, -10])
    hop_counter += 1
    x, y = root.winfo_x(), root.winfo_y()
    nx = max(0, min(screen_w-window_width,  x+hop_dx+random.randint(-2,2)))
    ny = max(0, min(screen_h-window_height, y+hop_dy+random.randint(-2,2)))
    root.geometry(f"+{nx}+{ny}")
    if hop_counter < 3:
        root.after(250, hop_animation)
    else:
        hop_counter = 0

# ---------------------------------------------------------------------------
# Pet sprite
# ---------------------------------------------------------------------------
def show_pet_sprite(mouse_x):
    """Show pet sprite facing toward mouse, meow, reset after 2.5s."""
    global facing_right, _pet_after_id
    # Face toward the mouse
    facing_right = mouse_x > root.winfo_x() + root.winfo_width() // 2
    root.after(0, lambda: btn.config(text=get_cat_sprite("pet")))
    root.after(0, sound_meow)
    # Cancel any previous reset timer
    if _pet_after_id is not None:
        root.after_cancel(_pet_after_id)
    def _reset_pet():
        global _pet_after_id
        _pet_after_id = None
        root.after(0, lambda: btn.config(text=get_cat_sprite("normal")))
    _pet_after_id = root.after(3000, _reset_pet)

# ---------------------------------------------------------------------------
# Mouse tracking
# ---------------------------------------------------------------------------
def track_mouse():
    global facing_right, mouse_tracking_enabled
    # Shake detection state
    _shake_history = []   # list of (time, x)
    _shake_cooldown = [0.0]

    while True:
        time.sleep(0.05)
        if drag["active"]:
            continue
        try:
            mx = root.winfo_pointerx()
            now = time.time()

            # Facing direction
            if mouse_tracking_enabled:
                new_facing = mx > root.winfo_x() + root.winfo_width()//2
                if new_facing != facing_right:
                    facing_right = new_facing

            # Shake detection — track last 0.4s of mouse x positions
            _shake_history.append((now, mx))
            _shake_history[:] = [(t, x) for t, x in _shake_history if now - t < 0.4]

            if len(_shake_history) >= 6 and now > _shake_cooldown[0]:
                xs = [x for _, x in _shake_history]
                # Count direction reversals
                reversals = 0
                for i in range(1, len(xs) - 1):
                    if (xs[i] - xs[i-1]) * (xs[i+1] - xs[i]) < 0:
                        reversals += 1
                # Total horizontal travel
                travel = sum(abs(xs[i] - xs[i-1]) for i in range(1, len(xs)))
                if reversals >= 3 and travel > 80:
                    # Direction = vector from neko center to mouse
                    try:
                        neko_cx = root.winfo_x() + root.winfo_width()  // 2
                        neko_cy = root.winfo_y() + root.winfo_height() // 2
                        mouse_x = root.winfo_pointerx()
                        mouse_y = root.winfo_pointery()
                        dx = mouse_x - neko_cx
                        dy = mouse_y - neko_cy
                        dist = max(1, (dx**2 + dy**2) ** 0.5)
                        # Speed = enough steps to cover dist + 25% overshoot
                        # move_window decays by 0.92 each frame (16ms)
                        # sum of geometric series: speed / (1-0.92) = speed / 0.08
                        # so speed = dist * 0.08 * 1.25
                        speed = dist * 0.08 * 1.25
                        speed = max(12, min(speed, 80))  # clamp: never too weak or wild
                        drag["vx"] = (dx / dist) * speed
                        drag["vy"] = (dy / dist) * speed
                    except Exception:
                        drag["vx"] = random.choice([-28, 28])
                        drag["vy"] = random.choice([-10, 0, 10])
                    _shake_cooldown[0] = now + 1.5
                    _shake_history.clear()
                    _mxi = root.winfo_pointerx()
                    if _mouse_over_window:
                        root.after(0, lambda x=_mxi: show_pet_sprite(x))
                    else:
                        root.after(0, move_window)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Inactivity loop
# ---------------------------------------------------------------------------
_idle_state    = "normal"   # "normal" | "looking" | "sleepy"
_idle_look_end = 0.0
_pet_after_id  = None       # after() id for pet sprite reset

def check_inactivity():
    global last_interaction_time, _idle_state, _idle_look_end
    while True:
        time.sleep(1)
        t = time.time() - last_interaction_time
        if (5 < t < 6 or 16 < t < 17) and root.state() == "normal":
            root.after(0, hop_animation)
        if 120 < t < 121 or 240 < t < 241:
            sound_meow()

        now = time.time()

        # Fade to transparent after 10s — but never while mouse is over window
        wake_age = time.time() - _last_wake_time
        if wake_age > 10 and not _mouse_over_window:
            root.after(0, lambda: root.attributes("-alpha", 0.7))
        else:
            root.after(0, lambda: root.attributes("-alpha", 1.0))

        if t > 40:
            last_interaction_time = time.time()
            _idle_state = "normal"
        elif t > 20:
            # Transition into idle if not already idle
            if _idle_state == "normal":
                if random.random() < 0.5:
                    _idle_state    = "looking"
                    _idle_look_end = now + 5      # looking for 5 seconds
                else:
                    _idle_state = "sleepy"
            # If looking timer expired, graduate to sleepy
            if _idle_state == "looking" and now >= _idle_look_end:
                _idle_state = "sleepy"
                # 40% chance: fling neko in a random direction when falling asleep
                if random.random() < 0.4 and not _mouse_over_window:
                    drag["vx"] = random.choice([-22, -18, 18, 22])
                    drag["vy"] = random.choice([-14, -10, 10, 14])
                    root.after(0, move_window)
            if _pet_after_id is None:
                root.after(0, lambda: btn.config(text=get_cat_sprite(_idle_state)))
        else:
            _idle_state = "normal"
            cur = btn.cget("text")
            if cur != get_cat_sprite("hover") and _pet_after_id is None:
                root.after(0, lambda: btn.config(text=get_cat_sprite("normal")))

# ---------------------------------------------------------------------------
# Hide/show toggle (used by the "Show/hide neko" automation action)
# ---------------------------------------------------------------------------
def hotkey_toggle():
    purr.play()
    root.wm_state("iconic") if root.state() == "normal" else root.deiconify()

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
threading.Thread(target=check_inactivity, daemon=True).start()
threading.Thread(target=track_mouse,      daemon=True).start()

try:
    root.iconbitmap(os.path.join(UTILS_DIR, "icon.ico"))
except Exception:
    pass

def _on_mouse_enter(e=None):
    global _mouse_over_window
    _mouse_over_window = True
    root.attributes("-alpha", 1.0)

def _on_mouse_leave(e=None):
    global _mouse_over_window
    _mouse_over_window = False

root.bind("<Enter>", _on_mouse_enter)
root.bind("<Leave>", _on_mouse_leave)

root.mainloop()
