---
name: user-config
description: DeepSeek API backend, settings.json path, environment variables, claude install location
type: user
originSessionId: 8f1e1905-3ea9-41cb-8c35-e5b566983382
---
- Claude Code installed at: `C:\Users\Administrator\AppData\Roaming\QClaw\npm-global\claude` (npm global install via QClaw)
- Settings in `.claude/settings.json` with env vars:
  - ANTHROPIC_BASE_URL: https://api.deepseek.com/anthropic
  - ANTHROPIC_MODEL: deepseek-v4-pro
  - ANTHROPIC_DEFAULT_HAIKU_MODEL: deepseek-v4-flash
  - Theme: dark
- No `mcp.json` configured yet (checked both project and global)
- Python 3.12.0 available, requests/pandas/schedule/openpyxl installed
- Desktop path: `C:\Users\Administrator\Desktop`
- Desktop shortcut: `Claude Code.bat` and `Claude Code.lnk` already created
- Memory sync: GitHub repo `https://github.com/hzj564406846-code/caiku.git` at `C:\Users\56440\.claude\caiku-sync`, auto-sync via scheduled task every 30 min, proxy `http://127.0.0.1:7892`
- 唯兔云代理(v2cloud): 开始菜单快捷方式 `唯兔云.lnk` → `C:\Users\56440\AppData\Local\Programs\v2cloud\v2cloud.exe`，本地代理端口 7892。需要代理时(下载国外资源、访问国外CDN等)自行启动，不必让用户手动操作。启动命令: `Start-Process "C:\Users\56440\AppData\Local\Programs\v2cloud\v2cloud.exe"`。注意:v2rayN 是另一个工具，不是唯兔云，别搞混。**关闭规范(有bug)**: 用完必须先"关闭连接"再退出软件，否则残留系统代理，正常网页都打不开。自动关闭方案: 先关 Windows 系统代理(注册表 HKCU\...\Internet Settings 的 ProxyEnable=0)再 Stop-Process 杀 v2cloud 进程。
- Another PC setup: clone repo → symlink memory dir → create scheduled task with sync-memory.bat
