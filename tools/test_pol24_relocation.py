"""Independently verify POL-24 and its recalculated coverage dependencies."""
import pyogrio

from relocate_pol24 import SOURCE, OUT
from test_pol20_relocation import main

if __name__ == '__main__':
    main(source_package=SOURCE / 'ESCENARIO_FINAL_183.gpkg', destination=OUT, slot='POL-24',
         candidate='CAND-POL-02764', platform='PLATAFORMA Q',
         exclusive_dv=12, overlap=34.545082609555045)
    prior = pyogrio.read_dataframe(SOURCE / 'ESCENARIO_FINAL_183.gpkg',
                                   layer='CELDAS_COMPLETAS_A_PARCIALES')
    current = pyogrio.read_dataframe(OUT / 'ESCENARIO_FINAL_183.gpkg',
                                     layer='CELDAS_COMPLETAS_A_PARCIALES')
    assert current.empty and list(current.columns) == list(prior.columns)
    print('PASS: tabla de transiciones vacia con esquema conservado, sin filas historicas.')
