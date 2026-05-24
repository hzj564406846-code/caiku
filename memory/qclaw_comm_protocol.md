---
name: qclaw-comm-protocol
description: Claude Code 与 QClaw（扫地机器人）之间的文件通讯协议，用于微信消息中转
type: reference
originSessionId: 656cad54-9f29-4e3f-ab96-60f534650d89
---
## 通讯架构

```
用户微信 → QClaw → inbox/<taskId>.json → Claude Code 轮询读取
                                              ↓
用户微信 ← QClaw ← outbox/<taskId>.json ← Claude Code 写入结果
```

## 目录结构
`C:/Users/Administrator/.qclaw/workspace/agent-comm/`
- `inbox/` — QClaw 写入任务，Claude Code 轮询
- `outbox/` — Claude Code 写入结果，QClaw 读取后发微信
- `processed/` — 已完成任务归档

## 消息格式

### 任务文件 inbox/<taskId>.json
```json
{
  "taskId": "YYYYMMDD-HHMMSS-随机",
  "from": "qclaw",
  "to": "claude-code",
  "createdAt": "ISO8601",
  "message": "用户微信消息原文",
  "context": {
    "wechatMsgId": "wx-msg-xxx",
    "user": "用户昵称",
    "channel": "wechat",
    "priority": "normal"
  },
  "status": "pending"
}
```

### 结果文件 outbox/<taskId>.json
```json
{
  "taskId": "...",
  "from": "claude-code",
  "to": "qclaw",
  "createdAt": "ISO8601",
  "status": "success|failed",
  "result": "详细结果",
  "artifacts": ["文件路径列表"],
  "summary": "适合转微信的摘要"
}
```

## Claude Code 侧轮询
- 用 Cron 定时任务每 30 秒检查 `inbox/` 目录
- 发现新 `.json` 文件后读取并执行
- 执行完写入 `outbox/`，把 inbox 文件移到 `processed/`
- 超时：inbox 中超过 10 分钟未处理的任务标记为 stale

## Why
Claude Code 没有对外的 HTTP API，QClaw 不能直接调用。文件系统是双方都能访问的唯一通道。
