param(
    [string]$Branch = "main",
    [string]$Output = "tramites-iprus-data.js",
    [string]$SaveHtml = "outputs\passig_citizen.html",
    [string]$SaveMetaJson = "outputs\passig_citizen-meta.json",
    [string]$EnvFile = ".env.egobedoc.local",
    [switch]$StrictTls
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncScript = Join-Path $root "sync-tramites-egobedoc.ps1"
$outputPath = Join-Path $root $Output

$syncArguments = @{
    Output = $Output
    SaveHtml = $SaveHtml
    SaveMetaJson = $SaveMetaJson
    EnvFile = $EnvFile
}
if ($StrictTls) {
    $syncArguments.StrictTls = $true
}

Push-Location $root
try {
    & $syncScript @syncArguments

    git diff --quiet -- $Output
    if ($LASTEXITCODE -eq 0) {
        Write-Output "No hubo cambios en $Output. No se requiere publicacion."
        return
    }
    if ($LASTEXITCODE -ne 1) {
        throw "No se pudo verificar el diff de $Output."
    }

    git add -- $Output
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "Auto-sync IPRUS queue data ($timestamp)"
    git push origin $Branch

    if (Test-Path -LiteralPath $outputPath) {
        $content = Get-Content -Raw -LiteralPath $outputPath
        $activeMatch = [regex]::Match($content, '"summary":\s*\{[\s\S]*?"total":\s*(\d+)')
        $historyMatch = [regex]::Match($content, '"historySummary":\s*\{[\s\S]*?"total":\s*(\d+)')
        if ($activeMatch.Success -and $historyMatch.Success) {
            Write-Output ("Sincronizacion publicada. Activos: {0}. Historial: {1}." -f $activeMatch.Groups[1].Value, $historyMatch.Groups[1].Value)
        } else {
            Write-Output "Sincronizacion publicada correctamente."
        }
    }
}
finally {
    Pop-Location
}
