"""
目标检测与自动瞄准配置模块。
支持 Kovaak's / Aim Lab 等瞄准训练软件中常见的目标颜色与形状。
"""

from dataclasses import dataclass, field
from typing import Tuple, List


@dataclass
class ColorRange:
    """HSV 颜色范围，用于目标筛选。"""
    name: str
    lower: Tuple[int, int, int]
    upper: Tuple[int, int, int]


# ── 预设颜色方案 ──────────────────────────────────────────────────
# Kovaak's 默认目标（橙红色球体）
KOVAAKS_ORANGE = ColorRange("kovaaks_orange", (5, 120, 120), (20, 255, 255))
# Aim Lab 默认目标（蓝色球体）
AIMLAB_BLUE = ColorRange("aimlab_blue", (90, 120, 100), (130, 255, 255))
# 常见红色目标
RED_TARGET_LOW = ColorRange("red_low", (0, 130, 130), (10, 255, 255))
RED_TARGET_HIGH = ColorRange("red_high", (160, 130, 130), (180, 255, 255))
# 常见黄色目标
YELLOW_TARGET = ColorRange("yellow", (20, 100, 100), (35, 255, 255))
# 粉紫色目标
PINK_TARGET = ColorRange("pink", (140, 80, 100), (170, 255, 255))
# 白色目标（低饱和度高亮度）—— 仅作为辅助，建议配合亮度检测使用
WHITE_TARGET = ColorRange("white", (0, 0, 200), (180, 50, 255))


@dataclass
class BotConfig:
    """全局可调参数。"""

    # ── 屏幕捕获 ──────────────────────────────────────────────────
    capture_region: dict = field(default_factory=lambda: {
        "top": 0, "left": 0, "width": 1920, "height": 1080
    })
    monitor_index: int = 1  # mss 显示器编号，1 = 主显示器
    force_mss: bool = False # True=强制用 mss，False=Windows 上优先 dxcam

    # ── 颜色检测 ──────────────────────────────────────────────────
    color_ranges: List[ColorRange] = field(default_factory=lambda: [
        KOVAAKS_ORANGE,
    ])

    # ── 亮度差异检测（白色 / 高亮目标）────────────────────────────
    enable_brightness_detect: bool = False
    brightness_threshold: int = 220       # 绝对亮度阈值（0~255）
    brightness_diff_threshold: int = 40   # 与局部背景的亮度差阈值
    brightness_bg_kernel: int = 51        # 局部背景模糊核大小（越大越平滑）

    # ── 目标筛选 ──────────────────────────────────────────────────
    min_target_area: int = 30       # 最小轮廓面积（像素²），过滤噪点
    max_target_area: int = 80000    # 最大轮廓面积，过滤背景大色块
    min_circularity: float = 0.30   # 最低圆度阈值（0~1），球形目标通常 > 0.5
    morph_kernel_size: int = 3      # 形态学操作核大小

    # ── 鼠标控制 ──────────────────────────────────────────────────
    game_mode: bool = True          # True=SendInput 相对位移（游戏），False=绝对坐标（桌面）
    sensitivity: float = 1.0        # 灵敏度倍率：发送的像素偏移 = 检测偏移 × sensitivity
    click_hold_time: float = 0.03   # 鼠标左键按住时长（秒），太短游戏不认
    move_click_gap: float = 0.01    # 移动完成到点击之间的间隔（秒）
    post_click_cooldown: float = 0.06  # 点击后冷却（秒），等目标消失再截下一帧
    dead_zone: int = 3              # 死区半径（像素），目标在此范围内不移动直接点击
    max_move_px: int = 500          # 单帧最大移动量（像素），超过视为误检直接丢弃
    use_smooth_move: bool = False   # 是否分步发送位移（平滑移动）
    smooth_steps: int = 3           # 平滑移动步数

    # ── 优先级策略 ──────────────────────────────────────────────
    priority: str = "nearest"       # nearest / largest / center

    # ── 性能 ─────────────────────────────────────────────────────
    loop_delay: float = 0.001       # 主循环间隔秒数
    show_preview: bool = False      # 是否显示调试预览窗口

    # ── 灵敏度自动校准 ──────────────────────────────────────────
    calibrate_move_px: int = 400    # 校准测试位移量（mickey），越大越精确
    calibrate_settle_ms: float = 0.25  # 每帧采样间隔（秒），需足够让游戏渲染

    # ── 快捷键 ─────────────────────────────────────────────────
    toggle_key: str = "f2"          # 启停热键
    exit_key: str = "f4"            # 退出热键
    preview_key: str = "f3"         # 切换预览窗口热键
    calibrate_key: str = "f5"       # 颜色取样校准热键
    sens_calibrate_key: str = "f6"  # 灵敏度自动校准热键
