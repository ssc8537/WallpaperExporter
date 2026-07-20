$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$IconPath = Join-Path $ProjectRoot "assets\app_icon.ico"
$EntryPath = Join-Path $ProjectRoot "main.py"
$AssetsPath = Join-Path $ProjectRoot "assets"
$DistPath = Join-Path $ProjectRoot "dist"
$VersionPath = Join-Path $DistPath "V1"
$ZipPath = Join-Path $DistPath "WallpaperExporter_V1.zip"
$BuildPath = Join-Path $ProjectRoot "dev-artifacts\build"
$SpecPath = Join-Path $ProjectRoot "dev-artifacts\build-spec"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "WallpaperExporter" `
    --icon $IconPath `
    --add-data "$AssetsPath;assets" `
    --distpath $VersionPath `
    --workpath $BuildPath `
    --specpath $SpecPath `
    $EntryPath

Compress-Archive -Path "$VersionPath\WallpaperExporter\*" -DestinationPath $ZipPath -Force
Write-Host "Build complete: $VersionPath\WallpaperExporter\WallpaperExporter.exe"
Write-Host "Release archive: $ZipPath"
