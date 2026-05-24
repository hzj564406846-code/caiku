---
name: robot-vacuum-control
description: 小米扫地机器人局域网/云端控制项目，当前阻塞：Token获取
type: project
originSessionId: 656cad54-9f29-4e3f-ab96-60f534650d89
---
## 目标
微信 → QClaw → Claude Code → 扫地机器人（局域网或云端控制）

## 设备信息
- **品牌**: 小米（Xiaomi）
- **IP**: 192.168.110.197
- **型号**: 未知（新款纯云控，不支持老版 miio LAN 协议）
- **端口扫描**: TCP 54321 拒连，UDP 54321 不回应，无开放端口

## 当前阻塞
**Token 获取失败**。所有尝试：
1. ❌ 局域网 miio 协议（UDP hello/TCP）：设备不回应，WiFi 模块休眠
2. ❌ 小米云 API（micloud）：需要 2FA 短信验证，程序化登录被拦截
3. ❌ 网络抓包：App 走云控，无 LAN 流量
4. ❌ Token 提取器网页：验证后只显示 "ok"，未完成回调

## 通讯架构（已完成部分）
- QClaw ↔ Claude Code 文件通讯协议已建立
- 通讯目录: `C:/Users/Administrator/.qclaw/workspace/agent-comm/`
- Bridge 脚本: `qclaw_bridge.py`（轮询 inbox，处理简单任务）
- 启动器: `Claude Code.bat`（桌面，同时启动 bridge + VS Code）
- 控制脚本: `xiaomi_vacuum.py`（已写好，等 Token）

## 可能的方向
1. 用户用网页 Token 提取器完整走一遍（可能是页面跳转没完成）
2. 安装米家 Windows 版，从本地文件提取 Token
3. 用 Home Assistant 集成（自动发现并获取 Token）
4. 换用小米云 API 中转（需要稳定登录方案）

## Why
用户不能直接连微信，通过 QClaw 中转。需要控制扫地机器人来自动化。
