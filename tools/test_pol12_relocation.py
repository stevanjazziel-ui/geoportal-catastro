"""Verify the approved79m move independently and preserve the published POL-20."""
from relocate_pol12 import SOURCE, OUT
from test_pol20_relocation import main

if __name__ == '__main__':
    main(source_package=SOURCE/'ESCENARIO_FINAL_183.gpkg', destination=OUT, slot='POL-12',
         candidate='CAND-POL-01024', platform='PLATAFORMA H',
         exclusive_dv=11, overlap=48.097451871594444)
