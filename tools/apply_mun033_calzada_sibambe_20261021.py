"""Apply the user's corrected camera ID to the marked carriageway, not MUN-036."""
from shapely.geometry import Point
from shapely.ops import nearest_points

import apply_mun033_jacinto_unidad_20261021 as movement

movement.RELEASE = 'MUN033_CALZADA_UNIDAD_NACIONAL_20261021'
movement.OUT = movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / movement.RELEASE
movement.BASELINE = 'MUN033_JACINTO_UNIDAD_NACIONAL_20261021'
movement.ADDRESS = 'Avenida Unidad Nacional - calzada sur, frente a urbanizacion Sibambe (punto marcado por el usuario)'
movement.AUTHORIZATION = 'Usuario aclara: Mover MUN-033 al circulo. MUN-036 permanece fija.'
movement.NODE_VALIDATED = False
movement.SOURCE_NOTE = 'Posicion aproximada interpretada de la captura del usuario y ajustada a la linea vial de la calzada sur; no es una interseccion ni un poste verificado.'


def locate_marked_carriageway(roads):
    # Similarity registration uses the visible former municipal point and the
    # southern Calicuchima crossing; the circle is then snapped to that roadway.
    prior_package = (movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' /
        'MACAJI_COMPENSACION_021_043_20261021/ESCENARIO_FINAL_183.gpkg')
    municipal = movement.read(prior_package, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    anchor_camera = municipal.loc['MUN-033'].geometry
    southern = roads.loc[858]
    calicuchima = roads.loc[878]
    movement.require(southern['name'] == 'Avenida Unidad Nacional' and calicuchima['name'] == 'Calicuchima',
        'Cambian las referencias viales de la captura')
    crossing = southern.geometry.intersection(calicuchima.geometry)
    movement.require(crossing.geom_type == 'Point', 'El cruce de referencia no es unico')
    pixel_a, pixel_b, pixel_target = complex(488, 160), complex(863, 361), complex(450, 255)
    utm_a, utm_b = complex(anchor_camera.x, anchor_camera.y), complex(crossing.x, crossing.y)
    estimated = utm_a + (pixel_target.conjugate() - pixel_a.conjugate()) * (utm_b - utm_a) / (pixel_b.conjugate() - pixel_a.conjugate())
    estimate = Point(estimated.real, estimated.imag)
    _, target = nearest_points(estimate, southern.geometry)
    movement.require(target.distance(estimate) < 5, 'El circulo no coincide con la calzada esperada')
    movement.require(target.distance(crossing) > 50, 'Destino demasiado cercano a Calicuchima')
    evidence = dict(roads=[movement.ADDRESS], source='PNPRI_RED_VIAL_REFERENCIA', sourceRow=858,
        screenshot='codex-clipboard-c94bb1b9-adf1-4bc4-b99d-5f18ab7fff3f.png',
        screenshotPixels={'formerMUN033': [488, 160], 'CalicuchimaSouthCrossing': [863, 361], 'redCircle': [450, 255]},
        imageEstimateUtm=[estimate.x, estimate.y], roadAdjustmentM=estimate.distance(target),
        metricCoordinates=[target.x, target.y], approximateFromScreenshot=True,
        onRequestedCarriageway=True, fieldVerified=False, protectedCamera='MUN-036')
    return target, evidence


movement.locate = locate_marked_carriageway

if __name__ == '__main__':
    movement.main()
