# ConfigCleaner

网络设备配置脚本解析工具，支持拖入脚本文件，自动识别步骤并提取配置命令、报文数据。

## 功能

- **步骤解析** — 自动识别脚本中的 Step 标记，按步骤分组展示
- **命令提取** — 从 `send_expect` 等交互中提取实际下发的 CLI 命令，过滤 `cat`/`ps`/`grep` 等非配置命令
- **报文提取** — 解析 `#Proc` 十六进制报文数据，支持文本查看和导出 PCAP
- **拖拽加载** — 支持拖拽脚本文件或点击选择

## 运行方式

### 源码运行

```bash
pip install tkinterdnd2
python main.py
```

### 打包为 EXE

```bash
pip install pyinstaller tkinterdnd2
pyinstaller ConfigCleaner-V3.1.spec
```

## 项目结构

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序（GUI + 解析逻辑） |
| `icon_data.py` | 图标 Base64 数据 |
| `network.ico` | 应用图标 |
| `ConfigCleaner-V3.1.spec` | PyInstaller 打包配置（最新） |

## 使用方式

1. 将网络脚本文件（`.txt`）拖入窗口或点击选择
2. 勾选需要处理的步骤
3. 选择输出模式：提取命令 / 报文文本 / 导出 PCAP
4. 点击执行，结果可复制到剪贴板
