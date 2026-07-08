param(
    [string]$Output = "tramites-iprus-data.js",
    [string]$SaveHtml = "outputs\passig_citizen.html",
    [string]$SaveMetaJson = "outputs\passig_citizen-meta.json",
    [string]$EnvFile = ".env.egobedoc.local",
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

Push-Location $root
try {
    python @arguments
}
finally {
    Pop-Location
}
