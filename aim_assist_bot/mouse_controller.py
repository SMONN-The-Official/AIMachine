"""
鼠标控制模块。

两种移动模式：
  1. game_mode=True  (默认) —— SendInput 相对位移
     游戏用 Raw Input 读取鼠标增量，只有 SendInput 注入的
     相对位移事件能被游戏识别。准心锁定在屏幕中心，发送
     (dx, dy) 让游戏移动准心到目标位置。
  2. game_mode=False —— SetCursorPos / pyautogui 绝对坐标
     适用于桌面窗口程序或不使用 Raw Input 的游戏。

Windows 上使用 ctypes 直接调用 Win32 API，延迟最低。
Linux/macOS 回退到 pyautogui（moveRel / moveTo）。
"""

import time
import sys
from typing import Tuple

from config import BotConfig

_IS_WIN32 = sys.platform == "win32"

# ═══════════════════════════════════════════════════════════════
# Windows 原生后端：ctypes SendInput
# ═══════════════════════════════════════════════════════════════
if _IS_WIN32:
    import ctypes
    import ctypes.wintypes

    _user32 = ctypes.windll.user32

    # ── SendInput 结构体 ────────────────────────────────────────
    _INPUT_MOUSE = 0
    _MOUSEEVENTF_MOVE = 0x0001
    _MOUSEEVENTF_LEFTDOWN = 0x0002
    _MOUSEEVENTF_LEFTUP = 0x0004
    _MOUSEEVENTF_ABSOLUTE = 0x8000

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUT(ctypes.Structure):
        class _UNION(ctypes.Union):
            _fields_ = [("mi", _MOUSEINPUT)]

        _anonymous_ = ("_union",)
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("_union", _UNION),
        ]

    def _send_input(*inputs):
        n = len(inputs)
        arr = (_INPUT * n)(*inputs)
        _user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))

    def _make_mouse_input(dx=0, dy=0, flags=0):
        inp = _INPUT()
        inp.type = _INPUT_MOUSE
        inp.mi.dx = dx
        inp.mi.dy = dy
        inp.mi.dwFlags = flags
        inp.mi.time = 0
        inp.mi.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
        return inp

    # ── 相对位移（游戏模式）────────────────────────────────────
    def _move_relative(dx: int, dy: int):
        inp = _make_mouse_input(dx, dy, _MOUSEEVENTF_MOVE)
        _send_input(inp)

    # ── 绝对坐标（桌面模式）────────────────────────────────────
    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def _get_cursor_pos() -> Tuple[int, int]:
        pt = _POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _set_cursor_pos(x: int, y: int):
        _user32.SetCursorPos(x, y)

    # ── 点击 ────────────────────────────────────────────────────
    def _click():
        down = _make_mouse_input(flags=_MOUSEEVENTF_LEFTDOWN)
        up = _make_mouse_input(flags=_MOUSEEVENTF_LEFTUP)
        _send_input(down, up)

# ═══════════════════════════════════════════════════════════════
# 跨平台后端：pyautogui（延迟导入）
# ═══════════════════════════════════════════════════════════════
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

    def _move_relative(dx: int, dy: int):
        pag = _ensure_pyautogui()
        pag.moveRel(dx, dy, _pause=False)

    def _get_cursor_pos() -> Tuple[int, int]:
        pag = _ensure_pyautogui()
        pos = pag.position()
        return pos.x, pos.y

    def _set_cursor_pos(x: int, y: int):
        pag = _ensure_pyautogui()
        pag.moveTo(x, y, _pause=False)

    def _click():
        pag = _ensure_pyautogui()
        pag.mouseDown(_pause=False)
        pag.mouseUp(_pause=False)


