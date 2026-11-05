"""Snap MUN-022 to the road intersection visible northeast of the user's marker."""
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import Point
import apply_mun033_jacinto_unidad_20261021 as movement

movement.CAMERA = 'MUN-022'
movement.RELEASE = 'MUN022_CRUCE_UNACH_20261105'
movement.OUT = movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / movement.RELEASE
movement.BASELINE = 'MUN002_CALPI_CENTRO_20261105'
movement.ADDRESS = 'J. M. Alvarez x via lateral sin nombre, costado oriental UNACH'
movement.AUTHORIZATION = 'Usuario solicita mover MUN-022 a la interseccion visible arriba y a la derecha de su posicion en la imagen. Cruce compartido de J.M. Alvarez y la via lateral sin nombre; desplazamiento aproximado de 32 m al noreste.'
movement.NODE_VALIDATED = True
movement.SOURCE_NOTE = 'Nodo compartido 7430992222 de las vias OSM 1071639015 y 794487008. Cruce cartografico; no poste verificado.'

def locate(roads):
    source = movement.ROOT.parent / 'entregas/COMPARACION_CAMARAS_COP/osm_unach.xml'
    root = ET.parse(source).getroot()
    ways = {w.attrib['id']: w for w in root.findall('way')}
    shared = set(n.attrib['ref'] for n in ways['1071639015'].findall('nd')) & set(n.attrib['ref'] for n in ways['794487008'].findall('nd'))
    movement.require(shared == {'7430992222'}, 'El cruce no tiene un unico nodo compartido')
    node = next(n for n in root.findall('node') if n.attrib['id'] == '7430992222')
    ll = [float(node.attrib['lon']), float(node.attrib['lat'])]
    x, y = Transformer.from_crs(4326, 32717, always_xy=True).transform(*ll)
    point = Point(x, y)
    return point, dict(roads=['J. M. Alvarez', 'via lateral sin nombre'],
        source='https://www.openstreetmap.org/node/7430992222', osmWays=['1071639015', '794487008'],
        sourceSha256=movement.digest(source), fieldVerified=False, centerlineGapM=0,
        metricCoordinates=[x, y], geographicCoordinates=ll)

movement.locate = locate

if __name__ == '__main__':
    movement.main()
    out = movement.OUT
    results = movement.read_json(out / 'RESULTADOS.json')
    results.update(status='MUN022_INTERSECCION_UNACH_AUTORIZADA', published=True)
    movement.write_json(out / 'RESULTADOS.json', results)
    approval = movement.read_json(out / 'APROBACION_Y_FUENTES.json')
    approval.update(published=True, publicationRequested=True)
    movement.write_json(out / 'APROBACION_Y_FUENTES.json', approval)
    with zipfile.ZipFile(out / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.relative_to(out).as_posix())
    movement.write_json(movement.ROOT / 'sig-bridge-active.json', dict(schemaVersion=1,
        root='./' + out.relative_to(movement.ROOT).as_posix() + '/', releaseId=movement.RELEASE,
        coverageData='riobamba-brechas-actualizadas-data.js'))
    print('MUN-022 ajustada al nodo compartido de la interseccion.', flush=True)
