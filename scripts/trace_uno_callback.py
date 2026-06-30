"""Diagnose exactly why UNO is dropped in _list_win32 callback."""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, "services/adapter-windows/src")
sys.path.insert(0, "packages/schemas/src")
sys.path.insert(0, "packages/shared-utils/src")

UNO_PID = 23992

EnumWindows = ctypes.windll.user32.EnumWindows
GetWindowTextW = ctypes.windll.user32.GetWindowTextW
GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
GetClassNameW = ctypes.windll.user32.GetClassNameW

kernel32 = ctypes.windll.kernel32
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

seen = set()

def callback(hwnd, _lparam):
    pid = ctypes.c_ulong()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value

    if pid_val != UNO_PID:
        return True

    handle = int(hwnd)
    length = GetWindowTextLengthW(hwnd)

    print(f"  [UNO] HWND={handle} PID={pid_val}")

    if length <= 0:
        print("  [UNO] DROPPED: length <= 0")
        return True

    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    if not title.strip():
        print("  [UNO] DROPPED: empty title after strip")
        return True

    print(f"  [UNO] title='{title}' (len={len(title)})")

    if handle in seen:
        print("  [UNO] DROPPED: duplicate handle")
        return True
    seen.add(handle)

    # Test _process_name_for_pid
    try:
        ph = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_val)
        if ph:
            buf2 = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(len(buf2))
            if kernel32.QueryFullProcessImageNameW(ph, 0, buf2, ctypes.byref(size)):
                pname = Path(buf2.value).name
            else:
                pname = None
            kernel32.CloseHandle(ph)
        else:
            pname = None
        print(f"  [UNO] process_name={pname}")
    except Exception as e:
        print(f"  [UNO] EXCEPTION in process_name: {e}")
        pname = None

    # Test GetClassNameW
    try:
        cn_buf = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, cn_buf, 256)
        class_name = cn_buf.value
    except Exception as e:
        print(f"  [UNO] EXCEPTION in GetClassNameW: {e}")
        class_name = ""

    print(f"  [UNO] class_name='{class_name}'")

    # Test IsWindowVisible
    try:
        vis = bool(IsWindowVisible(hwnd))
    except Exception as e:
        print(f"  [UNO] EXCEPTION in IsWindowVisible: {e}")
        vis = False

    print(f"  [UNO] visible={vis}")

    if not vis:
        print("  [UNO] DROPPED: not visible")
        return True

    # Test browser_candidate_warning
    try:
        from uno_adapter_windows.browser_attach import browser_candidate_warning
        is_br = browser_candidate_warning(pname, class_name) is not None
        print(f"  [UNO] is_browser_host={is_br}")
    except Exception as e:
        print(f"  [UNO] EXCEPTION in browser_candidate_warning: {e}")

    print("  [UNO] WOULD BE ADDED (if not caught by outer except)")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
print("=== EnumWindows callback trace for UNO ===")
EnumWindows(WNDENUMPROC(callback), 0)
print("=== Done ===")
