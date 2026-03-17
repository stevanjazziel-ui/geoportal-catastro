param(
  [string]$ShpPath = "D:\codex\CATASTRO 2026\CATASTRO_2026.shp",
  [string]$DbfPath = "D:\codex\CATASTRO 2026\CATASTRO_2026.dbf",
  [string]$OutputPath = "D:\codex\CATASTRO 2026\CATASTRO_2026.geojson"
)

$ErrorActionPreference = "Stop"

function Get-BigEndianInt32 {
  param([byte[]]$Bytes)
  return [System.BitConverter]::ToInt32([byte[]]($Bytes[3], $Bytes[2], $Bytes[1], $Bytes[0]), 0)
}

function Convert-Utm17SToLonLat {
  param(
    [double]$Easting,
    [double]$Northing
  )

  $a = 6378137.0
  $eccSquared = 0.0066943799901413165
  $k0 = 0.9996
  $eccPrimeSquared = $eccSquared / (1 - $eccSquared)

  $x = $Easting - 500000.0
  $y = $Northing - 10000000.0

  $m = $y / $k0
  $mu = $m / ($a * (1 - $eccSquared / 4 - 3 * $eccSquared * $eccSquared / 64 - 5 * [math]::Pow($eccSquared, 3) / 256))

  $e1 = (1 - [math]::Sqrt(1 - $eccSquared)) / (1 + [math]::Sqrt(1 - $eccSquared))

  $j1 = 3 * $e1 / 2 - 27 * [math]::Pow($e1, 3) / 32
  $j2 = 21 * $e1 * $e1 / 16 - 55 * [math]::Pow($e1, 4) / 32
  $j3 = 151 * [math]::Pow($e1, 3) / 96
  $j4 = 1097 * [math]::Pow($e1, 4) / 512

  $fp = $mu + $j1 * [math]::Sin(2 * $mu) + $j2 * [math]::Sin(4 * $mu) + $j3 * [math]::Sin(6 * $mu) + $j4 * [math]::Sin(8 * $mu)

  $sinFp = [math]::Sin($fp)
  $cosFp = [math]::Cos($fp)
  $tanFp = [math]::Tan($fp)

  $c1 = $eccPrimeSquared * $cosFp * $cosFp
  $t1 = $tanFp * $tanFp
  $n1 = $a / [math]::Sqrt(1 - $eccSquared * $sinFp * $sinFp)
  $r1 = $a * (1 - $eccSquared) / [math]::Pow(1 - $eccSquared * $sinFp * $sinFp, 1.5)
  $d = $x / ($n1 * $k0)

  $lat = $fp - ($n1 * $tanFp / $r1) * (
    $d * $d / 2 -
    (5 + 3 * $t1 + 10 * $c1 - 4 * $c1 * $c1 - 9 * $eccPrimeSquared) * [math]::Pow($d, 4) / 24 +
    (61 + 90 * $t1 + 298 * $c1 + 45 * $t1 * $t1 - 252 * $eccPrimeSquared - 3 * $c1 * $c1) * [math]::Pow($d, 6) / 720
  )

  $lonOrigin = -81.0
  $lon = (
    $d -
    (1 + 2 * $t1 + $c1) * [math]::Pow($d, 3) / 6 +
    (5 - 2 * $c1 + 28 * $t1 - 3 * $c1 * $c1 + 8 * $eccPrimeSquared + 24 * $t1 * $t1) * [math]::Pow($d, 5) / 120
  ) / $cosFp

  return [pscustomobject]@{
    Lon = $lonOrigin + ($lon * 180.0 / [math]::PI)
    Lat = $lat * 180.0 / [math]::PI
  }
}

function Get-SignedArea {
  param([object[]]$Ring)

  $area = 0.0
  for ($i = 0; $i -lt ($Ring.Count - 1); $i++) {
    $x1 = [double]$Ring[$i][0]
    $y1 = [double]$Ring[$i][1]
    $x2 = [double]$Ring[$i + 1][0]
    $y2 = [double]$Ring[$i + 1][1]
    $area += ($x1 * $y2) - ($x2 * $y1)
  }

  return $area / 2.0
}

