"""
目标检测模块。

支持两种检测模式，可叠加使用：
  1. HSV 颜色分割 —— 适用于彩色目标（橙、红、蓝等）
  2. 亮度差异检测 —— 适用于白色 / 高亮目标（与周围背景对比度高的亮点）

两种模式的掩码取并集后，统一走轮廓分析 → 面积/圆度过滤 → 优先级排序。
"""

from typing import List, Tuple, Optional
import cv2
import numpy as np
import math

from config import BotConfig, ColorRange


class Target:
    """检测到的单个目标。"""
    __slots__ = ("cx", "cy", "area", "radius", "circularity", "contour")

    def __init__(self, cx: int, cy: int, area: float, radius: float,
                 circularity: float, contour: np.ndarray):
        self.cx = cx
        self.cy = cy
        self.area = area
        self.radius = radius
        self.circularity = circularity
        self.contour = contour


class TargetDetector:

    def __init__(self, cfg: BotConfig):
        self._cfg = cfg
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (cfg.morph_kernel_size, cfg.morph_kernel_size),
        )
        self._frame_center: Optional[Tuple[int, int]] = None

    # ── 主检测入口 ──────────────────────────────────────────────
    def detect(self, frame_bgr: np.ndarray) -> List[Target]:
        h, w = frame_bgr.shape[:2]
        self._frame_center = (w // 2, h // 2)

        combined_mask = np.zeros((h, w), dtype=np.uint8)

        # 模式 1：HSV 颜色范围检测
        if self._cfg.color_ranges:
            hsv_mask = self._detect_by_color(frame_bgr)
            combined_mask = cv2.bitwise_or(combined_mask, hsv_mask)

        # 模式 2：亮度差异检测（白色 / 高亮目标）
        if self._cfg.enable_brightness_detect:
            bright_mask = self._detect_by_brightness(frame_bgr)
            combined_mask = cv2.bitwise_or(combined_mask, bright_mask)

        # 形态学降噪
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, self._kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, self._kernel)

        contours, _ = cv2.findContours(
            combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        targets = self._filter_contours(contours)
        targets = self._sort_targets(targets)
        return targets

    # ── HSV 颜色检测 ────────────────────────────────────────────
    def _detect_by_color(self, frame_bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h, w = frame_bgr.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for cr in self._cfg.color_ranges:
            lower = np.array(cr.lower, dtype=np.uint8)
            upper = np.array(cr.upper, dtype=np.uint8)
            m = cv2.inRange(hsv, lower, upper)
            mask = cv2.bitwise_or(mask, m)
        return mask

    # ── 亮度差异检测（白色目标核心算法）─────────────────────────
    def _detect_by_brightness(self, frame_bgr: np.ndarray) -> np.ndarray:
        """
        检测亮度显著高于局部背景的区域。

        步骤：
          1. 转灰度 → 全局高阈值二值化，提取所有亮区
          2. 高斯模糊生成局部背景亮度图
          3. 计算差值图（像素亮度 - 局部背景），对差值做阈值过滤
          4. 两个掩码取交集，保证既"绝对亮"又"比周围亮"
        """
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # 绝对亮度阈值
        _, bright_abs = cv2.threshold(
            gray, self._cfg.brightness_threshold, 255, cv2.THRESH_BINARY,
        )

        # 局部背景亮度（大核高斯模糊）
        ksize = self._cfg.brightness_bg_kernel
        if ksize % 2 == 0:
            ksize += 1
        bg = cv2.GaussianBlur(gray, (ksize, ksize), 0)

        # 亮度差值 = 原图 - 背景，仅保留正差值
        diff = cv2.subtract(gray, bg)
        _, bright_diff = cv2.threshold(
            diff, self._cfg.brightness_diff_threshold, 255, cv2.THRESH_BINARY,
        )

        # 交集：既绝对亮、又比周围显著更亮
        mask = cv2.bitwise_and(bright_abs, bright_diff)
        return mask

    # ── 轮廓过滤 ────────────────────────────────────────────────
    def _filter_contours(self, contours) -> List[Target]:
        results: List[Target] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._cfg.min_target_area or area > self._cfg.max_target_area:
                continue

            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < self._cfg.min_circularity:
                continue

            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            (_, _), radius = cv2.minEnclosingCircle(cnt)

            results.append(Target(cx, cy, area, radius, circularity, cnt))
        return results

    # ── 优先级排序 ──────────────────────────────────────────────
    def _sort_targets(self, targets: List[Target]) -> List[Target]:
        if not targets:
            return targets

        strategy = self._cfg.priority

        if strategy == "nearest":
            cx0, cy0 = self._frame_center
            targets.sort(key=lambda t: (t.cx - cx0) ** 2 + (t.cy - cy0) ** 2)
        elif strategy == "largest":
            targets.sort(key=lambda t: t.area, reverse=True)
        elif strategy == "center":
            cx0, cy0 = self._frame_center
            targets.sort(key=lambda t: abs(t.cx - cx0) + abs(t.cy - cy0))

        return targets

    # ── 调试可视化 ──────────────────────────────────────────────
    def draw_debug(self, frame_bgr: np.ndarray, targets: List[Target]) -> np.ndarray:
        vis = frame_bgr.copy()
        for i, t in enumerate(targets):
            color = (0, 255, 0) if i == 0 else (0, 200, 255)
            cv2.circle(vis, (t.cx, t.cy), int(t.radius), color, 2)
            cv2.circle(vis, (t.cx, t.cy), 3, (0, 0, 255), -1)
            label = f"#{i} A={int(t.area)} C={t.circularity:.2f}"
            cv2.putText(vis, label, (t.cx + 8, t.cy - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        if self._frame_center:
            cv2.drawMarker(vis, self._frame_center, (255, 255, 255),
                           cv2.MARKER_CROSS, 20, 1)
        return vis

    def build_mask_preview(self, frame_bgr: np.ndarray) -> np.ndarray:
        """返回组合掩码的可视化图（用于调试校准）。"""
        h, w = frame_bgr.shape[:2]
        combined = np.zeros((h, w), dtype=np.uint8)

        if self._cfg.color_ranges:
            combined = cv2.bitwise_or(combined, self._detect_by_color(frame_bgr))
        if self._cfg.enable_brightness_detect:
            combined = cv2.bitwise_or(combined, self._detect_by_brightness(frame_bgr))

        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, self._kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, self._kernel)
        return cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
