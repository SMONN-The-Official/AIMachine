"""
鼠标控制模块。
提供跨平台的鼠标移动与点击功能，支持平滑 / 瞬移两种模式。

- Windows：优先使用 ctypes + win32api 获得最低延迟
- Linux/macOS：使用 pyautogui 后端（需要桌面环境）
"""

import time
import sys
from typing import Tuple

from config import BotConfig

_USE_WIN32 = sys.platform == "win32"

# ── Windows 原生后端 ────────────────────────────────────────────
if _USE_WIN32:
    import ctypes

    _user32 = ctypes.windll.user32
    _MOUSEEVENTF_LEFTDOWN = 0x0002
    _MOUSEEVENTF_LEFTUP = 0x0004

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def _get_cursor_pos() -> Tuple[int, int]:
        pt = _POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _set_cursor_pos(x: int, y: int):
        _user32.SetCursorPos(x, y)

    def _mouse_down():
        _user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

    def _mouse_up():
        _user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

# ── 跨平台后端（延迟导入，避免无头环境崩溃）────────────────────
else:
    _pyautogui = None

    def _ensure_pyautogui():
        global _pyautogui
        if _pyautogui is None:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.0
            _pyautogui = pyautogui
        return _pyautogui

    def _get_cursor_pos() -> Tuple[int, int]:
        pag = _ensure_pyautogui()
        pos = pag.position()
        return pos.x, pos.y

    def _set_cursor_pos(x: int, y: int):
        pag = _ensure_pyautogui()
        pag.moveTo(x, y, _pause=False)

    def _mouse_down():
        pag = _ensure_pyautogui()
        pag.mouseDown(_pause=False)

    def _mouse_up():
        pag = _ensure_pyautogui()
        pag.mouseUp(_pause=False)


class MouseController:

    def __init__(self, cfg: BotConfig):
        self._cfg = cfg

    def get_position(self) -> Tuple[int, int]:
        return _get_cursor_pos()

    def move_to(self, x: int, y: int):
        """移动到绝对坐标，根据配置决定是否平滑。"""
        if self._cfg.use_smooth_move and self._cfg.smooth_steps > 1:
            self._smooth_move(x, y)
        else:
            _set_cursor_pos(x, y)

    def click(self):
        """执行一次左键点击。"""
        _mouse_down()
        _mouse_up()
        if self._cfg.click_delay > 0:
            time.sleep(self._cfg.click_delay)

    def move_and_click(self, x: int, y: int):
        """移动到目标并点击。"""
        self.move_to(x, y)
        self.click()

    def _smooth_move(self, dst_x: int, dst_y: int):
        """平滑移动（线性插值）。"""
        src_x, src_y = _get_cursor_pos()
        steps = self._cfg.smooth_steps
        for i in range(1, steps + 1):
            t = i / steps
            ix = int(src_x + (dst_x - src_x) * t)
            iy = int(src_y + (dst_y - src_y) * t)
            _set_cursor_pos(ix, iy)

    @staticmethod
    def frame_to_screen(fx: int, fy: int,
                        offset_x: int, offset_y: int) -> Tuple[int, int]:
        """将帧内坐标映射为屏幕绝对坐标。"""
        return fx + offset_x, fy + offset_y
