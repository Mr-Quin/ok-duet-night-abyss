"""Window lookup helpers for the live control service (Windows only)."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.c_void_p]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]


def enable_dpi_awareness():
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def process_path(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def window_text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def client_size(hwnd):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.right, rect.bottom


def find_window(exe=None, title=None, cls=None):
    """Largest visible top-level window matching all given filters."""
    matches = []

    @WNDENUMPROC
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        if cls and window_class(hwnd) != cls:
            return True
        if title and title.lower() not in window_text(hwnd).lower():
            return True
        if exe:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if process_path(pid.value).lower().rsplit("\\", 1)[-1] != exe.lower():
                return True
        w, h = client_size(hwnd)
        if w > 0 and h > 0:
            matches.append((w * h, hwnd))
        return True

    user32.EnumWindows(visit, 0)
    return max(matches)[1] if matches else None


def is_usable(hwnd):
    return bool(user32.IsWindow(hwnd)) and not user32.IsIconic(hwnd)


def window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def client_crop(hwnd, frame_w, frame_h):
    """(x, y, w, h) of the client area inside a window-capture frame."""
    bounds = wintypes.RECT()
    dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(bounds), ctypes.sizeof(bounds))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    w, h = client_size(hwnd)
    x = max(0, origin.x - bounds.left)
    y = max(0, origin.y - bounds.top)
    return x, y, min(w, frame_w - x), min(h, frame_h - y)
