"""Place MUN-036 at the former MUN-033 crossing, keeping MUN-033 fixed."""
import apply_mun033_jacinto_unidad_20261021 as movement

movement.CAMERA = 'MUN-036'
movement.RELEASE = 'MUN036_JACINTO_UNIDAD_NACIONAL_20261021'
movement.OUT = movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / movement.RELEASE
movement.BASELINE = 'MUN033_CALZADA_UNIDAD_NACIONAL_20261021'
movement.AUTHORIZATION = ('Usuario solicita mover MUN-036 a la interseccion donde estaba MUN-033 antes: '
    'Jacinto Gonzales x Avenida Unidad Nacional. MUN-033 permanece en la calzada sur marcada. '
    'Separacion resultante entre ambas: 68,41 m; destinos expresos del usuario.')

original_locate = movement.locate


def locate_former_mun033(roads):
    target, evidence = original_locate(roads)
    prior_package = (movement.ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' /
        'MUN033_JACINTO_UNIDAD_NACIONAL_20261021/ESCENARIO_FINAL_183.gpkg')
    prior = movement.read(prior_package, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    movement.require(target.wkb == prior.loc['MUN-033'].geometry.wkb,
        'El cruce no coincide exactamente con la anterior posicion de MUN-033')
    evidence.update(formerCamera='MUN-033', protectedCamera='MUN-033',
        requestedProximityExceptionM=68.40508687904483)
    return target, evidence


movement.locate = locate_former_mun033

if __name__ == '__main__':
    movement.main()
