"""
目标检测模块。
基于 HSV 颜色空间分割 + 轮廓分析，在每帧中定位所有目标并按优先级排序。
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

    def detect(self, frame_bgr: np.ndarray) -> List[Target]:
        """
        在一帧中检测所有目标。

        Parameters
        ----------
        frame_bgr : BGR 格式的截屏帧

        Returns
        -------
        按优先级排序的 Target 列表（索引 0 为最优先）
        """
        h, w = frame_bgr.shape[:2]
        self._frame_center = (w // 2, h // 2)

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        combined_mask = np.zeros((h, w), dtype=np.uint8)

        for cr in self._cfg.color_ranges:
            lower = np.array(cr.lower, dtype=np.uint8)
            upper = np.array(cr.upper, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, self._kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, self._kernel)

        contours, _ = cv2.findContours(
            combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        targets = self._filter_contours(contours)
        targets = self._sort_targets(targets)
        return targets

    def _filter_contours(self, contours) -> List[Target]:
        """根据面积和圆度筛选有效目标。"""
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

    def _sort_targets(self, targets: List[Target]) -> List[Target]:
        """按配置的优先级策略排序。"""
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

    def draw_debug(self, frame_bgr: np.ndarray, targets: List[Target]) -> np.ndarray:
        """在帧上绘制调试信息（轮廓、中心点、优先级编号）。"""
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
        """返回当前颜色过滤后的掩码图（用于校准调试）。"""
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h, w = frame_bgr.shape[:2]
        combined = np.zeros((h, w), dtype=np.uint8)
        for cr in self._cfg.color_ranges:
            lower = np.array(cr.lower, dtype=np.uint8)
            upper = np.array(cr.upper, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            combined = cv2.bitwise_or(combined, mask)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, self._kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, self._kernel)
        return cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
