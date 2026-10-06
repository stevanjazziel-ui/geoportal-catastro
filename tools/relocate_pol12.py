"""Apply the approved79m POL-12 move; keep the published POL-20 location fixed."""
import sys
from build_police_camera_proposal import ROOT
from relocate_pol20 import main, refresh_view

SOURCE = ROOT / 'data/seguridad-riobamba/REUBICACION_POL20_20261005'
OUT = ROOT / 'data/seguridad-riobamba/REUBICACION_POL12_20261006'
COMPARISON = ROOT / 'data/seguridad-riobamba/comparacion-pol12-20261006'

if __name__ == '__main__':
    if '--refresh-view' in sys.argv:
        refresh_view(slot='POL-12', destination=OUT)
    else:
        main(slot='POL-12', source=SOURCE, destination=OUT, comparison_dir=COMPARISON,
             selection_label='MEJORA_MAS_CERCANA', expected_candidate='CAND-POL-01024')
