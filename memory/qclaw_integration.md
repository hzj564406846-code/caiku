---
name: qclaw-integration
description: QClaw本地多模态Agent——看图流程、API、启动方式
metadata: 
  node_type: memory
  type: reference
  originSessionId: 80c9e7f4-e1c7-487d-8166-6ed089a144de
---

## QClaw 是什么
本地 Electron 桌面应用，提供多模态/视觉能力。充当 DeepSeek（纯文本模型）的"眼睛"。

## 安装位置
- 快捷方式: `C:\Users\Public\Desktop\QClaw.lnk`（公共桌面，所有人可见）
- 安装目录: `D:\AI\QClaw\QClaw.exe`

## API
- 地址: `http://127.0.0.1:28789/v1/chat/completions`
- 认证: Bearer `5b50f5ea834b5d056c47b5ebe619b7557e145eae64fa73a3`
- 格式: OpenAI 兼容
- 模型: `openclaw/main`
- 多模态: 支持 image_url（base64）

## 看图流程（每次需要看图时执行）
1. 检查 QClaw 是否在运行：`curl -s http://127.0.0.1:28789/v1/models`
2. 如果没反应 → 启动：`start "" "D:\AI\QClaw\QClaw.exe"` ，等 10 秒让它起来
3. 找到截图文件：`ls -lt /c/Users/Administrator/AppData/Local/Temp/ScreenShot_*`
4. 压缩图片（PIL thumbnail 1024px, JPEG quality 70）
5. **加载会话文件**：读 `C:\Users\Administrator\.claude\qclaw_session.json`
6. 把新图+问题追加到 messages，整包发给 QClaw
7. QClaw 回复追加回 messages，保存 session
8. 返回结果给用户

## 持久会话机制
- 会话文件: `C:\Users\Administrator\.claude\qclaw_session.json`
- System prompt 已写好：QClaw 知道自己是 QClaw、我是 Claude Code、主人是胡志君
- 每次请求带上完整 messages 历史，QClaw 就有持续上下文
- 不是每次开新窗口，是同一个对话不断追加

## 注意事项
- QClaw 用的是自己的线上模型，不是本地 Ollama
- QClaw 跟 OpenClaw 是两个不同的东西，不要搞混
- QClaw 模型也会幻觉，分析结果不能全信，错了让用户纠正
- QClaw API 免费，但上下文靠我维护的 session 文件来模拟
