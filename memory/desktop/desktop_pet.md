---
name: desktop-pet
description: 源源上班搭子桌宠项目状态
metadata:
  type: project
---

# 源源上班搭子 — 桌面宠物

## 技术栈
- Godot Engine 4.x（GDScript）
- DeepSeek API（deepseek-v4-flash）
- 代码位置：`C:\Users\Administrator\Documents\Codex\2026-07-27\new-chat\work\yuanyuan-desktop-pet\`
- 构建输出：`C:\Users\Administrator\Desktop\桌面宠物\`

## 最新版本
v1.4.0 — 心形弹窗 + 行为观察记忆（2026-08-03）

## 已实现功能
1. 桌面视频猫（idle/yawn/groom/sleepy/wash_face/scratch/roll）
2. 点击互动（温柔/傲娇/吐槽三层）
3. 托盘常驻、任务栏隐藏
4. 软件识别吐槽（微信/Excel/Word/PPT/浏览器/钉钉/IDE 等）
5. 天气感知 + 特效
6. 定时提醒（喝水、午饭、下班打卡）
7. 加班催促
8. 文字气泡 + 表情气泡
9. DeepSeek AI 聊天
10. 心形礼物弹窗（Godot 原生实现，48h 冷却）
11. 行为观察记忆（observation_service.gd）

## 行为观察记忆系统（刚接入）
- `observation_service.gd`: 每5分钟采集行为快照（活跃应用、切换次数、点击次数），存入 `user://behavior_log.json`
- 每日18:00通过 DeepSeek 生成一句话总结，存入 `user://behavior_insights.json`
- 猫主动说话时 30% 概率使用基于观察的个性化内容
- 纯本地计算趋势检测（高频应用、切换高峰、发呆时长）

## 已完成（Claude 2026-08-03）
- [x] 行为观察记忆系统（observation_service.gd）
- [x] 每日17:30 DeepSeek总结
- [x] 回家欢迎语（周末/周一/周五/早晚差异化）
- [x] 拖拽对话（拖走+边缘警告）
- [x] 连续工作检测（1h/2h提醒，3h触发心形礼物）
- [x] 猫主动说话30%概率使用行为洞察

## 待完成
- [ ] 深夜模式（用户说没必要，搁置）
- [ ] 窗口切换焦虑检测

## 数据存储位置
- `%APPDATA%/Godot/app_userdata/源源上班搭子/profile.json` — 设置
- `%APPDATA%/Godot/app_userdata/源源上班搭子/memory.json` — 聊天记忆
- `%APPDATA%/Godot/app_userdata/源源上班搭子/behavior_log.json` — 行为快照
- `%APPDATA%/Godot/app_userdata/源源上班搭子/behavior_insights.json` — 行为洞察

**Why this matters:** 后续继续开发或接手时，这个文件记录了完整的项目状态。
