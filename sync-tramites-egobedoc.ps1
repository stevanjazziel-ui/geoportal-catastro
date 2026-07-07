param(
    [string]$Output = "tramites-iprus-data.js",
    [string]$SaveHtml = "outputs\passig_citizen.html",
    [string]$SaveMetaJson = "outputs\passig_citizen-meta.json",
    [switch]$StrictTls
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
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
