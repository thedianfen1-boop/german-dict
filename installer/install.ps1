# 德语词典安装脚本：由安装程序自动运行，弹出窗口让用户选择安装位置
#   -Target <路径>  -Quiet   不弹窗口直接安装（用于测试）
param([string]$Target = '', [switch]$Quiet)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$name    = '德语词典'
$version = '__VERSION__'  # 生成安装包时由 tools/build_installer.py 替换为 app/version.py 里的版本号
$regKey  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\GermanDict'
$menuDir = Join-Path ([Environment]::GetFolderPath('Programs')) $name
$desktop = [Environment]::GetFolderPath('Desktop')

function Show-Msg($text, $icon = 'Information') {
    if (-not $Quiet) { [System.Windows.Forms.MessageBox]::Show($text, $name, 'OK', $icon) | Out-Null }
    else { Write-Output $text }
}

# 程序总是装在所选位置下的 GermanDict 子文件夹里，卸载时只删除这个文件夹
function Resolve-Dest($path) {
    $path = [Environment]::ExpandEnvironmentVariables($path.Trim()).TrimEnd('\')
    if (-not [IO.Path]::IsPathRooted($path)) { throw '请选择一个完整的文件夹路径' }
    if ((Split-Path $path -Leaf) -ieq 'GermanDict') { return $path }
    return Join-Path $path 'GermanDict'
}

function Install-To($dest) {
    $exe = Join-Path $dest 'GermanDict.exe'
    if ((Test-Path $dest) -and (Get-ChildItem $dest -Force | Select-Object -First 1) -and -not (Test-Path $exe)) {
        throw "文件夹 $dest 里已有其他文件，请换一个位置"
    }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    try { [IO.File]::WriteAllText((Join-Path $dest '.write-test'), 'x'); Remove-Item (Join-Path $dest '.write-test') }
    catch { throw "没有权限写入 $dest，请选择其他位置（例如 D 盘下的文件夹）" }

    # 停止正在运行的旧版本；如果旧版本装在别处，一并移除
    $old = (Get-ItemProperty $regKey -ErrorAction SilentlyContinue).InstallLocation
    foreach ($dir in @($old, $dest) | Where-Object { $_ } | Select-Object -Unique) {
        $oldExe = Join-Path $dir 'GermanDict.exe'
        if (Test-Path $oldExe) { Start-Process -FilePath $oldExe -ArgumentList '--stop' -Wait -WindowStyle Hidden }
    }
    Start-Sleep -Milliseconds 800
    if ($old -and ($old -ne $dest) -and (Test-Path (Join-Path $old 'GermanDict.exe')) -and ((Split-Path $old -Leaf) -ieq 'GermanDict')) {
        Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $exe) { Get-ChildItem $dest -Force | Remove-Item -Recurse -Force }

    Expand-Archive -Path (Join-Path $PSScriptRoot 'payload.zip') -DestinationPath $dest -Force

    # 快捷方式：桌面、开始菜单、安装文件夹里的卸载入口
    $ws = New-Object -ComObject WScript.Shell
    function New-Shortcut($path, $arguments, $desc) {
        $s = $ws.CreateShortcut($path)
        $s.TargetPath = $exe
        $s.Arguments = $arguments
        $s.WorkingDirectory = $dest
        $s.IconLocation = "$exe,0"
        $s.Description = $desc
        $s.Save()
    }
    New-Item -ItemType Directory -Force -Path $menuDir | Out-Null
    New-Shortcut (Join-Path $desktop "$name.lnk") '' '打开德语词典'
    New-Shortcut (Join-Path $menuDir "$name.lnk") '' '打开德语词典'
    New-Shortcut (Join-Path $menuDir "停止$name.lnk") '--stop' '停止后台运行的德语词典'
    New-Shortcut (Join-Path $menuDir "卸载$name.lnk") '--uninstall' '卸载德语词典'
    New-Shortcut (Join-Path $dest "卸载$name.lnk") '--uninstall' '双击卸载德语词典'

    # 在「设置 → 应用 → 已安装的应用」中登记，便于卸载
    New-Item -Path $regKey -Force | Out-Null
    $size = [int]((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
    $props = @{
        DisplayName     = $name
        DisplayVersion  = $version
        Publisher       = '淀粉'
        DisplayIcon     = $exe
        InstallLocation = $dest
        UninstallString = "`"$exe`" --uninstall"
    }
    foreach ($k in $props.Keys) { Set-ItemProperty -Path $regKey -Name $k -Value $props[$k] }
    Set-ItemProperty -Path $regKey -Name EstimatedSize -Value $size -Type DWord
    Set-ItemProperty -Path $regKey -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $regKey -Name NoRepair -Value 1 -Type DWord
    return $exe
}

# 默认位置：已安装过就用原来的位置，否则用当前用户的程序目录
$default = (Get-ItemProperty $regKey -ErrorAction SilentlyContinue).InstallLocation
if (-not $default) { $default = Join-Path $env:LOCALAPPDATA 'Programs\GermanDict' }

if ($Quiet) {
    $exe = Install-To (Resolve-Dest ($(if ($Target) { $Target } else { $default })))
    Write-Output "installed: $exe"
    exit 0
}

# ---------- 安装窗口 ----------
try { Add-Type -Name Dpi -Namespace Win32 -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'; [Win32.Dpi]::SetProcessDPIAware() | Out-Null } catch {}

$font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10)
$form = New-Object System.Windows.Forms.Form -Property @{
    Text = "安装 $name v$version"; ClientSize = New-Object System.Drawing.Size(560, 250); Font = $font
    FormBorderStyle = 'FixedDialog'; MaximizeBox = $false; MinimizeBox = $false
    StartPosition = 'CenterScreen'; BackColor = [System.Drawing.Color]::White
}
$exeIcon = Join-Path $PSScriptRoot 'icon.ico'
if (Test-Path $exeIcon) { $form.Icon = New-Object System.Drawing.Icon($exeIcon) }

$title = New-Object System.Windows.Forms.Label -Property @{
    Text = $name; Location = '24,18'; AutoSize = $true
    Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 16, [System.Drawing.FontStyle]::Bold)
}
$label = New-Object System.Windows.Forms.Label -Property @{ Text = '安装位置：'; Location = '26,74'; AutoSize = $true }
$box = New-Object System.Windows.Forms.TextBox -Property @{ Text = $default; Location = '28,100'; Size = '400,28' }
$browse = New-Object System.Windows.Forms.Button -Property @{ Text = '浏览…'; Location = '440,98'; Size = '92,32' }
$hint = New-Object System.Windows.Forms.Label -Property @{
    Text = "程序会安装到所选位置下的 GermanDict 文件夹，约 40 MB。`n你的数据（缓存、历史、API 密钥）单独保存，重装不会丢失。"
    Location = '26,140'; Size = '510,44'; ForeColor = [System.Drawing.Color]::FromArgb(110, 110, 115)
}
$status = New-Object System.Windows.Forms.Label -Property @{ Text = ''; Location = '26,205'; Size = '300,24' }
$ok = New-Object System.Windows.Forms.Button -Property @{ Text = '安装'; Location = '340,198'; Size = '92,34' }
$cancel = New-Object System.Windows.Forms.Button -Property @{ Text = '取消'; Location = '440,198'; Size = '92,34'; DialogResult = 'Cancel' }
$form.AcceptButton = $ok; $form.CancelButton = $cancel
$form.Controls.AddRange(@($title, $label, $box, $browse, $hint, $status, $ok, $cancel))

$browse.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog -Property @{
        Description = '选择安装位置（会在其中创建 GermanDict 文件夹）'; ShowNewFolderButton = $true
    }
    $start = Split-Path $box.Text -Parent
    if ($start -and (Test-Path $start)) { $dlg.SelectedPath = $start }
    if ($dlg.ShowDialog($form) -eq 'OK') { $box.Text = Resolve-Dest $dlg.SelectedPath }
})

$script:installedExe = $null
$ok.Add_Click({
    try {
        $dest = Resolve-Dest $box.Text
        $box.Text = $dest
        $ok.Enabled = $cancel.Enabled = $browse.Enabled = $box.Enabled = $false
        $status.Text = '正在安装，请稍候…'
        $form.Refresh()
        $script:installedExe = Install-To $dest
        $form.DialogResult = 'OK'
        $form.Close()
    }
    catch {
        $status.Text = ''
        $ok.Enabled = $cancel.Enabled = $browse.Enabled = $box.Enabled = $true
        [System.Windows.Forms.MessageBox]::Show($form, "$($_.Exception.Message)", $name, 'OK', 'Error') | Out-Null
    }
})

# 安装程序以隐藏方式启动 PowerShell，Windows 会把“隐藏”套用到程序显示的第一个窗口上。
# 先显示并关闭一个看不见的占位窗口把它用掉，安装窗口才能正常显示
$dummy = New-Object System.Windows.Forms.Form -Property @{
    ShowInTaskbar = $false; Opacity = 0; StartPosition = 'Manual'; Location = '-3000,-3000'; Size = '1,1'
}
$dummy.Show(); $dummy.Hide(); $dummy.Dispose()

$form.TopMost = $true
$form.Add_Shown({ $form.Activate(); $form.TopMost = $false })
$form.ShowDialog() | Out-Null
if ($script:installedExe) {
    Show-Msg "安装完成！`n`n桌面上已添加「$name」图标。`n首次使用请点击页面右上角的设置按钮，添加 DeepSeek API 密钥。"
    Start-Process -FilePath $script:installedExe
}
