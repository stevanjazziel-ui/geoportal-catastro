param(
    [string]$Branch = "main",
    [string]$SharedState = "tramites-iprus-shared-state.js"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $SharedState)) {
        throw "No existe el archivo compartido $SharedState."
    }

    git diff --quiet -- $SharedState
    if ($LASTEXITCODE -eq 0) {
        Write-Output "No hubo cambios en el archivo compartido. No se requiere publicacion."
        $global:LASTEXITCODE = 0
        return
    }
    if ($LASTEXITCODE -ne 1) {
        throw "No se pudo verificar el diff del archivo compartido."
    }

    git add -- $SharedState
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo preparar el archivo compartido para publicar."
    }
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "Publish IPRUS shared assignments ($timestamp)"
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo generar el commit de asignaciones compartidas."
    }
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo publicar el archivo compartido hacia GitHub."
    }
    Write-Output "Asignaciones compartidas publicadas correctamente."
    $global:LASTEXITCODE = 0
}
finally {
    Pop-Location
}
