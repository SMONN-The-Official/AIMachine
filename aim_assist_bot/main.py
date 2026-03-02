#!/usr/bin/env python3
"""
Aim Trainer 自动瞄准助手 —— 主程序入口。

功能：
  - 实时捕获屏幕画面
  - 通过颜色 + 形状检测识别训练目标
  - 自动移动光标至目标中心并点击
  - 循环锁定下一目标直至训练结束

快捷键（默认）：
  F2  启动 / 暂停
  F3  切换调试预览窗口
  F4  退出
  F5  颜色取样校准（按住后点击目标区域）
"""

import sys
import time
import threading

import cv2
import numpy as np

from config import BotConfig, ColorRange
from screen_capture import ScreenCapture
from target_detector import TargetDetector
from mouse_controller import MouseController

# 热键后端：优先使用 keyboard（Windows 上表现最佳），失败则回退 pynput
_HOTKEY_BACKEND = None

def _init_hotkey_backend():
    global _HOTKEY_BACKEND
    try:
        import keyboard
        keyboard.is_pressed("shift")  # 简单检测是否可用
        _HOTKEY_BACKEND = "keyboard"
    except Exception:
        try:
            from pynput import keyboard as _pk
            _HOTKEY_BACKEND = "pynput"
        except ImportError:
            _HOTKEY_BACKEND = None


# ── pynput key name → Key 对象映射 ──────────────────────────────
_PYNPUT_KEY_MAP = {}

def _pynput_resolve_key(name: str):
    """将配置中的键名（如 'f2'）转换为 pynput Key 枚举。"""
    from pynput.keyboard import Key
    if not _PYNPUT_KEY_MAP:
        for k in Key:
            _PYNPUT_KEY_MAP[k.name.lower()] = k
    return _PYNPUT_KEY_MAP.get(name.lower())


