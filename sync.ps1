cd "C:\Users\56440\.claude\caiku-sync"
git pull --rebase 2>&1 | Out-Null
git add -A
$status = git diff --cached --quiet 2>&1
if ($LASTEXITCODE -ne 0) {
    git commit -m "auto-sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    git push 2>&1 | Out-Null
}
