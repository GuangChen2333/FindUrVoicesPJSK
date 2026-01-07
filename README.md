# FindUrVoicesPJSK
《世界计划 : 缤纷舞台》单角色语音数据集一键获取工具，基于 Sekai-World 数据库。  
A one-click downloader for a single Project Sekai character’s voice dataset using the Sekai-World database.

## 特性 Features
- 支持独唱、资料语音、卡片语音等多种内容，按角色一键批量下载。
- 连接复用 + 小规模并发（可配）加速下载，HTTP/2 & 自定义 User-Agent。
- 元数据 30 天本地缓存，启动更快。
- tqdm 进度条展示（卡片总进度 + profile 单独进度）。
- 自动生成文本清单 `manifest.list`，可用脚本重写为 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 格式。

## 快速开始 Quick Start
- 直接下载最新发行版并执行：<https://github.com/GuangChen2333/FindUrVoicesPJSK/releases/latest>
- 运行后按提示选择模式、角色，输入卡片语音数量上限（如 800），即可开始下载。

### 从源码运行 From Source
```bash
poetry install
poetry run python main.py
```
可选参数：
- `wait_time`：请求间隔，默认 `0.3`（在 `main.py` 调整）。
- `download_workers`：并发数，默认 `5`。

## Manifest 重写 GPT-SoVITS 格式
使用脚本将 `manifest.list` 转为 `folder/filename|<id>|ja|content` 格式：
```bash
python scripts/rewrite_manifest.py <manifest_path> <target_folder> <character_id>
```
示例：
```bash
python scripts/rewrite_manifest.py output/dataset_4/manifest.list output/normalized shiho_hinomori
```
脚本会复用原始文件名，写回同一 `manifest.list`（目标文件夹自动创建）。

## 支持的下载内容 Supported Content
- 独唱 Solo songs
- 纯音频 Pure voices
- 角色资料音频 Profile voices
- 角色卡片音频 Card voices
