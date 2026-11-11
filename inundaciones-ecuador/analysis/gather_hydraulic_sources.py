"""Fetch public service metadata and official susceptibility intersections. No credentials."""
import concurrent.futures as cf,datetime,json,pathlib,urllib.request,urllib.parse
ROOT=pathlib.Path(__file__).parent;RAW=ROOT/'raw'/'hydraulic';RAW.mkdir(parents=True,exist_ok=True)
SERVICE='https://sgrportal.gestionderiesgos.gob.ec/server/rest/services/Susceptibilidad_de_Inundaciones/MapServer'
def get(url,name):
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'EcuadorHydraulicDataInventory/1.0'})
        with urllib.request.urlopen(req,timeout=35) as r:
            body=r.read();(RAW/name).write_bytes(body)
            return {'url':url,'status':r.status,'bytes':len(body),'local':name,'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    except Exception as e:return {'url':url,'error':str(e),'local':name}
def query(c):
    q=urllib.parse.urlencode({'f':'json','where':'1=1','geometry':f"{c['lon']},{c['lat']}",'geometryType':'esriGeometryPoint','inSR':4326,'spatialRel':'esriSpatialRelIntersects','outFields':'dpa_descan,dpa_despro,sui,descr,dpa_anio','returnGeometry':'false'})
    result=get(SERVICE+'/0/query?'+q,f"sngr-point-{c['id']}.json")
    if 'error' not in result:
        j=json.loads((RAW/result['local']).read_text(encoding='utf-8'))
        result['features']=j.get('features',[]);result['service_error']=j.get('error')
    return c['id'],result
def main():
    checks=[(SERVICE+'?f=pjson','sngr-service.json'),(SERVICE+'/0?f=pjson','sngr-layer.json'),
      ('https://services.inamhi.gob.ec/','inamhi-services.html'),
      ('https://servicios.inamhi.gob.ec/aplicaciones-web/','inamhi-apps.html'),
      ('https://www.inocar.mil.ec/web/index.php/productos','inocar-products.html'),
      ('https://www.hydrosheds.org/products/hydrorivers','hydrorivers.html'),
      ('https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/','jrc-index.html')]
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda x:get(*x),checks))
    print(json.dumps(results,ensure_ascii=False),flush=True)
    cat=json.loads((ROOT/'dist/data/cities.json').read_text(encoding='utf-8'))
    with cf.ThreadPoolExecutor(max_workers=5) as pool:points=dict(pool.map(query,cat['cities']))
    for c in cat['cities']:
        q=points[c['id']]
        c['sngr_point']={'status':'ok' if 'error' not in q and not q.get('service_error') else 'unavailable','features':[f['attributes'] for f in q.get('features',[])],
            'note':'Intersección únicamente en el punto de referencia; no representa toda la ciudad. Sin coincidencia no significa sin amenaza.','url':SERVICE+'/0','checked':'2026-11-11'}
        if c['id']=='3655131':
            c['geonames_original_province']=c['province'];c['province']='Santa Elena';c['code']='25';c['province_note']='Corrección administrativa: La Libertad pertenece a Santa Elena; GeoNames mantiene el código anterior.'
        if c['name']=='Eloy Alfaro':c['geonames_original_name']=c['name'];c['name']='Durán (Eloy Alfaro)'
        if c['name']=='Santo Domingo de los Colorados':c['geonames_original_name']=c['name'];c['name']='Santo Domingo'
    (ROOT/'dist/data/cities.json').write_text(json.dumps(cat,ensure_ascii=False,indent=1),encoding='utf-8')
    (ROOT/'hydraulic-access-checks.json').write_text(json.dumps({'services':results,'point_queries':points},ensure_ascii=False,indent=1),encoding='utf-8')
    print('SNGR checked',sum(c['sngr_point']['status']=='ok' for c in cat['cities']),'of',len(cat['cities']),flush=True)
if __name__=='__main__':main()