class AimBot:

    def __init__(self, cfg: BotConfig | None = None):
        self.cfg = cfg or BotConfig()
        self.capture = ScreenCapture(self.cfg)
        self.detector = TargetDetector(self.cfg)
        self.mouse = MouseController(self.cfg)

        self._running = False
        self._active = False
        self._show_preview = self.cfg.show_preview
        self._alive = True

        self._stats_hits = 0
        self._stats_start: float = 0

        self._hotkey_listener = None

    # ── 快捷键绑定 ──────────────────────────────────────────────
    def _bind_keys(self):
        _init_hotkey_backend()

        if _HOTKEY_BACKEND == "keyboard":
            import keyboard
            keyboard.on_press_key(self.cfg.toggle_key, lambda _: self._toggle())
            keyboard.on_press_key(self.cfg.exit_key, lambda _: self._quit())
            keyboard.on_press_key(self.cfg.preview_key, lambda _: self._toggle_preview())
            keyboard.on_press_key(self.cfg.calibrate_key, lambda _: self._calibrate_color())

        elif _HOTKEY_BACKEND == "pynput":
            from pynput import keyboard as pk

            toggle_key = _pynput_resolve_key(self.cfg.toggle_key)
            exit_key = _pynput_resolve_key(self.cfg.exit_key)
            preview_key = _pynput_resolve_key(self.cfg.preview_key)
            calibrate_key = _pynput_resolve_key(self.cfg.calibrate_key)

            def _on_press(key):
                if key == toggle_key:
                    self._toggle()
                elif key == exit_key:
                    self._quit()
                elif key == preview_key:
                    self._toggle_preview()
                elif key == calibrate_key:
                    self._calibrate_color()

            self._hotkey_listener = pk.Listener(on_press=_on_press)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()

        else:
            print("[警告] 未检测到可用的热键后端（keyboard / pynput）。")
            print("       请手动使用 Ctrl+C 退出。程序将立即启动自动瞄准。")
            self._active = True

    def _unbind_keys(self):
        if _HOTKEY_BACKEND == "keyboard":
            import keyboard
            keyboard.unhook_all()
        elif self._hotkey_listener is not None:
            self._hotkey_listener.stop()

    def _toggle(self):
        self._active = not self._active
        state = "ON" if self._active else "OFF"
        print(f"[Bot] 自动瞄准: {state}")
        if self._active:
            self._stats_start = time.time()
            self._stats_hits = 0

    def _toggle_preview(self):
        self._show_preview = not self._show_preview
        if not self._show_preview:
            cv2.destroyAllWindows()
        print(f"[Bot] 调试预览: {'ON' if self._show_preview else 'OFF'}")

    def _quit(self):
        print("[Bot] 正在退出...")
        self._active = False
        self._alive = False

    # ── 颜色取样校准 ───────────────────────────────────────────
    def _calibrate_color(self):
        """截取当前帧，取鼠标位置附近区域的平均 HSV 值并打印建议范围。"""
        frame = self.capture.grab()
        mx, my = self.mouse.get_position()
        ox, oy = self.capture.offset
        fx, fy = mx - ox, my - oy

        h, w = frame.shape[:2]
        r = 10
        x1 = max(0, fx - r)
        y1 = max(0, fy - r)
        x2 = min(w, fx + r)
        y2 = min(h, fy + r)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            print("[校准] 取样区域无效，请将光标移到目标上再按 F5")
            return

        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mean_h = int(np.mean(hsv_roi[:, :, 0]))
        mean_s = int(np.mean(hsv_roi[:, :, 1]))
        mean_v = int(np.mean(hsv_roi[:, :, 2]))

        margin_h, margin_s, margin_v = 12, 60, 60
        lower = (max(0, mean_h - margin_h), max(0, mean_s - margin_s), max(0, mean_v - margin_v))
        upper = (min(180, mean_h + margin_h), min(255, mean_s + margin_s), min(255, mean_v + margin_v))

        print(f"[校准] 采样 HSV 均值: H={mean_h} S={mean_s} V={mean_v}")
        print(f"[校准] 建议范围: lower={lower}, upper={upper}")
        print(f"[校准] 若需永久保存，请将以上范围写入 config.py 的 color_ranges 中")

        new_range = ColorRange("calibrated", lower, upper)
        self.cfg.color_ranges = [new_range]
        print("[校准] 已临时应用新颜色范围（重启后失效）")

    # ── 主循环 ──────────────────────────────────────────────────
    def run(self):
        self._bind_keys()
        self._alive = True
        print("=" * 55)
        print("  Aim Trainer 自动瞄准助手")
        print("=" * 55)
        print(f"  [{self.cfg.toggle_key.upper()}]  启动 / 暂停")
        print(f"  [{self.cfg.preview_key.upper()}]  切换调试预览")
        print(f"  [{self.cfg.calibrate_key.upper()}]  颜色取样校准")
        print(f"  [{self.cfg.exit_key.upper()}]  退出")
        print("=" * 55)
        print(f"  当前颜色方案: {[cr.name for cr in self.cfg.color_ranges]}")
        print(f"  优先级策略:   {self.cfg.priority}")
        print(f"  截屏区域:     {self.cfg.capture_region}")
        print(f"  热键后端:     {_HOTKEY_BACKEND or '无'}")
        print("=" * 55)
        if self._active:
            print("自动瞄准已启动。")
        else:
            print(f"按 [{self.cfg.toggle_key.upper()}] 开始...")

        try:
            while self._alive:
                if not self._active:
                    time.sleep(0.05)
                    continue

                frame = self.capture.grab()
                targets = self.detector.detect(frame)

                if targets:
                    best = targets[0]
                    sx, sy = MouseController.frame_to_screen(
                        best.cx, best.cy, *self.capture.offset
                    )
                    self.mouse.move_and_click(sx, sy)
                    self._stats_hits += 1

                if self._show_preview:
                    vis = self.detector.draw_debug(frame, targets)
                    info = f"Targets: {len(targets)} | Hits: {self._stats_hits}"
                    if self._stats_start > 0:
                        elapsed = time.time() - self._stats_start
                        hps = self._stats_hits / max(elapsed, 0.001)
                        info += f" | {hps:.1f} hits/s | {elapsed:.1f}s"
                    cv2.putText(vis, info, (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.imshow("AimBot Debug", vis)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self._quit()

                if self.cfg.loop_delay > 0:
                    time.sleep(self.cfg.loop_delay)

        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _cleanup(self):
        self.capture.close()
        cv2.destroyAllWindows()
        self._unbind_keys()
        if self._stats_hits > 0 and self._stats_start > 0:
            elapsed = time.time() - self._stats_start
            print(f"\n[统计] 命中: {self._stats_hits}  "
                  f"用时: {elapsed:.1f}s  "
                  f"速率: {self._stats_hits / max(elapsed, 0.001):.1f} hits/s")
        print("[Bot] 已退出。")


# ── CLI 入口 ────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Aim Trainer 自动瞄准助手")
    parser.add_argument("--preset", choices=["kovaaks", "aimlab", "custom"],
                        default="kovaaks", help="颜色预设 (默认: kovaaks)")
    parser.add_argument("--priority", choices=["nearest", "largest", "center"],
                        default="nearest", help="目标优先级策略")
    parser.add_argument("--preview", action="store_true",
                        help="启动时打开调试预览窗口")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="鼠标速度倍率")
    parser.add_argument("--smooth-steps", type=int, default=3,
                        help="平滑移动步数 (1=瞬移)")
    parser.add_argument("--min-area", type=int, default=30,
                        help="最小目标面积阈值")
    parser.add_argument("--max-area", type=int, default=80000,
                        help="最大目标面积阈值")
    parser.add_argument("--min-circularity", type=float, default=0.30,
                        help="最低圆度阈值 (0~1)")
    parser.add_argument("--region", type=str, default=None,
                        help="截屏区域: left,top,width,height (如 0,0,1920,1080)")

    args = parser.parse_args()

    cfg = BotConfig()
    cfg.priority = args.priority
    cfg.show_preview = args.preview
    cfg.mouse_speed = args.speed
    cfg.smooth_steps = args.smooth_steps
    cfg.min_target_area = args.min_area
    cfg.max_target_area = args.max_area
    cfg.min_circularity = args.min_circularity

    if args.region:
        parts = [int(x) for x in args.region.split(",")]
        if len(parts) == 4:
            cfg.capture_region = {
                "left": parts[0], "top": parts[1],
                "width": parts[2], "height": parts[3],
            }

    from config import (KOVAAKS_ORANGE, AIMLAB_BLUE,
                         RED_TARGET_LOW, RED_TARGET_HIGH, YELLOW_TARGET)

    presets = {
        "kovaaks": [KOVAAKS_ORANGE, RED_TARGET_LOW, RED_TARGET_HIGH],
        "aimlab": [AIMLAB_BLUE],
        "custom": cfg.color_ranges,
    }
    cfg.color_ranges = presets[args.preset]

    bot = AimBot(cfg)
    bot.run()


if __name__ == "__main__":
    main()