function Format-JsonValue {
  param($Value)

  if ($null -eq $Value) {
    return "null"
  }

  if ($Value -is [string]) {
    return '"' + ($Value.Replace('\', '\\').Replace('"', '\"')) + '"'
  }

  if ($Value -is [bool]) {
    return $Value.ToString().ToLowerInvariant()
  }

  if ($Value -is [System.ValueType]) {
    return [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0}", $Value)
  }

  return '"' + ($Value.ToString().Replace('\', '\\').Replace('"', '\"')) + '"'
}

function Format-LinearringJson {
  param([object[]]$Ring)

  $points = foreach ($point in $Ring) {
    '[' +
      ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:R}", [double]$point[0])) +
      ',' +
      ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:R}", [double]$point[1])) +
    ']'
  }

  return '[' + ($points -join ',') + ']'
}

function Get-PolygonGeometryJson {
  param([byte[]]$ContentBytes)

  $shapeType = [System.BitConverter]::ToInt32($ContentBytes, 0)
  if ($shapeType -eq 0) {
    return '{"type":"Polygon","coordinates":[]}'
  }

  if ($shapeType -ne 5) {
    throw "Tipo de geometria no soportado: $shapeType"
  }

  $numParts = [System.BitConverter]::ToInt32($ContentBytes, 36)
  $numPoints = [System.BitConverter]::ToInt32($ContentBytes, 40)

  $parts = New-Object int[] $numParts
  for ($i = 0; $i -lt $numParts; $i++) {
    $parts[$i] = [System.BitConverter]::ToInt32($ContentBytes, 44 + ($i * 4))
  }

  $pointsOffset = 44 + ($numParts * 4)
  $allPoints = New-Object object[] $numPoints

  for ($i = 0; $i -lt $numPoints; $i++) {
    $offset = $pointsOffset + ($i * 16)
    $x = [System.BitConverter]::ToDouble($ContentBytes, $offset)
    $y = [System.BitConverter]::ToDouble($ContentBytes, $offset + 8)
    $lonLat = Convert-Utm17SToLonLat -Easting $x -Northing $y
    $allPoints[$i] = @($lonLat.Lon, $lonLat.Lat)
  }

  $rings = New-Object System.Collections.Generic.List[object]
  for ($partIndex = 0; $partIndex -lt $numParts; $partIndex++) {
    $start = $parts[$partIndex]
    $end = if ($partIndex -lt ($numParts - 1)) { $parts[$partIndex + 1] - 1 } else { $numPoints - 1 }
    $ring = New-Object System.Collections.Generic.List[object]

    for ($pointIndex = $start; $pointIndex -le $end; $pointIndex++) {
      $ring.Add($allPoints[$pointIndex])
    }

    if ($ring.Count -gt 0) {
      $first = $ring[0]
      $last = $ring[$ring.Count - 1]
      if (($first[0] -ne $last[0]) -or ($first[1] -ne $last[1])) {
        $ring.Add(@($first[0], $first[1]))
      }
    }

    $rings.Add($ring.ToArray())
  }

  $polygons = New-Object System.Collections.Generic.List[object]
  foreach ($ring in $rings) {
    $area = Get-SignedArea -Ring $ring
    if (($area -lt 0) -or ($polygons.Count -eq 0)) {
      $polygon = New-Object System.Collections.Generic.List[object]
      $polygon.Add($ring)
      $polygons.Add($polygon)
    } else {
      $polygons[$polygons.Count - 1].Add($ring)
    }
  }

  if ($polygons.Count -le 1) {
    $ringsJson = @()
    if ($polygons.Count -eq 1) {
      $ringsJson = foreach ($ring in $polygons[0]) { Format-LinearringJson -Ring $ring }
    }
    return '{"type":"Polygon","coordinates":[' + ($ringsJson -join ',') + ']}'
  }

  $polygonJson = foreach ($polygon in $polygons) {
    $ringsJson = foreach ($ring in $polygon) { Format-LinearringJson -Ring $ring }
    '[' + ($ringsJson -join ',') + ']'
  }

  return '{"type":"MultiPolygon","coordinates":[' + ($polygonJson -join ',') + ']}'
}

function Read-DbfFields {
  param([System.IO.BinaryReader]$Reader)

  $header = $Reader.ReadBytes(32)
  $recordCount = [System.BitConverter]::ToInt32($header, 4)
  $headerLength = [System.BitConverter]::ToInt16($header, 8)
  $recordLength = [System.BitConverter]::ToInt16($header, 10)
  $fieldCount = ($headerLength - 33) / 32

  $fields = @()
  for ($i = 0; $i -lt $fieldCount; $i++) {
    $descriptor = $Reader.ReadBytes(32)
    $name = ([System.Text.Encoding]::ASCII.GetString($descriptor[0..10])).Trim([char]0).Trim()
    $fields += [pscustomobject]@{
      Name = $name
      Length = [int]$descriptor[16]
    }
  }

  $null = $Reader.ReadByte()

  return [pscustomobject]@{
    Fields = $fields
    RecordCount = $recordCount
    RecordLength = $recordLength
  }
}

$selectedFields = @("cod_catast", "nombre", "apellido", "tipo")

$shpStream = [System.IO.File]::OpenRead($ShpPath)
$dbfStream = [System.IO.File]::OpenRead($DbfPath)
$writer = New-Object System.IO.StreamWriter($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))

try {
  $shpReader = New-Object System.IO.BinaryReader($shpStream)
  $dbfReader = New-Object System.IO.BinaryReader($dbfStream)

  $null = $shpReader.ReadBytes(100)
  $dbfInfo = Read-DbfFields -Reader $dbfReader

  $fieldOffsets = @{}
  $offset = 1
  foreach ($field in $dbfInfo.Fields) {
    $fieldOffsets[$field.Name] = [pscustomobject]@{
      Offset = $offset
      Length = $field.Length
    }
    $offset += $field.Length
  }

  $writer.Write('{"type":"FeatureCollection","features":[')
  $firstFeature = $true

  for ($recordIndex = 0; $recordIndex -lt $dbfInfo.RecordCount; $recordIndex++) {
    $recordHeader = $shpReader.ReadBytes(8)
    if ($recordHeader.Length -lt 8) {
      break
    }

    $contentLengthWords = Get-BigEndianInt32 -Bytes $recordHeader[4..7]
    $contentBytes = $shpReader.ReadBytes($contentLengthWords * 2)
    $dbfRecordBytes = $dbfReader.ReadBytes($dbfInfo.RecordLength)

    if ($dbfRecordBytes.Length -lt $dbfInfo.RecordLength) {
      break
    }

    if ([char]$dbfRecordBytes[0] -eq '*') {
      continue
    }

    $properties = @{}
    foreach ($fieldName in $selectedFields) {
      if ($fieldOffsets.ContainsKey($fieldName)) {
        $meta = $fieldOffsets[$fieldName]
        $raw = [System.Text.Encoding]::UTF8.GetString($dbfRecordBytes, $meta.Offset, $meta.Length).Trim()
        $properties[$fieldName] = if ($raw) { $raw } else { $null }
      }
    }

    $geometryJson = Get-PolygonGeometryJson -ContentBytes $contentBytes
    $propertyJson = ($selectedFields | ForEach-Object {
      '"' + $_ + '":' + (Format-JsonValue -Value $properties[$_])
    }) -join ','

    if (-not $firstFeature) {
      $writer.Write(',')
    }

    $writer.Write('{"type":"Feature","properties":{')
    $writer.Write($propertyJson)
    $writer.Write('},"geometry":')
    $writer.Write($geometryJson)
    $writer.Write('}')
    $firstFeature = $false
  }

  $writer.Write(']}')
}
finally {
  if ($writer) { $writer.Dispose() }
  if ($shpStream) { $shpStream.Dispose() }
  if ($dbfStream) { $dbfStream.Dispose() }
}
