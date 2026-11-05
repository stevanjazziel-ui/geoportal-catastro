"""Move MUN-022 to the Alvarez/Roldos junction explicitly confirmed by the user."""
import xml.etree.ElementTree as ET
import zipfile
from pyproj import Transformer
from shapely.geometry import Point
import apply_mun033_jacinto_unidad_20261021 as movement

movement.CAMERA = 'MUN-022'
movement.RELEASE = 'MUN022_ALVAREZ_ROLDOS_20261105'
movement.OUT = movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / movement.RELEASE
movement.BASELINE = 'MUN022_CRUCE_UNACH_20261105'
movement.ADDRESS = 'J. M. Alvarez x Jaime Roldos Aguilera, costado oriental UNACH'
movement.AUTHORIZATION = 'Usuario aclara que no se referia a la Y y confirma la union de J. M. Alvarez con Jaime Roldos Aguilera, abajo a la izquierda de la captura. Publicar la correccion conservando las otras posiciones.'
movement.NODE_VALIDATED = True
movement.SOURCE_NOTE = 'Nodo compartido OSM 3755176522 de J.M. Alvarez (1071639015) y Jaime Roldos Aguilera (327777492). Cruce cartografico confirmado por el usuario; no poste verificado.'

def locate(roads):
    source = movement.ROOT.parent / 'entregas/COMPARACION_CAMARAS_COP/osm_unach.xml'
    root = ET.parse(source).getroot()
    ways = {w.attrib['id']: w for w in root.findall('way')}
    shared = set(n.attrib['ref'] for n in ways['1071639015'].findall('nd')) & set(n.attrib['ref'] for n in ways['327777492'].findall('nd'))
    movement.require(shared == {'3755176522'}, 'Cruce Alvarez/Roldos ambiguo')
    node = next(n for n in root.findall('node') if n.attrib['id'] == '3755176522')
    ll = [float(node.attrib['lon']), float(node.attrib['lat'])]
    x, y = Transformer.from_crs(4326, 32717, always_xy=True).transform(*ll)
    return Point(x, y), dict(roads=['J. M. Alvarez', 'Jaime Roldos Aguilera'],
        source='https://www.openstreetmap.org/node/3755176522', osmWays=['1071639015', '327777492'],
        sourceSha256=movement.digest(source), fieldVerified=False, centerlineGapM=0,
        metricCoordinates=[x, y], geographicCoordinates=ll)

movement.locate = locate

if __name__ == '__main__':
    movement.main()
    out = movement.OUT
    results = movement.read_json(out / 'RESULTADOS.json')
    results.update(status='MUN022_ALVAREZ_ROLDOS_CONFIRMADA', published=True)
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
    print('MUN-022 en la union de Alvarez y Roldos confirmada por el usuario.', flush=True)
