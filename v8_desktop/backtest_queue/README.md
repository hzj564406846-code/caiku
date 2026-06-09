# Backtest Queue

This folder is a handoff queue between Codex and Claude Code / local workers.

- `pending/`: tasks waiting to run.
- `running/`: optional place to move tasks while executing.
- `done/`: result summaries written by the runner.
- `failed/`: failed tasks with error notes.

Runner convention:

1. Read one task JSON from `pending/`.
2. Run the requested command(s) from `C:\Users\56440\v8_desktop`.
3. Save full raw reports under `C:\Users\56440\v8_desktop\reports`.
4. Save a concise result summary JSON and optional Markdown under `done/`.
5. Include any suggestions or concerns in the result summary.

Do not overwrite prior reports. Use timestamps in output names.
