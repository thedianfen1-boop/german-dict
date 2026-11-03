# 德语词典卸载脚本（由 GermanDict.exe --uninstall 调用）
#   -Quiet        不弹窗口直接卸载（用于测试），默认保留用户数据
#   -RemoveData   与 -Quiet 一起使用时同时删除用户数据
param([switch]$Quiet, [switch]$RemoveData)

Add-Type -AssemblyName System.Windows.Forms

$name    = '德语词典'
$dest    = $PSScriptRoot
$exe     = Join-Path $dest 'GermanDict.exe'
$dataDir = Join-Path $env:LOCALAPPDATA 'GermanDict'

function Ask($text) {
    if ($Quiet) { return 'Yes' }
    return [System.Windows.Forms.MessageBox]::Show($text, $name, 'YesNo', 'Question')
}

if ((Ask "确定要卸载$name吗？") -ne 'Yes') { exit }

if (Test-Path $exe) { Start-Process -FilePath $exe -ArgumentList '--stop' -Wait -WindowStyle Hidden }
Start-Sleep -Milliseconds 800

Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) "$name.lnk") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) $name) -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\GermanDict' -Recurse -Force -ErrorAction SilentlyContinue

if ($Quiet) {
    if ($RemoveData) { Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue }
} else {
    $keep = [System.Windows.Forms.MessageBox]::Show(
        "是否保留你的数据（查词缓存、历史记录和 API 密钥）？`n`n保留后重新安装可以直接使用。",
        $name, 'YesNo', 'Question')
    if ($keep -eq 'No') { Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue }
}

# 安全检查：只删除本程序的 GermanDict 文件夹。本脚本就在其中，稍等片刻再删
if ((Split-Path $dest -Leaf) -ieq 'GermanDict' -and (Test-Path $exe)) {
    Start-Process cmd.exe -ArgumentList "/c timeout /t 2 /nobreak >nul & rmdir /s /q `"$dest`"" -WindowStyle Hidden
}
if (-not $Quiet) { [System.Windows.Forms.MessageBox]::Show("$name 已卸载。", $name, 'OK', 'Information') | Out-Null }
