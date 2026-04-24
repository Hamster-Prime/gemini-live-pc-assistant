# Gemini Live PC Assistant

基于 Google Gemini Live API 的 Windows 电脑语音助手。通过麦克风与 Gemini 实时对话，用语音控制鼠标、键盘、打开/关闭应用、截屏等操作。

## 功能特性

- **实时语音对话**：通过 Gemini Live API 实现低延迟双向语音交互
- **唤醒词检测**：基于能量 VAD（语音活动检测），无需额外唤醒词模型
- **热键控制**：默认 `Ctrl+Space` 切换手动监听模式
- **PC 操控工具**（49 个）：
  - 鼠标：click、double_click、right_click、move、scroll、drag、wait_and_click
  - 键盘：type_text（支持中文）、press_key、hotkey、type_keys
  - 便捷：select_all、undo、redo、copy、paste、save_file、close_tab、new_tab
  - 应用：open_app、close_app
  - 窗口：minimize、maximize、restore、focus_window、list_windows、switch_window、lock_screen
  - 信息：screenshot、get_screen_info、get_mouse_position、get_pixel_color、get_clipboard、set_clipboard
  - 系统：get_volume、set_volume、get_system_info、get_battery_status、get_time、list_processes、kill_process
  - 文件：read_file、write_file、list_directory
  - 网络：open_url、search_web
  - 命令：run_command（内置危险命令过滤）
  - 音频：list_audio_devices
- **系统托盘**：pystray 托盘图标，包含设置和退出菜单
- **悬浮状态窗**：半透明悬浮窗显示当前状态、用户和助手文本（可拖拽）
- **静音控制**：`Ctrl+M` 快速切换麦克风静音
- **Session Resumption**：支持 Gemini Live API 会话恢复，断线重连时保持上下文
- **FAILSAFE**：pyautogui FAILSAFE 已启用，鼠标移到左上角可中断

## 系统要求

- Windows 10/11
- Python 3.10+
- 麦克风和扬声器
- Gemini API Key

## 安装

```bash
# 克隆项目
cd gemini-live-pc-assistant

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

## 配置

### 方式一：环境变量

```bash
set GEMINI_API_KEY=your_api_key_here
```

### 方式二：设置窗口

首次运行后，通过系统托盘 → 设置 填写 API Key。

### 方式三：配置文件

编辑 `assistant_config.json`（首次运行自动生成）。

## 运行

```bash
python main.py
```

启动后：
1. 系统托盘出现圆形图标（灰色=未连接，绿色=已连接）
2. 悬浮状态窗显示在屏幕左上角（可拖拽）
3. 连接 Gemini 后自动进入聆听状态
4. 按 `Ctrl+Space` 开始/停止手动监听
5. 对着麦克风说话即可与 Gemini 交互

## 使用说明

### 基本交互

- 助手连接后会持续监听麦克风
- 当检测到语音活动时，自动将音频发送给 Gemini
- Gemini 可以调用工具操控电脑，如"帮我打开记事本"、"点击屏幕中央"

### 热键操作

- `Ctrl+Space`：切换手动监听模式（默认超时 8 秒）

### 语音指令示例

- "打开记事本"
- "帮我截个屏"
- "点击坐标 500, 300"
- "按下回车键"
- "按 Ctrl+S 保存"
- "关闭计算器"
- "把鼠标移到屏幕中间"
- "向上滚动 5 格"

### 安全机制

- **pyautogui FAILSAFE**：快速将鼠标移到屏幕左上角可立即中断自动化操作
- **危险操作确认**：助手在执行危险操作前会先用语音确认

## 配置参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `api_key` | `""` | Gemini API Key（也可通过环境变量 `GEMINI_API_KEY` 设置） |
| `model` | `gemini-3.1-flash-live-preview` | Gemini 模型名称 |
| `hotkey` | `ctrl+space` | 切换手动监听的热键 |
| `wake_word` | `小助手` | 唤醒词（用于系统提示词） |
| `vad_threshold` | `180.0` | VAD 能量阈值 |
| `vad_multiplier` | `2.2` | VAD 噪声倍率 |
| `vad_attack_ms` | `150` | 语音开始检测时间 |
| `vad_release_ms` | `900` | 语音结束检测时间 |
| `pre_roll_ms` | `300` | 预缓冲时间 |
| `manual_listen_timeout` | `8.0` | 手动监听超时（秒） |
| `input_rate` | `16000` | 输入音频采样率 |
| `output_rate` | `24000` | 输出音频采样率 |
| `chunk_ms` | `30` | 音频块时长（毫秒） |
| `input_device_index` | `-1` | 输入设备索引（-1=系统默认） |
| `output_device_index` | `-1` | 输出设备索引（-1=系统默认） |
| `reconnect_initial_delay` | `2.0` | 重连初始延迟（秒） |
| `reconnect_max_delay` | `12.0` | 重连最大延迟（秒） |
| `screenshot_dir` | `runtime/screenshots` | 截图保存目录 |

## 项目结构

```
gemini-live-pc-assistant/
├── main.py              # 主入口，协调所有子系统
├── config.py            # 配置管理（dataclass + JSON 持久化）
├── audio_stream.py      # PyAudio 音频流管理（输入/输出/重采样）
├── gemini_session.py    # Gemini Live API 会话管理
├── tools.py             # 工具注册与分发（49 个 PC 控制工具）
├── pc_control.py        # PC 控制实现（pyautogui）
├── wake_word.py         # 基于能量的 VAD 唤醒检测
├── tray.py              # pystray 系统托盘
├── gui.py               # tkinter 设置窗口 + 悬浮状态窗
├── requirements.txt     # Python 依赖
└── README.md            # 本文件
```

## 常见问题

### Q: 连接失败？

检查 API Key 是否正确，网络是否可以访问 Google API。助手会在断开后自动重连。

### Q: 麦克风没声音？

检查系统麦克风权限，或在设置中调整 `input_device_index` 指定正确的输入设备。

### Q: 说话没反应？

调整 `vad_threshold`（降低阈值更灵敏，升高阈值更迟钝）。可通过设置窗口实时调整。

### Q: 如何停止自动化操作？

快速将鼠标移到屏幕左上角（pyautogui FAILSAFE），或按 `Ctrl+C` 中断终端。

## 许可

MIT License
