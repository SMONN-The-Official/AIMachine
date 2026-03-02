"""
高性能屏幕捕获模块。
使用 mss 进行低延迟截屏，返回 BGR numpy 数组供 OpenCV 处理。
"""

import numpy as np
import mss
import mss.tools

from config import BotConfig


class ScreenCapture:

    def __init__(self, cfg: BotConfig):
        self._sct = mss.mss()
        self._cfg = cfg
        self._region = self._build_region()

    def _build_region(self) -> dict:
        """根据配置或显示器信息构建截屏区域。"""
        mon = self._sct.monitors[self._cfg.monitor_index]
        region = self._cfg.capture_region.copy()
        if region["width"] == 0 or region["height"] == 0:
            region = {
                "top": mon["top"],
                "left": mon["left"],
                "width": mon["width"],
                "height": mon["height"],
            }
        return region

    @property
    def region(self) -> dict:
        return self._region

    @region.setter
    def region(self, value: dict):
        self._region = value

    @property
    def offset(self):
        """截屏区域左上角相对于屏幕的偏移，用于坐标映射。"""
        return self._region["left"], self._region["top"]

    def grab(self) -> np.ndarray:
        """截取一帧并返回 BGR 格式的 numpy 数组。"""
        raw = self._sct.grab(self._region)
        # mss 返回 BGRA，去掉 Alpha 通道
        frame = np.array(raw, dtype=np.uint8)[:, :, :3]
        return frame

    def close(self):
        self._sct.close()
