# Construit l'exécutable autonome dist\AudioBatch-Converter.exe (aucun Python
# requis chez l'utilisateur final). Usage :  powershell -File build_exe.ps1
# config.json, logs\ et ffmpeg_bin\ sont créés à côté de l'exe au premier lancement.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --quiet --upgrade pyinstaller
python -m pip install --quiet -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "AudioBatch-Converter" `
    --icon assets\app.ico `
    --exclude-module numpy `
    --exclude-module matplotlib `
    --exclude-module scipy `
    --exclude-module pandas `
    main.py

if (Test-Path "dist\AudioBatch-Converter.exe") {
    $size = [math]::Round((Get-Item "dist\AudioBatch-Converter.exe").Length / 1MB, 1)
    Write-Host "OK -> dist\AudioBatch-Converter.exe ($size Mo)"
} else {
    Write-Host "ECHEC : exe non produit"
    exit 1
}
