"""Apply the approved159m POL-24 move; preserve the other29 police locations."""
import sys
from build_police_camera_proposal import ROOT
from relocate_pol20 import main, refresh_view

SOURCE = ROOT / 'data/seguridad-riobamba/REUBICACION_POL12_20261006'
OUT = ROOT / 'data/seguridad-riobamba/REUBICACION_POL24_20261006'
COMPARISON = ROOT / 'data/seguridad-riobamba/comparacion-pol24-20261006'

if __name__ == '__main__':
    if '--refresh-view' in sys.argv:
        refresh_view(slot='POL-24', destination=OUT)
    else:
        main(slot='POL-24', source=SOURCE, destination=OUT, comparison_dir=COMPARISON,
             selection_label='LOCAL_PLATAFORMA_Q', expected_candidate='CAND-POL-02764')
