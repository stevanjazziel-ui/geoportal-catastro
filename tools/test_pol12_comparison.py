"""Independently verify the read-only POL-12 comparison."""
from compare_pol12_final import SOURCE, OUT
from test_pol20_comparison import main

if __name__ == '__main__':
    main(destination=OUT, package=SOURCE/'ESCENARIO_FINAL_183.gpkg', slot='POL-12')
