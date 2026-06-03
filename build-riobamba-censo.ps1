$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$zipPath = "C:\Users\PC\Downloads\BDD_CPV2022_MANLOC_CSV (1).zip"
$entryName = "1.3 BDD_CPV_2022_MANLOC_CSV/CPV_2022_Poblacion_Manloc.csv"
$outDir = Join-Path $PSScriptRoot "riobamba-censo-data"
$geoJsonPath = Join-Path $outDir "riobamba_manzanas.geojson"
$statsPath = Join-Path $outDir "riobamba_manzanas_stats.json"

if (-not (Test-Path $zipPath)) {
  throw "No se encontro el ZIP en: $zipPath"
}

if (-not (Test-Path $outDir)) {
  New-Item -ItemType Directory -Path $outDir | Out-Null
}

$baseUrl = "https://idgn.ecuadorencifras.gob.ec/server/rest/services/Hosted/Marco_Geoestadistico_2022/FeatureServer/6/query"
$whereClause = [System.Uri]::EscapeDataString("man LIKE '0601%'")
$idsUrl = "${baseUrl}?where=${whereClause}&returnIdsOnly=true&f=json"

Write-Host "Consultando manzanas censales oficiales de Riobamba..."
$idsResponse = Invoke-RestMethod -Uri $idsUrl -Method Get
$objectIds = @($idsResponse.objectIds)

if (-not $objectIds.Count) {
  throw "No se encontraron manzanas censales para Riobamba."
}

$featureList = New-Object System.Collections.Generic.List[object]
$geometryCodes = New-Object System.Collections.Generic.HashSet[string]
$batchSize = 400

for ($offset = 0; $offset -lt $objectIds.Count; $offset += $batchSize) {
  $batch = $objectIds[$offset..([Math]::Min($offset + $batchSize - 1, $objectIds.Count - 1))]
  $idsChunk = [string]::Join(",", $batch)
  $geoUrl = "${baseUrl}?objectIds=${idsChunk}&outFields=man&returnGeometry=true&f=geojson&outSR=4326"
  $geoResponse = Invoke-RestMethod -Uri $geoUrl -Method Get

  foreach ($feature in @($geoResponse.features)) {
    $null = $featureList.Add($feature)
    $null = $geometryCodes.Add([string]$feature.properties.man)
  }
}

$geoJson = [ordered]@{
  type = "FeatureCollection"
  features = @($featureList.ToArray())
}

$geoJson | ConvertTo-Json -Depth 100 | Set-Content -Path $geoJsonPath -Encoding UTF8

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)

try {
  $entry = $archive.GetEntry($entryName)
  if ($null -eq $entry) {
    throw "No se encontro la tabla de poblacion dentro del ZIP."
  }

  $reader = New-Object System.IO.StreamReader($entry.Open())

  try {
    $header = $reader.ReadLine()
    $columns = $header.Split(";")
    $indexMap = @{}
    for ($i = 0; $i -lt $columns.Length; $i += 1) {
      $indexMap[$columns[$i]] = $i
    }

    $statsByMan = @{}
    $riobambaPrefix = "0601"
    $lineCount = 0

    while (($line = $reader.ReadLine()) -ne $null) {
      if ([string]::IsNullOrWhiteSpace($line)) {
        continue
      }

      $parts = $line.Split(";")
      if ($parts.Length -lt $columns.Length) {
        continue
      }

      $man = "{0}{1}{2}{3}{4}{5}" -f `
        $parts[$indexMap["I01"]], `
        $parts[$indexMap["I02"]], `
        $parts[$indexMap["I03"]], `
        $parts[$indexMap["I04"]], `
        $parts[$indexMap["I05"]], `
        $parts[$indexMap["I06"]]

      if (-not $man.StartsWith($riobambaPrefix)) {
        continue
      }

      if (-not $geometryCodes.Contains($man)) {
        continue
      }

      if (-not $statsByMan.ContainsKey($man)) {
        $statsByMan[$man] = [ordered]@{
          man = $man
          population_total = 0
          male = 0
          female = 0
          age_0_14 = 0
          age_15_29 = 0
          age_30_44 = 0
          age_45_64 = 0
          age_65_plus = 0
        }
      }

      $record = $statsByMan[$man]
      $record.population_total += 1

      $sexCode = [string]$parts[$indexMap["P02"]]
      if ($sexCode -eq "1") {
        $record.male += 1
      } elseif ($sexCode -eq "2") {
        $record.female += 1
      }

      $age = 0
      [void][int]::TryParse([string]$parts[$indexMap["P03"]], [ref]$age)

      if ($age -le 14) {
        $record.age_0_14 += 1
      } elseif ($age -le 29) {
        $record.age_15_29 += 1
      } elseif ($age -le 44) {
        $record.age_30_44 += 1
      } elseif ($age -le 64) {
        $record.age_45_64 += 1
      } else {
        $record.age_65_plus += 1
      }

      $lineCount += 1
      if (($lineCount % 500000) -eq 0) {
        Write-Host "Procesadas $lineCount filas de poblacion..."
      }
    }

    $statsValues = @($statsByMan.Values | Sort-Object man)
    $summary = [ordered]@{
      manzanas = $statsValues.Count
      population_total = 0
      male = 0
      female = 0
      age_0_14 = 0
      age_15_29 = 0
      age_30_44 = 0
      age_45_64 = 0
      age_65_plus = 0
    }

    foreach ($item in $statsValues) {
      $summary.population_total += [int]$item.population_total
      $summary.male += [int]$item.male
      $summary.female += [int]$item.female
      $summary.age_0_14 += [int]$item.age_0_14
      $summary.age_15_29 += [int]$item.age_15_29
      $summary.age_30_44 += [int]$item.age_30_44
      $summary.age_45_64 += [int]$item.age_45_64
      $summary.age_65_plus += [int]$item.age_65_plus
    }

    $statsPayload = [ordered]@{
      generated_at = (Get-Date).ToString("s")
      source = "CPV 2022 Poblacion Manloc + Marco Geoestadistico 2022"
      summary = $summary
      byMan = $statsByMan
    }

    $statsPayload | ConvertTo-Json -Depth 10 | Set-Content -Path $statsPath -Encoding UTF8
  }
  finally {
    $reader.Close()
  }
}
finally {
  $archive.Dispose()
}

Write-Host "Listo."
Write-Host "GeoJSON: $geoJsonPath"
Write-Host "Stats:   $statsPath"
