"""Read-only POL-12 review against the published scenario with POL-20 in G."""
from build_police_camera_proposal import ROOT
from compare_pol20_final import main

SOURCE = ROOT / 'data/seguridad-riobamba/REUBICACION_POL20_20261005'
OUT = ROOT / 'data/seguridad-riobamba/comparacion-pol12-20261006'

if __name__ == '__main__':
    main(slot='POL-12', source=SOURCE, destination=OUT)
