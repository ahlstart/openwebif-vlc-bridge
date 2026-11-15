from http.server import BaseHTTPRequestHandler, HTTPServer
import ctypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from ctypes import wintypes

VLC_EXE = "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"
LISTEN = ("localhost", 8124)   # the userscript calls http://localhost:8124/vlc?url=...

# Any web page can make the browser call this helper, so only hand VLC real stream URLs.
# (A value starting with "--" would otherwise be parsed by VLC as a command-line option.)
ALLOWED_SCHEMES = ("http", "https", "rtsp", "udp")

# pythonw.exe (no console) sets sys.stdout/sys.stderr to None; http.server logs every
# request to sys.stderr and would crash each request. Send output to a log file instead.
if sys.stdout is None or sys.stderr is None:
    _log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VLCHelper.log"),
                "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

# --- Win32: bring the new VLC window to the foreground ---------------------------------
# Windows blocks background processes (like this helper) from stealing focus, so VLC
# would open behind the browser. Attaching to the foreground thread's input queue lets
# SetForegroundWindow succeed; an Alt key tap is the fallback.
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]

SW_RESTORE = 9
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x2


def find_vlc_window(pid: int, by_title: bool) -> int | None:
    """Visible titled top-level window of process `pid`, or (if by_title) any VLC window."""
    found: list[int] = []

    def cb(hwnd: int, _lparam: int) -> bool:  # pyright: ignore[reportUnusedParameter]
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, title, n + 1)
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid or (by_title and title.value.endswith("VLC media player")):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else None


def bring_to_front(hwnd: int) -> None:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    my_tid = kernel32.GetCurrentThreadId()
    attached = bool(fg_tid) and fg_tid != my_tid and user32.AttachThreadInput(my_tid, fg_tid, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(my_tid, fg_tid, False)
    if user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)


def raise_vlc(proc: "subprocess.Popen[bytes]", timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # If VLC runs in "one instance" mode, the new vlc.exe hands the URL to the
        # existing instance and exits - then look for any VLC window by title.
        hwnd = find_vlc_window(proc.pid, by_title=proc.poll() is not None)
        if hwnd:
            time.sleep(0.3)  # let VLC finish creating/activating its window
            bring_to_front(hwnd)
            return
        time.sleep(0.2)
    print("VLC window not found within %.0fs" % timeout, file=sys.stderr)


class H(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        url = qs.get("url", [""])[0]

        if url and urllib.parse.urlparse(url).scheme.lower() not in ALLOWED_SCHEMES:
            self.send_response(400)
            self.end_headers()
            return

        if url:
            proc = subprocess.Popen([VLC_EXE, url],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            threading.Thread(target=raise_vlc, args=(proc,), daemon=True).start()

        self.send_response(200)
        self.end_headers()


HTTPServer(LISTEN, H).serve_forever()
