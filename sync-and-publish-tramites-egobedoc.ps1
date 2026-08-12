param(
    [string]$Branch = "main",
    [string]$Output = "tramites-iprus-data.js",
    [string]$SharedState = "tramites-iprus-shared-state.js",
    [string]$SaveHtml = "outputs\passig_citizen.html",
    [string]$SaveMetaJson = "outputs\passig_citizen-meta.json",
    [string]$EnvFile = ".env.egobedoc.local",
    [switch]$StrictTls
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncScript = Join-Path $root "sync-tramites-egobedoc.ps1"
$outputPath = Join-Path $root $Output
$publishTargets = @($Output)
if ($SharedState) {
    $publishTargets += $SharedState
}

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
    if ($LASTEXITCODE -ne 0) {
        throw "La sincronizacion de eGOB devolvio un codigo de salida no valido."
    }

    git diff --quiet -- @publishTargets
    if ($LASTEXITCODE -eq 0) {
        Write-Output ("No hubo cambios en {0}. No se requiere publicacion." -f ($publishTargets -join ", "))
        $global:LASTEXITCODE = 0
        return
    }
    if ($LASTEXITCODE -ne 1) {
        throw ("No se pudo verificar el diff de: {0}." -f ($publishTargets -join ", "))
    }

    git add -- @publishTargets
    if ($LASTEXITCODE -ne 0) {
        throw ("No se pudo preparar la publicacion de: {0}." -f ($publishTargets -join ", "))
    }
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "Auto-sync IPRUS queue and shared state ($timestamp)"
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo generar el commit automatico de sincronizacion."
    }
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo publicar la sincronizacion automatica hacia GitHub."
    }

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
    $global:LASTEXITCODE = 0
}
finally {
    Pop-Location
}
