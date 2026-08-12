$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDirectory = Join-Path $repoRoot "outputs"
$logPath = Join-Path $logDirectory "sync-scheduler.log"

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location $repoRoot

Add-Content -LiteralPath $logPath -Value ("[{0}] Inicio de sincronizacion programada." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

try {
    & ".\sync-and-publish-tramites-egobedoc.ps1" *>> $logPath
    $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }
    Add-Content -LiteralPath $logPath -Value ("[{0}] Fin de sincronizacion programada. Codigo: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $exitCode)
    exit $exitCode
}
catch {
    $_ | Out-File -LiteralPath $logPath -Append -Encoding utf8
    Add-Content -LiteralPath $logPath -Value ("[{0}] Sincronizacion programada con error." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
    exit 1
}
