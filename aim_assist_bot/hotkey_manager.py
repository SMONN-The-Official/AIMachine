"""
跨平台热键管理器。

后端优先级：
  1. Win32 GetAsyncKeyState 轮询（Windows，无需管理员，游戏全屏可用）
  2. pynput Listener（Linux / macOS）

GetAsyncKeyState 是最可靠的 Windows 方案——它直接查询硬件按键状态，
不受窗口焦点、游戏反作弊钩子影响，也不需要管理员权限。
"""

import sys
import time
import threading
from typing import Callable, Dict, Optional

_IS_WIN32 = sys.platform == "win32"


# ── Virtual-Key 码映射 ──────────────────────────────────────────
_VK_MAP = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62,
    "numpad3": 0x63, "numpad4": 0x64, "numpad5": 0x65,
    "numpad6": 0x66, "numpad7": 0x67, "numpad8": 0x68,
    "numpad9": 0x69,
    "pause": 0x13, "capslock": 0x14, "scrolllock": 0x91,
}


class HotkeyManager:
    """
    统一热键接口。

    用法::

        hk = HotkeyManager()
        hk.register("f2", on_toggle)
        hk.register("f4", on_quit)
        hk.start()          # 启动后台线程（pynput 模式）

        # 主循环中每帧调用一次（Win32 轮询模式必需，pynput 模式可选）
        hk.poll()

        hk.stop()
    """

    def __init__(self):
        self._bindings: Dict[str, Callable] = {}
        self._backend: Optional[str] = None
        self._listener = None  # pynput Listener
        self._prev_state: Dict[int, bool] = {}  # Win32 轮询用
        self._started = False

    @property
    def backend_name(self) -> str:
        return self._backend or "none"

    # ── 注册 ────────────────────────────────────────────────────
    def register(self, key_name: str, callback: Callable):
        self._bindings[key_name.lower().strip()] = callback

    # ── 启动 ────────────────────────────────────────────────────
    def start(self):
        if self._started:
            return

        if _IS_WIN32:
            self._backend = "win32_poll"
            for name in self._bindings:
                vk = _VK_MAP.get(name)
                if vk is not None:
                    self._prev_state[vk] = False
            self._started = True
            print(f"[热键] 后端: Win32 GetAsyncKeyState 轮询")
            return

        # Linux / macOS → pynput
        try:
            from pynput import keyboard as pk
            from pynput.keyboard import Key

            key_obj_map: Dict[str, object] = {}
            for k in Key:
                key_obj_map[k.name.lower()] = k

            bound_keys = {}
            for name, cb in self._bindings.items():
                obj = key_obj_map.get(name)
                if obj is not None:
                    bound_keys[obj] = cb

            def _on_press(key):
                cb = bound_keys.get(key)
                if cb:
                    cb()

            self._listener = pk.Listener(on_press=_on_press)
            self._listener.daemon = True
            self._listener.start()
            self._backend = "pynput"
            self._started = True
            print(f"[热键] 后端: pynput Listener")
            return
        except Exception as e:
            print(f"[热键] pynput 初始化失败: {e}")

        self._backend = None
        print("[热键] 无可用后端，热键功能不可用")

    # ── 轮询（在主循环中每帧调用）─────────────────────────────
    def poll(self):
        """Win32 模式下检测按键边沿触发；pynput 模式无需调用但安全无害。"""
        if self._backend != "win32_poll":
            return

        import ctypes
        user32 = ctypes.windll.user32

        for name, cb in self._bindings.items():
            vk = _VK_MAP.get(name)
            if vk is None:
                continue
            # GetAsyncKeyState 最高位为 1 表示当前按下
            pressed = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            was_pressed = self._prev_state.get(vk, False)
            if pressed and not was_pressed:
                cb()
            self._prev_state[vk] = pressed

    # ── 停止 ────────────────────────────────────────────────────
    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._started = False
