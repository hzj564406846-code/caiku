---
name: video-generation-project
description: AI全自动视频生成器开发记录、当前状态、阻塞问题
type: project
originSessionId: 88c1b6f9-8c95-43c2-ac6c-dd35ec986fbf
---
## 项目目标
用 AI 全自动生成 PPT 风格知识视频（竖屏 1080×1920），用户只负责选题和最终审核，其余全部自动化。

## 版本演进

| 版本 | 方案 | 结果 |
|------|------|------|
| v1 (build_video.py) | 纯色背景 + PIL 文字 | 太简陋 |
| v2 (build_video_v2.py) | PIL 渐变背景 + 圆角卡片 + 逐条动画 | 画面干，缺少设计元素 |
| v3 (build_video_v3.py) | PIL 4套背景模板 + 3种布局 + 装饰元素 | 布局溢出、PIL 天花板低 |
| v4 (build_video_v4.py) | HTML/CSS + Edge无头截图 + SVG图标 + edge-tts + SRT字幕 | 排版精确，但缺真实素材 |
| v5 (build_video_v5.py) | ComfyUI AI背景 + HTML/CSS + Edge截图 + 字幕 | 画面效果不可控（模型不对+看不到图） |

## 关键技术栈
- **画面生成**: PIL / HTML+CSS / ComfyUI（Flux dev / SD 1.5）
- **截图**: Edge headless (`C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`)
- **配音**: edge-tts (zh-CN-YunxiNeural)
- **字幕**: edge-tts VTT → SRT → ffmpeg subtitles filter
- **合成**: ffmpeg (concat filter + subtitles burn-in)
- **ffmpeg**: `D:/AI/ffmpeg/ffmpeg-2025-02-13-git-19a2d26177-full_build/bin/`

## ComfyUI 环境
- **v1.7**: `D:/AI/ComfyUI-aki-v1.7/` — 有 Flux 模型（flux1-dev-kontext, flux1-fill）
- **windows_portable**: `D:/AI/ComfyUI_windows_portable/` — 有 SD 1.5 模型（majicMIX, cyberrealisticPony）
- 当前运行实例: windows_portable（端口 8188），但通过 extra_model_paths 也能看到 v1.7 的模型
- SD 1.5 模型是人物写真专用，不适合抽象背景
- Flux dev 用中文提示词效果差，英文提示词效果有改善但仍不理想

## 核心阻塞问题
**DeepSeek V4 Pro 是纯文本模型，看不到图片。**
- 用户需要每步看图判断 → 体验极差，不如自己做
- 换成 Claude 多模态模型可解决，但 Anthropic 官方 API 封禁中国 IP
- 尝试用中转站（AgentRouter/AnyRouter）注册失败，用户放弃
- 备选：本地 Ollama 多模态模型（qwen2.5-vl:7b）、通义千问 VL API

## 用户反馈总结
- "画面很干，缺少真实图片素材"
- "排盘完全是乱来，有溢出屏幕外的"
- "字幕跟声音也没跟上" / "有双字幕"
- "你本身无法看到图片，让你做这个工作确实有问题"
- "每次做完我都要看对不对再下达指令，比我自己做都累"

## 最新成果（2026-05-11）
- **minority_fashion_synced.mp4**: 62.9s, 1080×1920, 30fps, 10.2MB
- 音画同步（每段场景=配音时长），V2字幕效果（金色高亮、交替位置）
- Hook 开场 + 结尾 CTA

## 工作目录
- 主目录: `D:/创作内容导出/AI测试视频/`
- 临时目录: `C:/Users/Administrator/temp_v5/`
- ComfyUI 背景缓存: `D:/创作内容导出/AI测试视频/ai_assets/`
