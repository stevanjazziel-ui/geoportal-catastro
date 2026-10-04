"""Normalize exported proposal fields to the explicitly documented final context."""
import json
from review_police_camera_efficiency import OUT, PACKAGE, records, read_layer, export, write_json, write_csv, report


def main():
    data=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    rows=records(read_layer(OUT/'PROPUESTA_POLICIA_30_REVISION.gpkg','PROPUESTA_POLICIA_30_REVISION'))
    for _,p in rows:
        p['SELECCIONADO']=True
        for cat,field in [('DELINCUENCIA','EVENTOS_D_EXCLUSIVOS_FINAL'),('VIOLENCIA','EVENTOS_V_EXCLUSIVOS_FINAL'),('CONVIVENCIA','EVENTOS_C_EXCLUSIVOS_FINAL')]:
            p['NUEVOS_EVENTOS_'+cat+'_CUBIERTOS']=p[field]
    info=export('PROPUESTA_POLICIA_30_REVISION',rows)
    data['proposals']=[p for _,p in rows]
    data['layers']=[info if r['name']==info['name'] else r for r in data['layers']]
    for name,source,visual in [
        ('RADIOS_ALTERNATIVAS',[(g.buffer(200,quad_segs=64),p) for g,p in records(read_layer(OUT/'PROPUESTA_POLICIA_30_REVISION.gpkg','COMPARACION_ALTERNATIVAS'))],True),
        ('CANDIDATOS_ORIGINALES',records(read_layer(PACKAGE,'CANDIDATOS_POLICIA')),False),
        ('LIMITE_CANTONAL',records(read_layer(PACKAGE,'LIMITE_CANTONAL')),True)]:
        data['layers']=[r for r in data['layers'] if r['name']!=name]+[export(name,source,visual)]
    write_csv('PROPUESTA_POLICIA_30_REVISION.csv',data['proposals'])
    write_json('RESULTADOS.json',data)
    report(data)


if __name__=='__main__':main()
