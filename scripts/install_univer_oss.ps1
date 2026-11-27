$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Packages = @(
    '@univerjs/preset-sheets-filter',
    '@univerjs/preset-sheets-sort',
    '@univerjs/preset-sheets-data-validation',
    '@univerjs/preset-sheets-conditional-formatting',
    '@univerjs/preset-sheets-find-replace',
    '@univerjs/preset-sheets-hyper-link',
    '@univerjs/preset-sheets-table',
    '@univerjs/preset-sheets-drawing',
    '@univerjs/preset-sheets-note',
    '@univerjs/preset-sheets-thread-comment'
)

Write-Host 'Memasang preset open-source Univer...' -ForegroundColor Cyan
& npm install --save-dev @Packages
if ($LASTEXITCODE -ne 0) {
    throw 'npm install gagal. Jangan gunakan --force atau --legacy-peer-deps; simpan output error untuk diperiksa.'
}

$BuildScript = Join-Path $ProjectRoot 'scripts/build_invoice_univer.mjs'
if (-not (Test-Path $BuildScript)) {
    throw 'scripts/build_invoice_univer.mjs tidak ditemukan. Pastikan script build Kargo tetap ada.'
}

Write-Host 'Membangun bundle Univer Invoice...' -ForegroundColor Cyan
& node $BuildScript
if ($LASTEXITCODE -ne 0) {
    throw 'Build Univer gagal. Simpan output error untuk diperiksa.'
}

Write-Host 'Selesai. Restart aplikasi Kargo untuk mencoba fitur tambahan.' -ForegroundColor Green
