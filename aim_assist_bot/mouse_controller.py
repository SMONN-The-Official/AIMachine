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

    # ── 点击（down 和 up 必须分开发送，中间留持续时间）────────
    def _mouse_down():
        inp = _make_mouse_input(flags=_MOUSEEVENTF_LEFTDOWN)
        _send_input(inp)

    def _mouse_up():
        inp = _make_mouse_input(flags=_MOUSEEVENTF_LEFTUP)
        _send_input(inp)

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

    def _mouse_down():
        pag = _ensure_pyautogui()
        pag.mouseDown(_pause=False)

    def _mouse_up():
        pag = _ensure_pyautogui()
        pag.mouseUp(_pause=False)


# ═══════════════════════════════════════════════════════════════
# 对外接口
# ═══════════════════════════════════════════════════════════════
class MouseController:

    def __init__(self, cfg: BotConfig):
        self._cfg = cfg

    # ── 游戏模式：相对位移 ──────────────────────────────────────
    def move_relative(self, dx: int, dy: int) -> bool:
        """
        发送相对鼠标位移。

        返回 True 表示发送了移动，False 表示在死区内未移动。
        dx, dy 是屏幕像素偏移量（目标 - 准心）。
        """
        # 死区：目标已足够接近准心，不再移动
        if abs(dx) <= self._cfg.dead_zone and abs(dy) <= self._cfg.dead_zone:
            return False

        # 最大偏移量限制：防止误检导致准心飞出屏幕
        cap = self._cfg.max_move_px
        if cap > 0:
            dx = max(-cap, min(cap, dx))
            dy = max(-cap, min(cap, dy))

        s = self._cfg.sensitivity
        real_dx = int(round(dx * s))
        real_dy = int(round(dy * s))

        if self._cfg.use_smooth_move and self._cfg.smooth_steps > 1:
            self._smooth_move_relative(real_dx, real_dy)
        else:
            _move_relative(real_dx, real_dy)

        return True

    def click(self):
        """
        执行一次完整的左键点击。
        down 和 up 分开发送，中间保持按住状态一段时间，
        确保游戏能识别为有效点击。
        """
        _mouse_down()
        time.sleep(self._cfg.click_hold_time)
        _mouse_up()

    def move_relative_and_click(self, dx: int, dy: int) -> bool:
        """
        移动到目标并点击（游戏模式主调用）。

        返回 True 表示执行了移动+点击，False 表示目标在死区内（仅点击）。
        """
        moved = self.move_relative(dx, dy)

        # 移动后等一小段时间让游戏处理完位移再点击
        if moved:
            time.sleep(self._cfg.move_click_gap)

        self.click()
        return moved

    # ── 桌面模式：绝对坐标 ──────────────────────────────────────
    def move_to(self, x: int, y: int):
        if self._cfg.use_smooth_move and self._cfg.smooth_steps > 1:
            self._smooth_move_absolute(x, y)
        else:
            _set_cursor_pos(x, y)

    def move_and_click(self, x: int, y: int):
        self.move_to(x, y)
        time.sleep(self._cfg.move_click_gap)
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

        流程：
          1. 连续空截几帧刷掉截屏缓冲区的旧帧
          2. 截帧 A（基准帧）
          3. SendInput 发送大幅测试位移
          4. 等待足够长时间让游戏渲染新画面
          5. 连续截多帧，逐帧与帧 A 做相位相关分析
          6. 取检测到的最大水平偏移作为实际位移
          7. sensitivity = test_dx / actual_pixel_shift
          8. 发反向位移恢复原位

        使用 cv2.phaseCorrelate（傅里叶相位相关）测量两帧间的
        亚像素级精确位移。比模板匹配更鲁棒——即使 Kovaak's 的
        大面积纯色背景也能正确测量。
        """
        import cv2
        import numpy as np
        import os

        test_dx = self._cfg.calibrate_move_px
        settle = self._cfg.calibrate_settle_ms
        n_samples = 5

        print(f"[灵敏度校准] 开始...")
        print(f"  截屏后端: {capture.backend_name}")
        print(f"  测试位移: {test_dx} mickey")
        print(f"  等待时间: {settle:.2f}s × {n_samples} 帧采样")

        # 刷掉截屏缓冲区的陈旧帧
        for _ in range(5):
            capture.grab()
            time.sleep(0.03)

        frame_a = capture.grab()
        h, w = frame_a.shape[:2]
        print(f"  帧尺寸:   {w}×{h}")

        # 诊断：保存帧 A
        diag_dir = os.path.join(os.path.dirname(__file__), "diag")
        os.makedirs(diag_dir, exist_ok=True)
        cv2.imwrite(os.path.join(diag_dir, "calib_frame_a.png"), frame_a)

        # 取帧中心区域转为 float64 灰度（phaseCorrelate 要求）
        pad = 80
        roi = (slice(h // 4, h * 3 // 4), slice(pad, w - pad))
        gray_a = cv2.cvtColor(frame_a[roi], cv2.COLOR_BGR2GRAY).astype(np.float64)

        # 检查帧 A 是否全黑（说明截屏后端无法捕获游戏画面）
        mean_brightness = np.mean(gray_a)
        print(f"  帧A平均亮度: {mean_brightness:.1f} (全黑=0)")
        if mean_brightness < 5:
            print(f"[灵敏度校准] 帧 A 几乎全黑！截屏后端无法捕获游戏画面。")
            print(f"  解决方案:")
            print(f"    1. 安装 dxcam: pip install dxcam")
            print(f"    2. 或将 Kovaak's 切换为「无边框窗口」模式")
            print(f"  诊断图片已保存到 {diag_dir}/ 目录")
            return self._cfg.sensitivity

        hann = cv2.createHanningWindow(
            (gray_a.shape[1], gray_a.shape[0]), cv2.CV_64F
        )

        # 发送测试位移
        _move_relative(test_dx, 0)

        # 多帧采样
        best_shift = 0.0
        best_confidence = 0.0
        best_frame_b = None

        for i in range(n_samples):
            time.sleep(settle)
            frame_b = capture.grab()
            gray_b = cv2.cvtColor(frame_b[roi], cv2.COLOR_BGR2GRAY).astype(np.float64)

            (dx_detected, _dy), confidence = cv2.phaseCorrelate(
                gray_a, gray_b, hann
            )
            print(f"  帧#{i}: 偏移={dx_detected:+.1f}px, 置信度={confidence:.4f}")

            if abs(dx_detected) > abs(best_shift):
                best_confidence = confidence
                best_shift = dx_detected
                best_frame_b = frame_b

        # 恢复原位
        _move_relative(-test_dx, 0)
        time.sleep(settle)

        # 诊断：保存帧 B 和差异图
        if best_frame_b is not None:
            cv2.imwrite(os.path.join(diag_dir, "calib_frame_b.png"), best_frame_b)
            diff = cv2.absdiff(frame_a, best_frame_b)
            cv2.imwrite(os.path.join(diag_dir, "calib_diff.png"), diff)

        # 检查帧 A 和帧 B 是否完全相同
        if best_frame_b is not None:
            pixel_diff = np.mean(cv2.absdiff(frame_a, best_frame_b))
            print(f"  帧A-B 平均像素差: {pixel_diff:.2f} (0=完全相同)")
            if pixel_diff < 0.5:
                print(f"[灵敏度校准] 截到的两帧几乎完全相同！")
                print(f"  说明截屏后端未能捕获到游戏的实时画面。")
                print(f"  解决方案:")
                print(f"    1. 安装 dxcam: pip install dxcam")
                print(f"    2. 或将 Kovaak's 切换为「无边框窗口」模式")
                print(f"  诊断图片已保存到 {diag_dir}/ 目录，请查看:")
                print(f"    calib_frame_a.png — 移动前截图")
                print(f"    calib_frame_b.png — 移动后截图")
                print(f"    calib_diff.png    — 两帧差异")
                return self._cfg.sensitivity

        actual_px = abs(best_shift)

        if actual_px < 1.0:
            print(f"[灵敏度校准] 未检测到有效画面移动 (最大偏移={actual_px:.1f}px)")
            print(f"  诊断图片已保存到 {diag_dir}/ 目录")
            print(f"  排查建议:")
            print(f"    1. 安装 dxcam: pip install dxcam")
            print(f"    2. 或将 Kovaak's 切换为「无边框窗口」模式")
            print(f"    3. 确保在训练场景内（非主菜单）按 F6")
            return self._cfg.sensitivity

        new_sens = test_dx / actual_px
        self._cfg.sensitivity = new_sens

        print(f"[灵敏度校准] 完成!")
        print(f"  发送:       {test_dx} mickey")
        print(f"  画面偏移:   {actual_px:.1f} 像素")
        print(f"  置信度:     {best_confidence:.4f}")
        print(f"  sensitivity = {new_sens:.4f}")
        print(f"  (即 1 屏幕像素 ≈ {new_sens:.2f} mickey)")

        return new_sens

    @staticmethod
    def frame_to_screen(fx: int, fy: int,
                        offset_x: int, offset_y: int) -> Tuple[int, int]:
        return fx + offset_x, fy + offset_y
