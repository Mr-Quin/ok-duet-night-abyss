"""Live control service: frame capture plus input injection for the game window, on 127.0.0.1.

Run it in the interactive desktop session as administrator (the game runs elevated):
    python -m harness.live.service
"""
import ctypes
import json
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
from windows_capture import WindowsCapture

from harness.live import winapi

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
PORT = 8770
user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x1, 0x2, 0x4
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x8, 0x10
MOUSEEVENTF_WHEEL, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x800, 0x8000, 0x4000
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE, KEYEVENTF_EXTENDEDKEY = 0x2, 0x8, 0x1


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


# set-1 scancodes; (code, extended)
SCAN = {"esc": (0x01, 0), "tab": (0x0F, 0), "enter": (0x1C, 0), "space": (0x39, 0), "lshift": (0x2A, 0),
        "lctrl": (0x1D, 0), "lalt": (0x38, 0), "up": (0x48, 1), "down": (0x50, 1), "left": (0x4B, 1),
        "right": (0x4D, 1), "f1": (0x3B, 0), "f2": (0x3C, 0), "f3": (0x3D, 0), "f4": (0x3E, 0)}
for i, c in enumerate("1234567890"):
    SCAN[c] = (0x02 + i, 0)
for row, start in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for i, c in enumerate(row):
        SCAN[c] = (start + i, 0)


def send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def key_input(name, up):
    code, ext = SCAN[name]
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if ext else 0)
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(0, code, flags, 0, 0)
    return i


def mouse_input(flags, dx=0, dy=0, data=0):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    return i


class Game:
    def __init__(self):
        self.hwnd = None
        self.latest = None
        self.lock = threading.Lock()
        self.control = None

    def ensure(self):
        if self.hwnd and winapi.is_usable(self.hwnd):
            return self.hwnd
        hwnd = winapi.find_window("EM-Win64-Shipping.exe", None, None)
        if not hwnd:
            raise RuntimeError("game window not found")
        self.hwnd = hwnd
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

        @cap.event
        def on_frame_arrived(frame, control):
            buf = frame.frame_buffer
            x, y, w, h = winapi.client_crop(hwnd, buf.shape[1], buf.shape[0])
            with self.lock:
                self.latest = (time.time(), np.ascontiguousarray(buf[y:y + h, x:x + w, :3]))

        @cap.event
        def on_closed():
            pass

        self.control = cap.start_free_threaded()
        for _ in range(50):
            if self.latest is not None:
                break
            time.sleep(0.05)
        return hwnd

    def frame(self, max_age=0.5):
        self.ensure()
        deadline = time.time() + 2
        while time.time() < deadline:
            with self.lock:
                if self.latest and time.time() - self.latest[0] <= max_age:
                    return self.latest[1].copy()
            time.sleep(0.03)
        with self.lock:
            return None if self.latest is None else self.latest[1].copy()

    def to_screen(self, x, y):
        pt = wintypes.POINT(int(x), int(y))
        user32.ClientToScreen(self.ensure(), ctypes.byref(pt))
        return pt.x, pt.y

    def foreground(self):
        return user32.GetForegroundWindow() == self.ensure()

    def focus(self):
        hwnd = self.ensure()
        # a synthetic Alt tap satisfies the foreground-lock rule for SetForegroundWindow
        send(key_input("lalt", False), key_input("lalt", True))
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return self.foreground()

    def move(self, x, y):
        # The game tracks the cursor from mouse input and sometimes puts it back after a bare
        # SetCursorPos, so also send an absolute move event across the virtual desktop.
        sx, sy = self.to_screen(x, y)
        user32.SetCursorPos(sx, sy)
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        ax = int((sx - vx) * 65535 / max(1, vw - 1))
        ay = int((sy - vy) * 65535 / max(1, vh - 1))
        send(mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, ax, ay))

    def click(self, x, y, button="left", hold=0.05):
        self.move(x, y)
        time.sleep(0.05)
        down, up = (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left" else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
        send(mouse_input(down))
        time.sleep(hold)
        send(mouse_input(up))

    def scroll(self, x, y, notches):
        self.move(x, y)
        time.sleep(0.05)
        step = 1 if notches > 0 else -1
        for _ in range(abs(int(notches))):
            send(mouse_input(MOUSEEVENTF_WHEEL, data=120 * step))
            time.sleep(0.015)

    def key(self, name, hold=0.06):
        send(key_input(name, False))
        time.sleep(hold)
        send(key_input(name, True))

    def turn(self, dx, dy=0, steps=10):
        for _ in range(steps):
            send(mouse_input(MOUSEEVENTF_MOVE, int(dx / steps), int(dy / steps)))
            time.sleep(0.01)


GAME = Game()


def save_frame(name="last", scale=1.0):
    img = GAME.frame()
    if img is None:
        raise RuntimeError("no frame")
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.png"
    if scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), img)
    return {"path": str(path), "w": img.shape[1], "h": img.shape[0]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_raw(self, img):
        body = np.ascontiguousarray(img).tobytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("X-Shape", ",".join(str(v) for v in img.shape))
        self.send_header("X-Time", "%.4f" % time.time())
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        f = lambda k, d=0.0: float(q.get(k, d))
        try:
            cmd = url.path.strip("/")
            if cmd == "frame":
                # raw BGR pixels, resized to width w; skips PNG encoding and the disk
                img = GAME.frame(max_age=f("max_age", 0.2))
                w = int(f("w", img.shape[1]))
                if w != img.shape[1]:
                    img = cv2.resize(img, (w, int(img.shape[0] * w / img.shape[1])), interpolation=cv2.INTER_AREA)
                if q.get("gray") == "1":
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                return self.send_raw(img)
            if cmd == "status":
                GAME.ensure()
                w, h = winapi.client_size(GAME.hwnd)
                res = {"hwnd": GAME.hwnd, "client": [w, h], "foreground": GAME.foreground()}
            elif cmd == "shot":
                res = save_frame(q.get("name", "last"), f("scale", 1.0))
            elif cmd in ("click", "key", "scroll", "turn", "move") and not GAME.foreground() and q.get("force") != "1":
                res = {"error": "game is not the foreground window; refusing to send input"}
            elif cmd == "focus":
                res = {"ok": GAME.focus(), "foreground": GAME.foreground()}
            elif cmd == "click":
                GAME.click(f("x"), f("y"), q.get("button", "left"))
                if "park_x" in q:
                    time.sleep(0.05)
                    GAME.move(f("park_x"), f("park_y"))
                res = {"ok": True}
            elif cmd == "move":
                GAME.move(f("x"), f("y"))
                res = {"ok": True}
            elif cmd == "key":
                GAME.key(q["k"].lower(), f("hold", 0.06))
                res = {"ok": True}
            elif cmd == "scroll":
                GAME.scroll(f("x"), f("y"), f("n"))
                res = {"ok": True}
            elif cmd == "turn":
                GAME.turn(f("dx"), f("dy"), int(f("steps", 10)))
                res = {"ok": True}
            else:
                res = {"error": "unknown command"}
            code = 200 if "error" not in res else 409
        except Exception as e:
            res, code = {"error": repr(e)}, 500
        body = json.dumps(res).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    winapi.enable_dpi_awareness()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


