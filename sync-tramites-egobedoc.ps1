param(
    [string]$Output = "tramites-iprus-data.js",
    [string]$SaveHtml = "outputs\passig_citizen.html",
    [string]$SaveMetaJson = "outputs\passig_citizen-meta.json",
    [string]$EnvFile = ".env.egobedoc.local",
    [string]$PythonExe = $env:IPRUS_PYTHON_EXE,
    [switch]$StrictTls
)

function Import-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (-not $name) {
            return
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $root $EnvFile
Import-EnvFile -Path $envPath

$arguments = @(
    ".\sync-egobedoc-passig-citizen.py",
    "--output", $Output,
    "--save-html", $SaveHtml,
    "--save-meta-json", $SaveMetaJson
)

if (-not $StrictTls) {
    $arguments += "--insecure"
}

$pythonCandidates = @()
if ($PythonExe) {
    $pythonCandidates += $PythonExe
}
$pythonCandidates += @(
    (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"),
    "python"
)

$resolvedPython = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq "python" -or (Test-Path -LiteralPath $candidate)) {
        $resolvedPython = $candidate
        break
    }
}

if (-not $resolvedPython) {
    throw "No se encontro un ejecutable de Python para la sincronizacion."
}

Push-Location $root
try {
    & $resolvedPython @arguments
}
finally {
    Pop-Location
}
