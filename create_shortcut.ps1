# Adds "MediaBatch Converter" to the Windows Start menu (current user, no admin rights).
# Usage:  powershell -ExecutionPolicy Bypass -File create_shortcut.ps1

$appDir  = $PSScriptRoot
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    Write-Error "pythonw.exe not found in PATH - install Python 3.12+ from python.org first."
    exit 1
}

$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "MediaBatch Converter.lnk"
$sh  = New-Object -ComObject WScript.Shell
$s   = $sh.CreateShortcut($lnk)
$s.TargetPath       = $pythonw
$s.Arguments        = "`"$appDir\main.py`""
$s.WorkingDirectory = $appDir
$s.IconLocation     = "$appDir\assets\app.ico,0"
$s.Description      = "Batch audio & image converter"
$s.Save()

Write-Host "Shortcut created: $lnk"
