import json
import math
import unicodedata
from pathlib import Path


OSM = Path(r"D:\codex\riobamba-censo-data\riobamba_osm_walk_network_5categorias_todas_plataformas.json")
OUT = Path(r"D:\codex\riobamba-camaras-data.js")


def norm(value):
    value = unicodedata.normalize("NFD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(value.lower().replace(".", "").replace(",", "").split())


def dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def load_roads():
    data = json.loads(OSM.read_text(encoding="utf-8"))
    roads = []
    for element in data["elements"]:
        tags = element.get("tags") or {}
        name = tags.get("name")
        geometry = element.get("geometry")
        if not name or not geometry:
            continue
        roads.append(
            {
                "name": name,
                "norm": norm(name),
                "points": [(point["lat"], point["lon"]) for point in geometry],
            }
        )
    return roads


ROADS = load_roads()


ALIASES = {
    "9 de octubre": ["9 de octubre", "avenida 9 de octubre"],
    "madrid": ["madrid", "diaz de la madrid"],
    "eloy alfaro": ["eloy alfaro", "avenida eloy alfaro"],
    "leopoldo freire": ["leopoldo freire", "avenida leopoldo freire"],
    "orozco": ["jose de orozco"],
    "loja": ["loja"],
    "veloz": ["jose veloz"],
    "pedro alvarado": ["alvarado"],
    "junin": ["junin"],
    "5 de junio": ["5 de junio"],
    "antonio jose de sucre": ["avenida antonio jose de sucre", "mariscal sucre"],
    "febres cordero": ["leon febres cordero"],
    "primera constituyente": ["primera constituyente"],
    "guayaquil": ["guayaquil"],
    "cristobal colon": ["cristobal colon", "avenida cristobal colon"],
    "daniel leon borja": ["avenida daniel leon borja"],
    "miguel angel leon": ["avenida miguel angel leon"],
    "carlos zambrano": ["avenida carlos zambrano"],
    "la prensa": ["avenida la prensa", "la prensa"],
    "carabobo": ["carabobo"],
    "pedro vicente maldonado": ["pedro vicente maldonado", "avenida pedro vicente maldonado"],
    "11 de noviembre": ["11 de noviembre", "avenida 11 de noviembre"],
    "victor emilio estrada": ["victor emilio estrada"],
    "calle v": ["calle v"],
    "colombia": ["colombia"],
    "morona": ["morona"],
    "argentinos": ["argentinos"],
    "juan lavalle": ["juan lavalle", "juan de lavalle"],
    "unidad nacional": ["avenida unidad nacional"],
    "duchicela": ["duchicela", "de los duchicelas"],
    "canonigo ramos": ["avenida canonigo ramos"],
    "teofilo saenz": ["teofilo saenz"],
    "lizarzaburu": ["avenida jose a lizarzaburu"],
    "alfonso chavez": ["avenida alfonso chavez"],
    "atahualpa": ["avenida atahualpa", "atahualpa villacres"],
    "san andres": ["san andres"],
    "panamericana sur": ["panamericana sur", "panamericana"],
    "juan felix proano": ["avenida juan felix proano"],
}

ALIASES.update({
    "ricardo descalzi": ["ricardo descalzi"],
    "agustin cueva": ["agustin cueva tamariz"],
    "cordobes": ["avenida luis cordovez", "luis a cordovez"],
    "espejo": ["eugenio espejo"],
    "olmedo": ["olmedo", "jose joaquin de olmedo"],
    "pichincha": ["pichincha"],
    "placido camacho": ["placido caamano"],
    "lizardo garcia": ["lizardo garcia"],
    "espana": ["espana"],
    "diego de ibarra": ["diego de ibarra"],
    "eplicachima": ["eplicachima"],
    "rey cacha": ["rey cacha"],
    "heroes": ["avenida heroes de tapi", "heroes del cenepa"],
    "comandante jimenez": ["jimenez"],
    "monseñor leonidas proaño": ["avenida monsenor leonidas proano"],
    "monseñor proaño": ["avenida monsenor leonidas proano"],
    "antonio lizarzaburu": ["avenida jose a lizarzaburu"],
    "agustin torres": ["agustin torres solis"],
    "padre lobato": ["padre lobato", "padre juan lobato"],
    "puna": ["puna"],
    "sangay": ["sangay"],
    "bucarest": ["bucarest"],
    "manuel benjamin carrion": ["manuel benjamin carrion", "manuel benjamin carrion mora"],
    "londres": ["londres"],
    "teniente hugo ortiz": ["teniente hugo ortiz"],
    "panamericana": ["panamericana", "panamericana sur"],
    "jaime roldos": ["jaime roldos aguilera"],
    "velasco ibarra": ["jose maria velasco ibarra", "velasco ibarra"],
    "puruha": ["puruha"],
    "buenos aires": ["buenos aires"],
    "rocafuerte": ["vicente rocafuerte"],
    "chile": ["chile"],
    "edelberto bonilla": ["avenida edelberto bonilla oleas", "avenida edelberto bonilla olea"],
    "araujo chiriboga": ["avenida araujo chiriboga", "araujo chiriboga"],
    "la opinion": ["la opinion"],
    "patria libre": ["patria libre"],
    "la paz": ["la paz"],
    "mexico": ["mexico"],
    "pedro bernan": ["pedro bernan"],
    "cuba": ["cuba"],
    "javier esponosa": ["javier donoso", "jose manuel espinoza"],
    "gaspar de villarroel": ["gaspar de villarroel"],
    "bernardo darquea": ["bernardo darquea"],
    "baron de carondelet": ["baron de carondelet"],
    "juan de velasco": ["juan de velasco"],
    "la valle": ["juan lavalle", "juan de lavalle"],
    "eduardo quigman": ["eduardo kingman"],
    "aracely gilbert": ["araceli gilbert"],
    "rio coca": ["rio coca"],
    "machupichus": ["machupichus"],
    "rio tomebamba": ["rio tomebamba"],
    "rio paute": ["rio paute"],
    "pedro donoso": ["pedro leon donoso", "p donoso", "d donoso"],
    "vicente ramon roca": ["vicente ramon roca"],
    "baquerizo moreno": ["gabriel garcia moreno"],
    "republica": ["via de la republica"],
    "gonzalo davalos": ["gonzalo davalos"],
    "los nogales": ["los nogales"],
    "juan montalvo": ["juan montalvo"],
    "roma": ["roma"],
    "amsterdam": ["amsterdam"],
    "francia": ["francia"],
    "baltazar paredes": ["baltazar", "diogenes paredes"],
    "argentina": ["argentina"],
    "santos leopoldo cabezas": ["santos leopoldo cabezas"],
    "diego novoa": ["diego noboa", "diego novoa"],
    "jose maria urvina": ["jose maria urbina"],
    "pallatanga": ["pallatanga"],
    "san andrez": ["san andres"],
    "milton reyes": ["avenida milton reyes"],
    "luis urdaneta": ["luis de rivera", "luis a costales"],
    "manuel zambrano": ["avenida carlos zambrano"],
})


def road_matches(query):
    candidates = ALIASES.get(query, [query])
    result = []
    for road in ROADS:
        name = road["norm"]
        if any(alias == name or alias in name for alias in candidates):
            result.append(road)
    return result


def geocode_pair(a, b):
    roads_a = road_matches(a)
    roads_b = road_matches(b)
    best = None
    for road_a in roads_a:
        for road_b in roads_b:
            for point_a in road_a["points"]:
                for point_b in road_b["points"]:
                    score = dist2(point_a, point_b)
                    if best is None or score < best[0]:
                        best = (score, point_a, point_b, road_a["name"], road_b["name"])
    if not best:
        return None
    lat = (best[1][0] + best[2][0]) / 2
    lon = (best[1][1] + best[2][1]) / 2
    meters = math.sqrt(best[0]) * 111_320
    return {
        "lat": round(lat, 7),
        "lng": round(lon, 7),
        "method": f"OSM local: {best[3]} / {best[4]}",
        "distanceMeters": round(meters, 1),
        "confidence": "alta" if meters <= 45 else "media" if meters <= 140 else "baja",
    }


MANUAL = {
    "RIO-012-DOMO": (-1.6538, -78.6676, "Aproximado: Av. La Prensa, sector Monumental Libro"),
    "RIO-027-DOMO": (-1.6848, -78.6768, "Aproximado: Av. Alfonso Chávez y vía de circunvalación"),
    "RIO-028-DOMO": (-1.6944, -78.6579, "Aproximado: Panamericana Sur y bypass"),
    "RIO-030-DOMO": (-1.6816, -78.6684, "Aproximado: Av. Circunvalación, Parque Ecológico"),
    "RIO-031-DOMO": (-1.6752, -78.6662, "Aproximado: Av. Circunvalación y Av. Juan Félix Proaño"),
}

MANUAL.update({
    "RIO-042-DOMO": (-1.6558, -78.6656, "Aproximado: Av. Canónigo Ramos, sector Distrito de Educación"),
    "RIO-051-DOMO": (-1.6562, -78.6702, "Aproximado: Parque Ricpamba"),
    "RIO-057-DOMO": (-1.6617, -78.6567, "Aproximado: sector La Opinión y Patria Libre"),
    "RIO-059-DOMO": (-1.6648, -78.6604, "Aproximado: La Paz y México"),
    "RIO-060-DOMO": (-1.6614, -78.6669, "Aproximado: Pedro Bernan y Cuba"),
    "RIO-063-DOMO": (-1.6572, -78.6596, "Aproximado: Av. Barón de Carondelet y Juan de Velasco"),
    "RIO-065-DOMO": (-1.6742, -78.6688, "Aproximado: Eduardo Kingman y Araceli Gilbert"),
    "RIO-068-LA": (-1.6636, -78.6546, "Aproximado: Centro Operativo Local Riobamba"),
    "RIO-073-DOMO": (-1.7794, -78.5994, "Aproximado: Mercado Central, parroquia Licto"),
    "RIO-074-DOMO": (-1.6309, -78.7058, "Aproximado: ingreso a Licán y Panamericana E35"),
    "RIO-080-DOMO": (-1.6467, -78.7501, "Aproximado: ingreso a Calpi y Panamericana E35"),
    "RIO-084-DOMO": (-1.7445, -78.6272, "Aproximado: salida a Macas, parroquia San Luis"),
    "RIO-087-FIJA": (-1.6685, -78.6512, "Aproximado: Santos Leopoldo Cabezas, donación La Georgina"),
    "RIO-088-FIJA": (-1.6687, -78.6510, "Aproximado: Santos Leopoldo Cabezas, donación La Georgina"),
    "RIO-090-FIJA": (-1.6662, -78.6497, "Aproximado: parque Galápagos"),
    "RIO-091-FIJA": (-1.6663, -78.6499, "Aproximado: parque Galápagos"),
    "RIO-094-FIJA": (-1.6262, -78.7832, "Aproximado: vía a Riobamba y Gabriel Moncayo, ingreso San Juan"),
    "RIO-095-FIJA": (-1.5980, -78.8050, "Aproximado: vía a Riobamba Pan. 492 la Y, salida al Chimborazo"),
    "RIO-096-FIJA": (-1.5984, -78.8054, "Aproximado: vía a Riobamba Pan. 492 la Y, salida al Chimborazo"),
    "RIO-097-FIJA": (-1.6050, -78.7980, "Aproximado: vía al Chimborazo la Y, ingreso La Delicia"),
    "RIO-098-FIJA": (-1.6120, -78.7900, "Aproximado: vía a Riobamba Pan. 492, Shobolpamba"),
})


CAMERAS = [
    ("RIO-001-DOMO", "DOMO", "9 de Octubre y Madrid", "Centro de privación de libertad de menores", "9 de octubre", "madrid", "NO", "SI"),
    ("RIO-002-DOMO", "DOMO", "Eloy Alfaro y Leopoldo Freire", "UNACH", "eloy alfaro", "leopoldo freire", "NO", "NO"),
    ("RIO-003-DOMO", "DOMO", "Orozco y Loja", "Cancha de Villa María", "orozco", "loja", "NO", "NO"),
    ("RIO-004-DOMO", "DOMO", "Veloz y Pedro Alvarado", "Parque San Francisco", "veloz", "pedro alvarado", "NO", "NO"),
    ("RIO-005-DOMO", "DOMO", "Junín y 5 de Junio", "Mercado San Alfonso", "junin", "5 de junio", "NO", "NO"),
    ("RIO-006-DOMO", "DOMO", "Antonio José de Sucre y Febres Cordero", "", "antonio jose de sucre", "febres cordero", "NO", "NO"),
    ("RIO-007-DOMO", "DOMO", "Primera Constituyente y 5 de Junio", "Parque Maldonado, BNF", "primera constituyente", "5 de junio", "NO", "NO"),
    ("RIO-008-FIJA", "FIJA", "Primera Constituyente y 5 de Junio", "Parque Maldonado, BNF", "primera constituyente", "5 de junio", "NO", "NO"),
    ("RIO-009-DOMO", "DOMO", "Guayaquil y Cristóbal Colón", "Mercado La Merced", "guayaquil", "cristobal colon", "NO", "NO"),
    ("RIO-010-DOMO", "DOMO", "Av. Daniel León Borja y Miguel Ángel León", "Plaza de toros", "daniel leon borja", "miguel angel leon", "SI", "SI"),
    ("RIO-011-DOMO", "DOMO", "Av. Daniel León Borja y Carlos Zambrano", "Parque Infantil", "daniel leon borja", "carlos zambrano", "SI", "NO"),
    ("RIO-012-DOMO", "DOMO", "Av. La Prensa y 9 de Julio", "Monumental Libro", None, None, "NO", "NO"),
    ("RIO-013-DOMO", "DOMO", "Av. 9 de Octubre y Carabobo", "", "9 de octubre", "carabobo", "NO", "NO"),
    ("RIO-014-DOMO", "DOMO", "Pedro Vicente Maldonado y Av. 11 de Noviembre", "Gasolinera Espoch", "pedro vicente maldonado", "11 de noviembre", "NO", "NO"),
    ("RIO-015-DOMO", "DOMO", "Av. Antonio José de Sucre y Víctor Emilio Estrada", "Shopping y UNACH", "antonio jose de sucre", "victor emilio estrada", "NO", "SI"),
    ("RIO-016-DOMO", "DOMO", "Leopoldo Freire y Calle V", "Cárcel de Mayores vía a Chambo", "leopoldo freire", "calle v", "NO", "NO"),
    ("RIO-017-FIJA", "FIJA", "Leopoldo Freire y Calle V", "Cárcel de Mayores vía a Chambo", "leopoldo freire", "calle v", "NO", "NO"),
    ("RIO-018-DOMO", "DOMO", "Colombia y Carabobo", "Mercado La Condamine", "colombia", "carabobo", "SI", "NO"),
    ("RIO-019-DOMO", "DOMO", "10 de Agosto y Morona", "", "10 de agosto", "morona", "NO", "SI"),
    ("RIO-020-DOMO", "DOMO", "Daniel León Borja y La Prensa", "", "daniel leon borja", "la prensa", "NO", "NO"),
    ("RIO-021-DOMO", "DOMO", "José de Orozco y Cristóbal Colón", "Plaza Roja", "orozco", "cristobal colon", "NO", "SI"),
    ("RIO-022-DOMO", "DOMO", "Argentinos y Juan Lavalle", "Iglesia de la Loma de Quito", "argentinos", "juan lavalle", "NO", "NO"),
    ("RIO-023-DOMO", "DOMO", "Unidad Nacional y Duchicela", "Monumento del Tren", "unidad nacional", "duchicela", "NO", "NO"),
    ("RIO-024-DOMO", "DOMO", "Av. 9 de Octubre y Duchicela", "", "9 de octubre", "duchicela", "NO", "NO"),
    ("RIO-025-DOMO", "DOMO", "Canónigo Ramos y Teófilo Sáenz", "Parque Sesquicentenario", "canonigo ramos", "teofilo saenz", "NO", "NO"),
    ("RIO-026-DOMO", "DOMO", "11 de Noviembre y Lizarzaburu", "", "11 de noviembre", "lizarzaburu", "NO", "NO"),
    ("RIO-027-DOMO", "DOMO", "Alfonso Chávez y Circunvalación", "", None, None, "NO", "NO"),
    ("RIO-028-DOMO", "DOMO", "Panamericana Sur y Bypass", "", None, None, "NO", "SI"),
    ("RIO-029-DOMO", "DOMO", "Av. Atahualpa y San Andrés", "Esquina", "atahualpa", "san andres", "NO", "NO"),
    ("RIO-030-DOMO", "DOMO", "Avenida Circunvalación", "Parque Ecológico", None, None, "NO", "NO"),
    ("RIO-031-DOMO", "DOMO", "Av. Circunvalación y Juan Félix Proaño", "", None, None, "NO", "NO"),
]

CAMERAS.extend([
    ("RIO-032-DOMO", "DOMO", "Ricardo Descalzi y Agustín Cueva", "", "ricardo descalzi", "agustin cueva", "NO", "NO"),
    ("RIO-033-DOMO", "DOMO", "Av. Cordobés y Espejo", "", "cordobes", "espejo", "SI", "NO"),
    ("RIO-034-DOMO", "DOMO", "Olmedo y Pichincha", "", "olmedo", "pichincha", "NO", "NO"),
    ("RIO-035-DOMO", "DOMO", "Plácido Camacho y Lizardo García", "", "placido camacho", "lizardo garcia", "NO", "SI"),
    ("RIO-036-DOMO", "DOMO", "10 de Agosto y España", "", "10 de agosto", "espana", "NO", "NO"),
    ("RIO-037-DOMO", "DOMO", "Primera Constituyente y Carabobo", "", "primera constituyente", "carabobo", "NO", "NO"),
    ("RIO-038-DOMO", "DOMO", "José Veloz y Diego de Ibarra", "", "veloz", "diego de ibarra", "NO", "NO"),
    ("RIO-039-DOMO", "DOMO", "Eplicachima y Rey Cacha", "", "eplicachima", "rey cacha", "NO", "NO"),
    ("RIO-040-DOMO", "DOMO", "Av. de los Héroes y Comandante Jiménez", "", "heroes", "comandante jimenez", "NO", "NO"),
    ("RIO-041-DOMO", "DOMO", "Av. José Lizarzaburu y Monseñor Leónidas Proaño", "", "lizarzaburu", "monseñor leonidas proaño", "NO", "NO"),
    ("RIO-042-DOMO", "DOMO", "Avenida Canónigo Ramos y Canal de Riego", "Distrito de Educación", None, None, "NO", "NO"),
    ("RIO-043-DOMO", "DOMO", "Avenida Antonio Lizarzaburu y Agustín Torres", "Multiplaza", "antonio lizarzaburu", "agustin torres", "NO", "NO"),
    ("RIO-044-DOMO", "DOMO", "Cristóbal Colón y Padre Lobato", "Parque Central", "cristobal colon", "padre lobato", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-045-DOMO", "DOMO", "Calle Puná y Sangay", "Barrio La Tarazana", "puna", "sangay", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-046-DOMO", "DOMO", "Av. Leopoldo Freire y Bucarest", "Mercado Mayorista", "leopoldo freire", "bucarest", "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-047-DOMO", "DOMO", "Monseñor Proaño y Manuel Benjamín Carrión", "", "monseñor proaño", "manuel benjamin carrion", "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-048-DOMO", "DOMO", "Londres y Juan Félix Proaño", "", "londres", "juan felix proano", "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-049-DOMO", "DOMO", "Teniente Hugo Ortiz y Panamericana", "", "teniente hugo ortiz", "panamericana", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-050-DOMO", "DOMO", "Jaime Roldós y José María Velasco Ibarra", "", "jaime roldos", "velasco ibarra", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-051-DOMO", "DOMO", "Parque Ricpamba", "", None, None, "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-052-DOMO", "DOMO", "Puruhá y Buenos Aires", "", "puruha", "buenos aires", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-053-DOMO", "DOMO", "Orozco y Miguel Ángel León", "", "orozco", "miguel angel leon", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-054-DOMO", "DOMO", "Rocafuerte y Chile", "", "rocafuerte", "chile", "SI", "SI", "GADM RIOBAMBA"),
    ("RIO-055-DOMO", "DOMO", "Edelberto Bonilla y Araujo Chiriboga", "", "edelberto bonilla", "araujo chiriboga", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-056-DOMO", "DOMO", "Leopoldo Freire y Quito", "", "leopoldo freire", "quito", "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-057-DOMO", "DOMO", "La Opinión y Patria Libre", "", None, None, "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-058-DOMO", "DOMO", "Av. 9 de Octubre y Pichincha", "", "9 de octubre", "pichincha", "NO", "SI", "MINEDUC"),
    ("RIO-059-DOMO", "DOMO", "La Paz y México", "", None, None, "NO", "NO", "MINEDUC"),
    ("RIO-060-DOMO", "DOMO", "Pedro Bernan y Cuba", "", None, None, "NO", "SI", "MINEDUC"),
    ("RIO-061-DOMO", "DOMO", "Av. Antonio José de Sucre y Javier Esponosa", "", "antonio jose de sucre", "javier esponosa", "NO", "SI", "MINEDUC"),
    ("RIO-062-DOMO", "DOMO", "Gaspar de Villarroel y Bernardo Darquea", "", "gaspar de villarroel", "bernardo darquea", "NO", "SI", "MINEDUC"),
    ("RIO-063-DOMO", "DOMO", "Av. Barón de Carondelet y Juan de Velasco", "", None, None, "NO", "SI", "MINEDUC"),
    ("RIO-064-DOMO", "DOMO", "Av. Unidad Nacional y La Valle", "", "unidad nacional", "la valle", "SI", "SI", "GADM RIOBAMBA"),
    ("RIO-065-DOMO", "DOMO", "Eduardo Quigman y Aracely Gilbert", "", None, None, "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-066-DOMO", "DOMO", "Panamericana Norte y Río Coca", "", "panamericana", "rio coca", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-067-DOMO", "DOMO", "Monseñor Leonidas Proaño y Machupichus", "Entrada CELEC", "monseñor leonidas proaño", "machupichus", "NO", "NO", "ECU911"),
    ("RIO-068-LA", "LA", "Centro Operativo Local Riobamba", "", None, None, "NO", "SI", "ECU911"),
    ("RIO-069-DOMO", "DOMO", "Río Tomebamba y Río Paute", "Parque Las Acacias", "rio tomebamba", "rio paute", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-070-DOMO", "DOMO", "Pedro Donoso y Av. Canónigo Ramos", "Campana de la Paz", "pedro donoso", "canonigo ramos", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-071-DOMO", "DOMO", "Vicente Ramón Roca y Baquerizo Moreno", "Cdla. Galápagos", "vicente ramon roca", "baquerizo moreno", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-072-DOMO", "DOMO", "10 de Agosto y Carabobo", "", "10 de agosto", "carabobo", "NO", "NO"),
    ("RIO-073-DOMO", "DOMO", "Mercado Central Parroquia Licto", "", None, None, "NO", "NO", "GADP LICTO"),
    ("RIO-074-DOMO", "DOMO", "Ingreso a Licán y Panamericana E35", "", None, None, "NO", "NO"),
    ("RIO-075-DOMO", "DOMO", "Av. de la República y Monseñor Leonidas Proaño", "", "republica", "monseñor leonidas proaño", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-076-DOMO", "DOMO", "Av. de los Héroes y Gonzalo Dávalos", "", "heroes", "gonzalo davalos", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-077-DOMO", "DOMO", "Villarroel y Juan Montalvo", "", "gaspar de villarroel", "juan montalvo", "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-078-DOMO", "DOMO", "Olmedo y Juan de Velasco", "", "olmedo", "juan de velasco", "NO", "SI", "GADM RIOBAMBA"),
    ("RIO-079-DOMO", "DOMO", "Roma y Amsterdam", "", "roma", "amsterdam", "NO", "NO", "GADM RIOBAMBA"),
    ("RIO-080-DOMO", "DOMO", "Ingreso a Calpi y Panamericana E35", "", None, None, "NO", "NO"),
    ("RIO-081-FIJA", "FIJA", "Av. Unidad Nacional y Diego de Ibarra", "", "unidad nacional", "diego de ibarra", "NO", "NO"),
    ("RIO-082-FIJA", "FIJA", "Colombia y Francia", "", "colombia", "francia", "NO", "NO"),
    ("RIO-083-DOMO", "DOMO", "Vicente Ramón Roca y Jaime Roldós Aguilera", "Cdla. Galápagos", "vicente ramon roca", "jaime roldos", "NO", "NO", "BARRIO GALAPAGOS"),
    ("RIO-084-DOMO", "DOMO", "Av. Juan Félix Proaño y salida a Macas", "", None, None, "NO", "NO", "GDPSAN LUIS"),
    ("RIO-085-DOMO", "DOMO", "José de Orozco y Baltazar Paredes", "", "orozco", "baltazar paredes", "SI", "NO", "DONACIÓN LA GEORGINA"),
    ("RIO-086-DOMO", "DOMO", "Av. La Prensa y Argentinos", "", "la prensa", "argentinos", "SI", "NO", "DONACIÓN LA GEORGINA"),
    ("RIO-087-FIJA", "FIJA", "Santos Leopoldo Cabezas y SN", "", None, None, "SI", "NO", "DONACIÓN LA GEORGINA"),
    ("RIO-088-FIJA", "FIJA", "Santos Leopoldo Cabezas y SN", "", None, None, "NO", "NO", "DONACIÓN LA GEORGINA"),
    ("RIO-089-FIJA", "FIJA", "Jaime Roldós Aguilera y Diego Novoa", "", "jaime roldos", "diego novoa", "NO", "NO", "BARRIO GALAPAGOS"),
    ("RIO-090-FIJA", "FIJA", "José María Urvina y Calle SN", "Parque Galápagos", None, None, "NO", "NO", "BARRIO GALAPAGOS"),
    ("RIO-091-FIJA", "FIJA", "José María Urvina y Calle SN", "Parque Galápagos", None, None, "NO", "NO", "BARRIO GALAPAGOS"),
    ("RIO-092-FIJA", "FIJA", "José María Urvina y Antonio José de Sucre", "", "jose maria urvina", "antonio jose de sucre", "NO", "NO", "BARRIO GALAPAGOS"),
    ("RIO-093-FIJA", "FIJA", "Diego Novoa y Antonio José de Sucre", "", "diego novoa", "antonio jose de sucre", "NO", "NO", "BARRIO GALAPAGOS"),
    ("RIO-094-FIJA", "FIJA", "Vía a Riobamba y Gabriel Moncayo", "Estadio ingreso San Juan", None, None, "NO", "NO", "GADP SAN JUAN"),
    ("RIO-095-FIJA", "FIJA", "Vía a Riobamba Pan. 492 la Y y Chaupi salida al Chimborazo", "", None, None, "NO", "NO", "GADP SAN JUAN"),
    ("RIO-096-FIJA", "FIJA", "Vía a Riobamba Pan. 492 la Y y Chaupi salida al Chimborazo", "", None, None, "NO", "NO", "GADP SAN JUAN"),
    ("RIO-097-FIJA", "FIJA", "Vía al Chimborazo la Y ingreso La Delicia", "", None, None, "NO", "NO", "GADP SAN JUAN"),
    ("RIO-098-FIJA", "FIJA", "Vía a Riobamba Pan. 492 Shobolpamba", "", None, None, "NO", "NO", "GADP SAN JUAN"),
    ("RIO-099-DOMO", "DOMO", "Av. Gonzalo Dávalos y Los Nogales", "", "gonzalo davalos", "los nogales", "SI", "NO"),
    ("RIO-100-FIJA", "FIJA", "Av. Gonzalo Dávalos y Los Nogales", "", "gonzalo davalos", "los nogales", "NO", "NO"),
    ("RIO-101-DOMO", "DOMO", "Pallatanga y San Andrez", "", "pallatanga", "san andrez", "SI", "NO"),
    ("RIO-102-DOMO", "DOMO", "Av. 11 de Noviembre y Milton Reyes", "", "11 de noviembre", "milton reyes", "NO", "NO"),
    ("RIO-103-DOMO", "DOMO", "Luis Urdaneta y Manuel Zambrano", "", "luis urdaneta", "manuel zambrano", "SI", "NO"),
])


features = []
for idx, row in enumerate(CAMERAS[:30], 1):
    camera_id, camera_type, address, reference, street_a, street_b, megaphone, change = row[:8]
    institution = row[8] if len(row) > 8 else "ECU 911 Riobamba"
    located = geocode_pair(street_a, street_b) if street_a and street_b else None
    if camera_id in MANUAL:
        lat, lng, method = MANUAL[camera_id]
        located = {
            "lat": lat,
            "lng": lng,
            "method": method,
            "distanceMeters": None,
            "confidence": "media",
        }
    if not located:
        angle = idx * 2.399963
        radius = 0.003 + (idx % 9) * 0.00055
        located = {
            "lat": round(-1.6636 + math.sin(angle) * radius, 7),
            "lng": round(-78.6546 + math.cos(angle) * radius, 7),
            "method": "Aproximado: punto referencial urbano por falta de cruce verificable en OSM local",
            "distanceMeters": None,
            "confidence": "baja",
        }
    features.append(
        {
            "n": idx,
            "id": camera_id,
            "type": camera_type,
            "address": address,
            "reference": reference,
            "megaphone": megaphone == "SI",
            "requiresChange": change == "SI",
            "lat": located["lat"],
            "lng": located["lng"],
            "method": located["method"],
            "distanceMeters": located["distanceMeters"],
            "confidence": located["confidence"],
            "institution": institution,
        }
    )

OUT.write_text(
    "window.RIOBAMBA_CAMERAS_DATA = "
    + json.dumps(
        {
            "sourcePdf": r"C:\Users\PC\Downloads\INFORME ESTADO DE CÁMARAS CANTÓN RIOBAMBA.pdf",
            "note": "Subconjunto de 30 cámaras usado en el visor: RIO-001 a RIO-030 del informe.",
            "cameras": features,
        },
        ensure_ascii=False,
        indent=2,
    )
    + ";\n",
    encoding="utf-8",
)
print(f"Wrote {len(features)} cameras to {OUT}")
print(json.dumps(features, ensure_ascii=False, indent=2))
