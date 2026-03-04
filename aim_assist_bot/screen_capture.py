"""
高性能屏幕捕获模块。

后端优先级（Windows）：
  1. dxcam  — DXGI Desktop Duplication，直接从 GPU 输出缓冲区读帧
             能正确捕获 DirectX 全屏/无边框游戏画面，延迟 < 1ms
  2. mss    — GDI BitBlt，仅适用于桌面窗口或无边框窗口
             无法捕获 DirectX 独占全屏游戏（会截到黑屏或桌面缓存）

Linux / macOS：
  仅 mss（dxcam 仅支持 Windows）

返回 BGR numpy 数组供 OpenCV 处理。
"""

import sys
import numpy as np

from config import BotConfig

_IS_WIN32 = sys.platform == "win32"


class ScreenCapture:

    def __init__(self, cfg: BotConfig):
        self._cfg = cfg
        self._backend_name = "unknown"

        # 后端初始化
        self._dxcam_device = None
        self._mss_device = None

        if _IS_WIN32 and not cfg.force_mss:
            self._try_init_dxcam()

        if self._dxcam_device is None:
            self._init_mss()

    # ── dxcam 后端 ──────────────────────────────────────────────
    def _try_init_dxcam(self):
        try:
            import dxcam
            cam = dxcam.create(output_color="BGR")
            if cam is None:
                print("[截屏] dxcam 创建失败，回退到 mss")
                return
            self._dxcam_device = cam
            self._backend_name = "dxcam (DXGI)"
            print(f"[截屏] 使用 dxcam (DXGI Desktop Duplication)")
        except ImportError:
            print("[截屏] dxcam 未安装，回退到 mss")
            print("       建议安装: pip install dxcam")
        except Exception as e:
            print(f"[截屏] dxcam 初始化异常: {e}，回退到 mss")

    # ── mss 后端 ────────────────────────────────────────────────
    def _init_mss(self):
        import mss
        self._mss_device = mss.mss()
        self._mss_region = self._build_mss_region()
        self._backend_name = "mss (GDI)"
        if _IS_WIN32:
            print(f"[截屏] 使用 mss (GDI) — 注意: 可能无法捕获 DirectX 全屏游戏")
            print(f"       若截屏异常，请将游戏切换为「无边框窗口」模式")
            print(f"       或安装 dxcam: pip install dxcam")

    def _build_mss_region(self) -> dict:
        mon = self._mss_device.monitors[self._cfg.monitor_index]
        region = self._cfg.capture_region.copy()
        if region["width"] == 0 or region["height"] == 0:
            region = {
                "top": mon["top"],
                "left": mon["left"],
                "width": mon["width"],
                "height": mon["height"],
            }
        return region

    # ── 属性 ────────────────────────────────────────────────────
    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def region(self) -> dict:
        if self._mss_device is not None:
            return self._mss_region
        r = self._cfg.capture_region
        return r

    @region.setter
    def region(self, value: dict):
        if self._mss_device is not None:
            self._mss_region = value

    @property
    def offset(self):
        """截屏区域左上角相对于屏幕的偏移，用于坐标映射。"""
        r = self.region
        return r["left"], r["top"]

    # ── 截帧 ────────────────────────────────────────────────────
    def grab(self) -> np.ndarray:
        """截取一帧并返回 BGR 格式的 numpy 数组。"""
        if self._dxcam_device is not None:
            return self._grab_dxcam()
        return self._grab_mss()

    def _grab_dxcam(self) -> np.ndarray:
        r = self._cfg.capture_region
        left, top = r["left"], r["top"]
        right, bottom = left + r["width"], top + r["height"]
        region = (left, top, right, bottom)

        frame = self._dxcam_device.grab(region=region)
        if frame is None:
            # dxcam 在无新帧时返回 None，短暂重试
            import time
            for _ in range(10):
                time.sleep(0.005)
                frame = self._dxcam_device.grab(region=region)
                if frame is not None:
                    break
        if frame is None:
            # 最终回退：返回黑帧避免崩溃
            return np.zeros(
                (r["height"], r["width"], 3), dtype=np.uint8
            )
        return np.ascontiguousarray(frame)

    def _grab_mss(self) -> np.ndarray:
        raw = self._mss_device.grab(self._mss_region)
        # mss 返回 BGRA，去掉 Alpha 通道
        frame = np.array(raw, dtype=np.uint8)[:, :, :3]
        return frame

    # ── 关闭 ────────────────────────────────────────────────────
    def close(self):
        if self._dxcam_device is not None:
            try:
                del self._dxcam_device
            except Exception:
                pass
            self._dxcam_device = None
        if self._mss_device is not None:
            self._mss_device.close()
            self._mss_device = None