# ═══════════════════════════════════════════════════════════════
# 对外接口
# ═══════════════════════════════════════════════════════════════
class MouseController:

    def __init__(self, cfg: BotConfig):
        self._cfg = cfg

    # ── 游戏模式：相对位移 ──────────────────────────────────────
    def move_relative(self, dx: int, dy: int):
        """
        发送相对鼠标位移。游戏模式核心函数。

        dx, dy 是像素偏移量（目标位置 - 准心位置），
        乘以 sensitivity 倍率后经 SendInput 发送给系统。
        """
        s = self._cfg.sensitivity
        real_dx = int(round(dx * s))
        real_dy = int(round(dy * s))

        if self._cfg.use_smooth_move and self._cfg.smooth_steps > 1:
            self._smooth_move_relative(real_dx, real_dy)
        else:
            _move_relative(real_dx, real_dy)

    def click(self):
        _click()
        if self._cfg.click_delay > 0:
            time.sleep(self._cfg.click_delay)

    def move_relative_and_click(self, dx: int, dy: int):
        """移动相对偏移并点击（游戏模式主调用）。"""
        self.move_relative(dx, dy)
        self.click()

    # ── 桌面模式：绝对坐标 ──────────────────────────────────────
    def move_to(self, x: int, y: int):
        if self._cfg.use_smooth_move and self._cfg.smooth_steps > 1:
            self._smooth_move_absolute(x, y)
        else:
            _set_cursor_pos(x, y)

    def move_and_click(self, x: int, y: int):
        """移动到绝对坐标并点击（桌面模式）。"""
        self.move_to(x, y)
        self.click()

    def get_position(self) -> Tuple[int, int]:
        return _get_cursor_pos()

    # ── 平滑移动 ────────────────────────────────────────────────
    def _smooth_move_relative(self, total_dx: int, total_dy: int):
        """将总偏移分成 N 步逐步发送。"""
        steps = self._cfg.smooth_steps
        remainder_x, remainder_y = 0.0, 0.0
        for i in range(1, steps + 1):
            target_x = total_dx * i / steps
            target_y = total_dy * i / steps
            prev_x = total_dx * (i - 1) / steps
            prev_y = total_dy * (i - 1) / steps
            step_dx = target_x - prev_x + remainder_x
            step_dy = target_y - prev_y + remainder_y
            int_dx = int(round(step_dx))
            int_dy = int(round(step_dy))
            remainder_x = step_dx - int_dx
            remainder_y = step_dy - int_dy
            _move_relative(int_dx, int_dy)

    def _smooth_move_absolute(self, dst_x: int, dst_y: int):
        src_x, src_y = _get_cursor_pos()
        steps = self._cfg.smooth_steps
        for i in range(1, steps + 1):
            t = i / steps
            ix = int(src_x + (dst_x - src_x) * t)
            iy = int(src_y + (dst_y - src_y) * t)
            _set_cursor_pos(ix, iy)

    # ── 灵敏度自动校准 ──────────────────────────────────────────
    def calibrate_sensitivity(self, capture, detector) -> float:
        """
        自动校准 sensitivity 倍率。

        原理：
          1. 截帧 A，记录所有目标的位置
          2. 发送已知位移 SendInput(test_dx, 0)
          3. 等待画面稳定，截帧 B
          4. 通过帧 A 与帧 B 之间画面的整体偏移量，反算
             实际 1 mickey 对应多少屏幕像素
          5. sensitivity = test_dx / 实际屏幕偏移

        使用模板匹配（cv2.matchTemplate）测量两帧之间的像素偏移，
        比依赖目标检测更鲁棒——即使场景中没有可点击目标也能校准。

        Parameters
        ----------
        capture : ScreenCapture 实例
        detector : TargetDetector 实例（此校准不依赖它，保留接口兼容）

        Returns
        -------
        校准后的 sensitivity 值，同时已写入 self._cfg.sensitivity
        """
        import cv2
        import numpy as np

        test_dx = self._cfg.calibrate_move_px
        settle = self._cfg.calibrate_settle_ms

        print(f"[灵敏度校准] 开始... 发送测试位移 {test_dx} mickey →")

        frame_a = capture.grab()

        h, w = frame_a.shape[:2]
        margin = max(test_dx * 2, 200)
        roi_y1, roi_y2 = h // 4, h * 3 // 4
        roi_x1, roi_x2 = margin, w - margin
        template = frame_a[roi_y1:roi_y2, roi_x1:roi_x2].copy()

        _move_relative(test_dx, 0)
        time.sleep(settle)

        frame_b = capture.grab()

        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(gray_b, gray_t, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < 0.5:
            print(f"[灵敏度校准] 模板匹配置信度过低 ({max_val:.2f})，校准失败")
            print(f"             请确保游戏画面中有静态参照物（墙壁、地板等）")
            # 发回去恢复原位
            _move_relative(-test_dx, 0)
            return self._cfg.sensitivity

        actual_shift = max_loc[0] - roi_x1
        # actual_shift 是模板在帧 B 中相对于帧 A 中原位置的偏移（像素）

        # 发回去恢复原位
        _move_relative(-test_dx, 0)
        time.sleep(settle)

        if abs(actual_shift) < 2:
            print(f"[灵敏度校准] 未检测到画面移动 (shift={actual_shift}px)")
            print(f"             可能原因：游戏未使用 Raw Input，或 SendInput 被拦截")
            return self._cfg.sensitivity

        # sensitivity = 需要发送多少 mickey 才能移动 1 屏幕像素
        # 我们发了 test_dx mickey，画面移了 actual_shift 像素
        # 要让 "检测到 N 像素偏移 → 发 N×sens mickey → 准心刚好移 N 像素"
        # 即 N × sens / test_dx × actual_shift = N
        # → sens = test_dx / actual_shift
        new_sens = test_dx / abs(actual_shift)

        self._cfg.sensitivity = new_sens

        print(f"[灵敏度校准] 完成!")
        print(f"  发送:     {test_dx} mickey")
        print(f"  画面移动: {abs(actual_shift)} 像素")
        print(f"  匹配度:   {max_val:.3f}")
        print(f"  sensitivity = {new_sens:.4f}")
        print(f"  (即 1 屏幕像素 = {new_sens:.2f} mickey)")

        return new_sens

    @staticmethod
    def frame_to_screen(fx: int, fy: int,
                        offset_x: int, offset_y: int) -> Tuple[int, int]:
        return fx + offset_x, fy + offset_y
