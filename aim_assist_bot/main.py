#!/usr/bin/env python3
"""
Aim Trainer 自动瞄准助手 —— 主程序入口。

功能：
  - 实时捕获屏幕画面
  - 通过颜色 + 亮度双模式检测识别训练目标（含白色小球）
  - 自动移动光标至目标中心并点击
  - 循环锁定下一目标直至训练结束

快捷键（默认）：
  F2  启动 / 暂停
  F3  切换调试预览窗口
  F4  退出
  F5  颜色取样校准
"""

import sys
import time

import cv2
import numpy as np

from config import BotConfig, ColorRange
from screen_capture import ScreenCapture
from target_detector import TargetDetector
from mouse_controller import MouseController
from hotkey_manager import HotkeyManager


class AimBot:

    def __init__(self, cfg: BotConfig | None = None):
        self.cfg = cfg or BotConfig()
        self.capture = ScreenCapture(self.cfg)
        self.detector = TargetDetector(self.cfg)
        self.mouse = MouseController(self.cfg)
        self.hotkeys = HotkeyManager()

        self._active = False
        self._show_preview = self.cfg.show_preview
        self._alive = True

        self._stats_hits = 0
        self._stats_start: float = 0

    # ── 快捷键回调 ──────────────────────────────────────────────
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
        frame = self.capture.grab()
        mx, my = self.mouse.get_position()
        ox, oy = self.capture.offset
        fx, fy = mx - ox, my - oy

        h, w = frame.shape[:2]
        r = 10
        x1, y1 = max(0, fx - r), max(0, fy - r)
        x2, y2 = min(w, fx + r), min(h, fy + r)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            print("[校准] 取样区域无效，请将光标移到目标上再按 F5")
            return

        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mean_h = int(np.mean(hsv_roi[:, :, 0]))
        mean_s = int(np.mean(hsv_roi[:, :, 1]))
        mean_v = int(np.mean(hsv_roi[:, :, 2]))

        margin_h, margin_s, margin_v = 12, 60, 60
        lower = (max(0, mean_h - margin_h),
                 max(0, mean_s - margin_s),
                 max(0, mean_v - margin_v))
        upper = (min(180, mean_h + margin_h),
                 min(255, mean_s + margin_s),
                 min(255, mean_v + margin_v))

        print(f"[校准] 采样 HSV 均值: H={mean_h} S={mean_s} V={mean_v}")
        print(f"[校准] 建议范围: lower={lower}, upper={upper}")

        # 低饱和度样本（白色/灰色）自动启用亮度检测
        if mean_s < 60 and mean_v > 180:
            self.cfg.enable_brightness_detect = True
            self.cfg.brightness_threshold = max(160, mean_v - 50)
            self.cfg.color_ranges = []
            print(f"[校准] 检测到低饱和度高亮目标，已切换为亮度检测模式")
            print(f"       亮度阈值={self.cfg.brightness_threshold}, "
                  f"差值阈值={self.cfg.brightness_diff_threshold}")
        else:
            new_range = ColorRange("calibrated", lower, upper)
            self.cfg.color_ranges = [new_range]
            print("[校准] 已临时应用新 HSV 颜色范围（重启后失效）")

    # ── 主循环 ──────────────────────────────────────────────────
    def run(self):
        self.hotkeys.register(self.cfg.toggle_key, self._toggle)
        self.hotkeys.register(self.cfg.exit_key, self._quit)
        self.hotkeys.register(self.cfg.preview_key, self._toggle_preview)
        self.hotkeys.register(self.cfg.calibrate_key, self._calibrate_color)
        self.hotkeys.start()

        self._alive = True
        self._print_banner()

        try:
            while self._alive:
                # 每帧都轮询热键（Win32 模式依赖此调用）
                self.hotkeys.poll()

                if not self._active:
                    time.sleep(0.02)
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

    def _print_banner(self):
        detect_mode = []
        if self.cfg.color_ranges:
            detect_mode.append(f"HSV颜色({', '.join(c.name for c in self.cfg.color_ranges)})")
        if self.cfg.enable_brightness_detect:
            detect_mode.append(f"亮度差异(阈值={self.cfg.brightness_threshold})")
        mode_str = " + ".join(detect_mode) or "无"

        print("=" * 60)
        print("  Aim Trainer 自动瞄准助手")
        print("=" * 60)
        print(f"  [{self.cfg.toggle_key.upper()}]  启动 / 暂停")
        print(f"  [{self.cfg.preview_key.upper()}]  切换调试预览")
        print(f"  [{self.cfg.calibrate_key.upper()}]  颜色取样校准")
        print(f"  [{self.cfg.exit_key.upper()}]  退出")
        print("-" * 60)
        print(f"  检测模式:   {mode_str}")
        print(f"  优先级策略: {self.cfg.priority}")
        print(f"  截屏区域:   {self.cfg.capture_region}")
        print(f"  热键后端:   {self.hotkeys.backend_name}")
        print("=" * 60)
        if self._active:
            print("自动瞄准已启动。")
        else:
            print(f"按 [{self.cfg.toggle_key.upper()}] 开始...")

    def _cleanup(self):
        self.capture.close()
        cv2.destroyAllWindows()
        self.hotkeys.stop()
        if self._stats_hits > 0 and self._stats_start > 0:
            elapsed = time.time() - self._stats_start
            print(f"\n[统计] 命中: {self._stats_hits}  "
                  f"用时: {elapsed:.1f}s  "
                  f"速率: {self._stats_hits / max(elapsed, 0.001):.1f} hits/s")
        print("[Bot] 已退出。")


