"""Map exported SWMM flooding to surface cells, preserving step-integrated volume.

Usage: python swmm_surface_exchange.py SWMM_OUTPUT mapping.json new-forcing.json
mapping.json: {"source":..., "geometry_evidence":..., "nodes":{"node_id":[[row,col]]}}
One-way surcharge overflow only. It does not compute inlet capture or surface feedback.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def export(directory,mapping,output):
    directory=Path(directory);mapping=Path(mapping);output=Path(output)
    if output.exists():raise FileExistsError('Use a new forcing file')
    cfg=json.loads(mapping.read_text(encoding='utf-8'))
    if not cfg.get('source') or not cfg.get('geometry_evidence'):raise ValueError('Mapping provenance is required')
    series={k:[] for k in cfg['nodes']}
    with (directory/'nodes.csv').open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['node'] in series:series[row['node']].append((float(row['seconds']),float(row['flood_m3_s'])))
    ports=[]
    for node,rows in series.items():
        if len(rows)<2 or rows[0][0]!=0:raise ValueError('Missing node or incomplete time series')
        ports.append({'id':f'swmm_overflow_{node}','kind':'swmm_prescribed_exchange','cells':cfg['nodes'][node],
                      'seconds':[t for t,q in rows],'m3_s':[q for t,q in rows],'interpolation':'interval_end',
                      'source':f"{cfg['source']}; node export SHA256={hashlib.sha256((directory/'nodes.csv').read_bytes()).hexdigest()}"})
    if not ports:raise ValueError('No mapped nodes')
    forcing={'surface_exchange':ports,'stage_boundaries':[],'mapping_evidence':cfg['geometry_evidence'],
             'limitation':'One-way SWMM flooding only. Surface feedback and drainage capture are not computed. Avoid double counting network runoff and surface rainfall.'}
    output.write_text(json.dumps(forcing,ensure_ascii=False,indent=2),encoding='utf-8')
    return forcing


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('mapping');p.add_argument('output');a=p.parse_args();export(a.directory,a.mapping,a.output)
