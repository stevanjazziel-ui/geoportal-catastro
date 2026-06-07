from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"


@dataclass
class CategorizedIsochroneConfig:
    key: str
    display_name: str
    output_suffix: str
    source_zip_candidates: tuple[Path, ...]
    distance_by_category: dict[str, int] = field(default_factory=lambda: {"BARRIAL": 400, "ZONAL": 1000})
    category_field_candidates: tuple[str, ...] = ("CATEGORIA", "categoria", "Categoria")
    name_field_candidates: tuple[str, ...] = ("Nombre_Equ", "nombre", "NOMBRE")
    type_field_candidates: tuple[str, ...] = ("Equipamien", "equipamiento", "EQUIPAMIEN")
    code_field_candidates: tuple[str, ...] = ("codigo", "CODIGO", "Codigo")
    omitted_categories: tuple[str, ...] = ("CANTONAL",)

    def resolve_source_zip(self) -> Path:
        for path in self.source_zip_candidates:
            if path.exists():
                return path
        return self.source_zip_candidates[0]

    @property
    def output_equipamientos(self) -> Path:
        return DATA_DIR / f"riobamba_{self.output_suffix}.geojson"

    @property
    def output_equipamientos_stats(self) -> Path:
        return DATA_DIR / f"riobamba_{self.output_suffix}_stats.json"

    @property
    def output_isocronas(self) -> Path:
        return DATA_DIR / f"riobamba_isocronas_{self.output_suffix}.geojson"

    @property
    def output_isocronas_stats(self) -> Path:
        return DATA_DIR / f"riobamba_isocronas_{self.output_suffix}_stats.json"

    @property
    def extract_dir(self) -> Path:
        return DATA_DIR / f"_tmp_{self.output_suffix}"

    @property
    def shp_polygon_basename(self) -> str:
        return f"isocronas_{self.output_suffix}_manzanas"

    @property
    def shp_start_points_basename(self) -> str:
        return f"puntos_inicio_isocronas_{self.key}"

    @property
    def shp_covered_manzanas_basename(self) -> str:
        return f"manzanas_dentro_isocronas_{self.output_suffix}"

    @property
    def display_name_title(self) -> str:
        return str(self.display_name or self.key).strip().title()

    @property
    def shp_polygon_label(self) -> str:
        return f"ZIP con shapefiles separados del borde exterior de cada isocrona de {self.display_name_title}"

    @property
    def shp_start_points_label(self) -> str:
        return f"Shapefile ZIP con los puntos de inicio de las isocronas de {self.display_name_title}"

    @property
    def shp_covered_manzanas_label(self) -> str:
        return f"ZIP con shapefiles separados de las manzanas dentro de cada isocrona de {self.display_name_title}"


CATEGORIZED_ISOCHRONE_CONFIGS = {
    "bienestar": CategorizedIsochroneConfig(
        key="bienestar",
        display_name="bienestar social",
        output_suffix="bienestar_social_categorizada",
        source_zip_candidates=(
            Path(r"C:\Users\PC\Downloads\categorizados\Bienestar social.rar"),
        ),
    ),
    "cultura": CategorizedIsochroneConfig(
        key="cultura",
        display_name="cultura",
        output_suffix="cultura_categorizada",
        source_zip_candidates=(
            Path(r"C:\Users\PC\Downloads\categorizados\Cultural.rar"),
        ),
    ),
    "educacion": CategorizedIsochroneConfig(
        key="educacion",
        display_name="educacion",
        output_suffix="educacion_categorizada",
        source_zip_candidates=(
            Path(r"C:\Users\PC\Downloads\categorizados\Educacion.rar"),
            BASE_DIR / "EDUCACION_CATEGORIZADO.zip",
            Path(r"E:\Riobamba\equipamientos\EDUCACION 2\EDUCACION_CATEGORIZADO.zip"),
        ),
    ),
    "recreacion": CategorizedIsochroneConfig(
        key="recreacion",
        display_name="recreacion y deporte",
        output_suffix="recreacion_deporte_categorizada",
        source_zip_candidates=(
            Path(r"C:\Users\PC\Downloads\categorizados\Recreacion y deporte.rar"),
        ),
    ),
    "salud": CategorizedIsochroneConfig(
        key="salud",
        display_name="salud",
        output_suffix="salud_categorizada",
        source_zip_candidates=(
            BASE_DIR / "SALUD.rar",
            Path(r"E:\Riobamba\equipamientos\salud\SALUD_CATEGORIZADO\SALUD.rar"),
            BASE_DIR / "SALUD_CATEGORIZADO.zip",
            Path(r"C:\Users\PC\Downloads\SALUD_CATEGORIZADO.zip"),
        ),
    ),
}


def get_categorized_isochrone_config(key: str) -> CategorizedIsochroneConfig:
    normalized = str(key or "").strip().lower()
    if normalized not in CATEGORIZED_ISOCHRONE_CONFIGS:
        available = ", ".join(sorted(CATEGORIZED_ISOCHRONE_CONFIGS))
        raise KeyError(f"Capa no soportada: {key}. Disponibles: {available}")
    return CATEGORIZED_ISOCHRONE_CONFIGS[normalized]


def iter_categorized_isochrone_configs() -> list[CategorizedIsochroneConfig]:
    return [CATEGORIZED_ISOCHRONE_CONFIGS[key] for key in sorted(CATEGORIZED_ISOCHRONE_CONFIGS)]
