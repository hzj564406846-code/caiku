# caiku-sync 定时同步脚本
# 用法：直接运行即可注册 Windows 计划任务，每10分钟自动 git pull + push

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = "caiku-sync"

# ---- 同步逻辑 ----
$syncScript = @"
cd `"$scriptDir`"
git pull --rebase 2>&1 | Out-Null
git add -A
`$status = git diff --cached --quiet 2>&1
if (`$LASTEXITCODE -ne 0) {
    git commit -m "auto-sync `$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    git push 2>&1 | Out-Null
}
"@

$syncScriptPath = "$scriptDir\sync.ps1"
$syncScript | Set-Content -Path $syncScriptPath -Encoding UTF8

# ---- 删除旧任务（如果存在）----
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "已删除旧的计划任务: $taskName"
}

# ---- 创建新计划任务 ----
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -File `"$syncScriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "caiku-sync 计划任务已注册（每10分钟同步一次）"
Write-Host "同步目录: $scriptDir"
