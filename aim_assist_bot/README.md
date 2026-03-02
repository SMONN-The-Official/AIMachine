# Aim Trainer 自动瞄准助手

基于 **OpenCV 计算机视觉** 的屏幕目标检测与自动点击工具，适用于 Kovaak's / Aim Lab 等瞄准训练软件。

## 工作原理

```
屏幕截取 (mss)
  ├─ HSV 颜色分割 ──────→ 彩色目标掩码 ─┐
  └─ 亮度差异检测 ──────→ 白色目标掩码 ─┤
                                         ├─→ 合并 → 形态学降噪 → 轮廓检测
                                         │     → 面积/圆度过滤 → 优先级排序
                                         │     → 鼠标移动+点击 → 循环
```

### 双模式检测

| 模式 | 适用场景 | 原理 |
|------|----------|------|
| **HSV 颜色分割** | 橙、红、蓝等彩色目标 | 在 HSV 色彩空间按预设范围提取掩码 |
| **亮度差异检测** | 白色 / 高亮目标 | 对比像素亮度与局部背景亮度的差异，提取显著亮点 |

两种模式可同时启用，掩码取并集后统一走轮廓分析。

## 安装

### 环境要求
- Python 3.10+
- Windows 10/11（推荐，支持 win32 原生鼠标 API 和 GetAsyncKeyState 热键）
- Linux / macOS 也可运行（使用 pyautogui + pynput 后端）

### 安装依赖

```bash
cd aim_assist_bot
pip install -r requirements.txt
```

> **Linux 额外依赖**：`sudo apt install python3-tk python3-dev scrot`

## 快速开始

### 1. Kovaak's 默认（橙红色目标）

```bash
python main.py
```

### 2. Aim Lab 默认（蓝色目标）

```bash
python main.py --preset aimlab
```

### 3. 白色目标

```bash
python main.py --preset white
```

### 4. 全部颜色 + 白色（通吃模式）

```bash
python main.py --preset all --preview
```

### 5. 自定义参数

```bash
python main.py --preset white --priority nearest --preview \
    --smooth-steps 2 --min-area 50 \
    --brightness-threshold 200 --brightness-diff 30
```

### 6. 指定截屏区域

```bash
python main.py --region 0,0,1920,1080
```

## 快捷键

| 按键 | 功能 |
|------|------|
| **F2** | 启动 / 暂停自动瞄准 |
| **F3** | 切换调试预览窗口 |
| **F4** | 退出程序 |
| **F5** | 颜色取样校准（将光标放在目标上按下） |

### 热键后端

| 平台 | 后端 | 说明 |
|------|------|------|
| Windows | `GetAsyncKeyState` 轮询 | 直接查询硬件按键状态，游戏全屏可用，无需管理员 |
| Linux/macOS | `pynput` Listener | 需要桌面环境 |

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--preset` | 颜色预设：`kovaaks`/`aimlab`/`white`/`all`/`custom` | `kovaaks` |
| `--priority` | 优先级：`nearest`/`largest`/`center` | `nearest` |
| `--preview` | 启动时开启调试预览 | 关闭 |
| `--speed` | 鼠标速度倍率 | `1.0` |
| `--smooth-steps` | 平滑移动步数（1 = 瞬移） | `3` |
| `--min-area` | 最小目标面积（像素²） | `30` |
| `--max-area` | 最大目标面积（像素²） | `80000` |
| `--min-circularity` | 最低圆度阈值（0~1） | `0.30` |
| `--region` | 截屏区域 `left,top,width,height` | 全屏 |
| `--brightness-threshold` | 亮度检测绝对阈值 (0~255) | `220` |
| `--brightness-diff` | 亮度差值阈值（与局部背景对比） | `40` |

## 颜色校准

如果默认颜色预设不能正确识别目标：

1. 启动程序：`python main.py --preview`
2. 按 **F2** 暂停自动瞄准
3. 将鼠标光标移动到训练软件中的目标上方
4. 按 **F5** 进行颜色取样
5. 程序会自动判断目标类型：
   - **低饱和度高亮度** → 自动切换为亮度检测模式（白色目标）
   - **高饱和度** → 应用新的 HSV 颜色范围（彩色目标）
6. 按 **F2** 恢复自动瞄准，测试效果
7. 满意后将参数写入 `config.py` 中永久保存

## 配置文件

编辑 `config.py` 可以精细调整所有参数：

```python
from config import BotConfig, ColorRange

cfg = BotConfig()

# 白色目标：启用亮度检测
cfg.enable_brightness_detect = True
cfg.brightness_threshold = 210
cfg.brightness_diff_threshold = 35
cfg.color_ranges = []               # 纯亮度模式，不用颜色

# 或者：彩色 + 白色同时检测
cfg.color_ranges = [
    ColorRange("my_orange", (5, 120, 120), (20, 255, 255)),
]
cfg.enable_brightness_detect = True  # 同时启用亮度检测

# 调整检测灵敏度
cfg.min_target_area = 50
cfg.min_circularity = 0.4

# 鼠标行为
cfg.smooth_steps = 2
cfg.click_delay = 0.005
```

## 项目结构

```
aim_assist_bot/
├── main.py              # 主程序入口、CLI 参数、主循环
├── config.py            # 配置参数与颜色预设
├── screen_capture.py    # 屏幕捕获模块 (mss)
├── target_detector.py   # 目标检测模块（HSV 颜色 + 亮度差异双模式）
├── mouse_controller.py  # 鼠标控制模块（Win32 / pyautogui）
├── hotkey_manager.py    # 热键管理器（Win32 轮询 / pynput）
├── requirements.txt     # Python 依赖
└── README.md            # 本文件
```

## 调试技巧

- 使用 `--preview` 参数开启实时预览窗口，查看检测效果
- 按 F3 可以随时切换预览窗口的开/关
- 如果检测到太多噪点，提高 `--min-area` 或 `--min-circularity`
- 如果白色目标检测不到，降低 `--brightness-threshold`（如 190）
- 如果白色背景被误检，提高 `--brightness-diff`（如 60）
- 退出时会打印命中统计（命中数、用时、命中速率）
