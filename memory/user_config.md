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
- 唯兔云代理: 桌面端有快捷方式，需要时可自行启动代理，不必每次让用户手动操作
- Another PC setup: clone repo → symlink memory dir → create scheduled task with sync-memory.bat
