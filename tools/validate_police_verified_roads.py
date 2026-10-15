"""Check every proposed junction against raw OSM source vertices, not displayed labels."""
import json
from pathlib import Path
import geopandas as gpd
from shapely import force_2d
from review_police_verified_main_roads import OUT, ROADS, PACKAGE, PRINCIPAL, normalized, separated
from review_police_kde_intersections import parts, source_hash


def main():
    report=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    proposals=gpd.read_file(OUT/'REVISION_POLICIA_30.gpkg',layer='PROPUESTA_POLICIA_30_REVISION')
    current=gpd.read_file(PACKAGE,layer='PROPUESTA_POLICIA_30_FINAL')
    roads=gpd.read_file(ROADS).to_crs(32717)
    roads['KEY']=roads.osm_id.astype(str)
    assert proposals.crs.to_epsg()==32717 and len(proposals)==30
    assert proposals.ID_POLICIA.is_unique and set(proposals.ID_POLICIA)==set(current.ID_POLICIA)
    assert proposals.geometry.is_valid.all() and proposals.geometry.to_wkb().nunique()==30
    checks=[]
    for row in proposals.itertuples():
        ids=row.OSM_IDS.split(' | ')
        source=roads.loc[roads.KEY.isin(ids)]
        assert set(source.KEY)==set(ids)
        xy=(row.geometry.x,row.geometry.y)
        arms=set()
        for way in source.itertuples():
            assert not separated(way.bridge) and not separated(way.tunnel)
            found=False
            for line in parts(force_2d(way.geometry)):
                coords=[tuple(c[:2]) for c in line.coords]
                for i,c in enumerate(coords):
                    if c!=xy:
                        continue
                    found=True
                    for j in (i-1,i+1):
                        if 0<=j<len(coords) and coords[j]!=xy:
                            arms.add(coords[j])
            assert found, f'{row.ID_POLICIA}: no es vertice original de {way.osm_id}'
        assert len(arms)>=3 and len({normalized(v) for v in source['name'] if normalized(v)})>=2
        assert source.highway.isin(PRINCIPAL).any()
        checks.append({'id':row.ID_POLICIA,'sourceVertexVerified':True,'arms':len(arms),
            'osmIds':ids,'principalNames':source.loc[source.highway.isin(PRINCIPAL),'name'].dropna().unique().tolist(),
            'displacementM':row.DESPLAZAMIENTO_M})
    assert all(source_hash(Path(p))==h for p,h in report['sourceHashes'].items())
    assert report['applied'] is False and report['published'] is False
    validation={'passed':True,'proposals':30,'uniquePositions':30,'crs':'EPSG:32717',
        'originalsAndPublicSelectionUnchanged':True,'sharedSourceVerticesVerified':True,
        'bridgeTunnelAndUnconnectedCrossingsRejected':True,'checks':checks,
        'requiresReviewOfLongMovesAndCoverageLoss':True,'applied':False,'published':False}
    (OUT/'VALIDACION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'proposals':30,'sourcesUnchanged':True,'published':False}))


if __name__=='__main__':
    main()