# ── CLI 入口 ────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Aim Trainer 自动瞄准助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
颜色预设说明:
  kovaaks  - Kovaak's 默认橙红色目标
  aimlab   - Aim Lab 默认蓝色目标
  white    - 白色/高亮目标（亮度差异检测）
  all      - 同时启用所有颜色 + 亮度检测
  custom   - 使用 config.py 中的默认设置""",
    )
    parser.add_argument("--preset",
                        choices=["kovaaks", "aimlab", "white", "all", "custom"],
                        default="kovaaks", help="颜色预设 (默认: kovaaks)")
    parser.add_argument("--priority",
                        choices=["nearest", "largest", "center"],
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
                        help="截屏区域: left,top,width,height")
    parser.add_argument("--brightness-threshold", type=int, default=220,
                        help="亮度检测阈值 (0~255，默认 220)")
    parser.add_argument("--brightness-diff", type=int, default=40,
                        help="亮度差值阈值 (默认 40)")

    args = parser.parse_args()

    cfg = BotConfig()
    cfg.priority = args.priority
    cfg.show_preview = args.preview
    cfg.mouse_speed = args.speed
    cfg.smooth_steps = args.smooth_steps
    cfg.min_target_area = args.min_area
    cfg.max_target_area = args.max_area
    cfg.min_circularity = args.min_circularity
    cfg.brightness_threshold = args.brightness_threshold
    cfg.brightness_diff_threshold = args.brightness_diff

    if args.region:
        parts = [int(x) for x in args.region.split(",")]
        if len(parts) == 4:
            cfg.capture_region = {
                "left": parts[0], "top": parts[1],
                "width": parts[2], "height": parts[3],
            }

    from config import (KOVAAKS_ORANGE, AIMLAB_BLUE, WHITE_TARGET,
                         RED_TARGET_LOW, RED_TARGET_HIGH, YELLOW_TARGET)

    if args.preset == "kovaaks":
        cfg.color_ranges = [KOVAAKS_ORANGE, RED_TARGET_LOW, RED_TARGET_HIGH]
        cfg.enable_brightness_detect = False
    elif args.preset == "aimlab":
        cfg.color_ranges = [AIMLAB_BLUE]
        cfg.enable_brightness_detect = False
    elif args.preset == "white":
        cfg.color_ranges = [WHITE_TARGET]
        cfg.enable_brightness_detect = True
    elif args.preset == "all":
        cfg.color_ranges = [KOVAAKS_ORANGE, AIMLAB_BLUE,
                            RED_TARGET_LOW, RED_TARGET_HIGH,
                            YELLOW_TARGET, WHITE_TARGET]
        cfg.enable_brightness_detect = True
    # "custom" 使用 BotConfig 默认值

    bot = AimBot(cfg)
    bot.run()


if __name__ == "__main__":
    main()
