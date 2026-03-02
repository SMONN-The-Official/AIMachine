# Aim Trainer 自动瞄准助手

基于 **OpenCV 计算机视觉** 的屏幕目标检测与自动点击工具，适用于 Kovaak's / Aim Lab 等瞄准训练软件。

## 工作原理

```
屏幕截取 (mss) → HSV 颜色分割 → 形态学降噪 → 轮廓检测 → 面积/圆度过滤 → 优先级排序 → 鼠标移动+点击 → 循环
```

1. **屏幕捕获** — 使用 `mss` 库以极低延迟截取游戏画面
2. **颜色分割** — 将 BGR 图像转为 HSV 色彩空间，按预设颜色范围提取目标掩码
3. **形态学处理** — 开/闭运算去除噪点和填充空洞
4. **轮廓分析** — 查找外轮廓，根据面积和圆度过滤有效目标
5. **优先级排序** — 支持"最近优先"、"最大优先"、"靠近中心优先"三种策略
6. **鼠标控制** — 将目标帧坐标映射到屏幕坐标，移动光标并点击
7. **循环执行** — 不断重复以上步骤，直到手动暂停或训练结束

## 安装

### 环境要求
- Python 3.10+
- Windows 10/11（推荐，支持 win32 原生鼠标 API）
- Linux / macOS 也可运行（使用 pyautogui 后端）

### 安装依赖

```bash
cd aim_assist_bot
pip install -r requirements.txt
```

> **Linux 额外依赖**：`sudo apt install python3-tk python3-dev scrot`

## 快速开始

### 1. 默认运行（Kovaak's 预设）

```bash
python main.py
```

### 2. 使用 Aim Lab 预设

```bash
python main.py --preset aimlab
```

### 3. 自定义参数

```bash
python main.py --preset kovaaks --priority nearest --preview --smooth-steps 2 --min-area 50
```

### 4. 指定截屏区域

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

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--preset` | 颜色预设：`kovaaks` / `aimlab` / `custom` | `kovaaks` |
| `--priority` | 优先级：`nearest` / `largest` / `center` | `nearest` |
| `--preview` | 启动时开启调试预览 | 关闭 |
| `--speed` | 鼠标速度倍率 | `1.0` |
| `--smooth-steps` | 平滑移动步数（1 = 瞬移） | `3` |
| `--min-area` | 最小目标面积（像素²） | `30` |
| `--max-area` | 最大目标面积（像素²） | `80000` |
| `--min-circularity` | 最低圆度阈值（0~1） | `0.30` |
| `--region` | 截屏区域 `left,top,width,height` | 全屏 |

## 颜色校准

如果默认颜色预设不能正确识别目标：

1. 启动程序：`python main.py --preview`
2. 按 **F2** 暂停自动瞄准
3. 将鼠标光标移动到训练软件中的目标上方
4. 按 **F5** 进行颜色取样
5. 程序会在终端打印出推荐的 HSV 颜色范围，并临时应用
6. 按 **F2** 恢复自动瞄准，测试效果
7. 满意后将颜色范围写入 `config.py` 中永久保存

## 配置文件

编辑 `config.py` 可以精细调整所有参数：

```python
from config import BotConfig, ColorRange

cfg = BotConfig()

# 自定义颜色范围
cfg.color_ranges = [
    ColorRange("my_target", (10, 150, 150), (25, 255, 255)),
]

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
├── main.py              # 主程序入口与主循环
├── config.py            # 配置参数与颜色预设
├── screen_capture.py    # 屏幕捕获模块
├── target_detector.py   # 目标检测模块（OpenCV）
├── mouse_controller.py  # 鼠标控制模块（跨平台）
├── requirements.txt     # Python 依赖
└── README.md            # 本文件
```

## 调试技巧

- 使用 `--preview` 参数开启实时预览窗口，查看检测效果
- 按 F3 可以随时切换预览窗口的开/关
- 如果检测到太多噪点，提高 `--min-area` 或 `--min-circularity`
- 如果目标检测不到，降低 `--min-area` 和 `--min-circularity`，或使用 F5 重新校准颜色
- 退出时会打印命中统计（命中数、用时、命中速率）
