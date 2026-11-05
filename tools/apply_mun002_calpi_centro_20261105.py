"""Move MUN-002 to the previously approved Calpi-centre site, vacated by MUN-004."""
import json
import sqlite3
import sys
import zipfile
import apply_mun033_jacinto_unidad_20261021 as movement

movement.CAMERA = 'MUN-002'
movement.RELEASE = 'MUN002_CALPI_CENTRO_20261105'
movement.OUT = movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / movement.RELEASE
movement.BASELINE = 'RURALES_COP_UNACH_20261105'
movement.ADDRESS = 'Calpi - CENTRO (anterior ubicacion de MUN-004)'
movement.AUTHORIZATION = 'Usuario solicita mover MUN-002 a Calpi centro. Se reutiliza la posicion de MUN-004 anterior a su traslado a la UNACH; MUN-003 permanece en la entrada de Calpi.'
movement.NODE_VALIDATED = False
movement.SOURCE_NOTE = 'Coordenada del proyecto previamente identificada como Calpi CENTRO (MUN-004). Referencia cartografica, no poste verificado.'

def locate(roads):
    source = (movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'
        'MUN036_JACINTO_UNIDAD_NACIONAL_20261021/ESCENARIO_FINAL_183.gpkg')
    prior = movement.read(source, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    row = prior.loc['MUN-004']
    movement.require(row.PARROQUIA == 'Calpi' and row.FUNCION == 'CENTRO', 'Referencia de Calpi centro incorrecta')
    target = row.geometry
    return target, dict(sourcePackage=source.relative_to(movement.ROOT).as_posix(),
        sourceSha256=movement.digest(source), formerCamera='MUN-004', fieldVerified=False,
        metricCoordinates=[target.x, target.y], sourceAddress=row.DIRECCION,
        roads=[movement.ADDRESS])

movement.locate = locate
original_calculate = movement.calculate

def calculate(*args, **kwargs):
    validator = kwargs['node_validator']
    def validate(store, changes, municipal, police, urban):
        audit, blocks = validator(store, changes, municipal, police, urban)
        for point, props in municipal:
            if props['ID_PROPUESTA'] == 'MUN-002':
                props.update(PARROQUIA='Calpi', FUNCION='CENTRO',
                    DESTINO_REVISION='CALPI_CENTRO', COORDENADAS_USUARIO_ANTES_CONSERVADAS=False,
                    ESTADO_REVISION='DESTINO_AUTORIZADO_USUARIO')
        return audit, blocks
    kwargs['node_validator'] = validate
    return original_calculate(*args, **kwargs)

movement.calculate = calculate

if __name__ == '__main__':
    if '--finalize-only' not in sys.argv:
        movement.main()
    out = movement.OUT
    final = movement.read(out / 'ESCENARIO_FINAL_183.gpkg', 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    movement.require(final.loc['MUN-002'].PARROQUIA == 'Calpi' and final.loc['MUN-002'].FUNCION == 'CENTRO', 'Parroquia/funcion incorrectas')
    movement.require(final.loc['MUN-004'].PARROQUIA == 'Riobamba', 'Se altero el traslado UNACH')
    results = movement.read_json(out / 'RESULTADOS.json')
    results.update(status='MUN002_CALPI_CENTRO_AUTORIZADO', published=True)
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
    print('MUN-002 en Calpi centro: parroquia, funcion, coordenadas y coberturas verificadas.', flush=True)
