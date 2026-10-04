"""Explain the cycle-loss constraint; never overwrite the official municipal solution."""
import json
import time
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix,csr_matrix
from shapely.ops import unary_union
from close_final_camera_study import (OUT,PREVIOUS,MUNICIPAL_SOURCE,KEYS,read_layer,records,
    coverage,corridor_atoms,jsave,pct)


def main():
    data=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    cameras=records(read_layer(PREVIOUS,'CAMARAS_EXISTENTES_103_CONSOLIDADA'))
    municipal=records(read_layer(PREVIOUS,'PROPUESTA_50_CONSOLIDADA'))
    candidates=records(read_layer(OUT/'MUNICIPALES_CHECKPOINT.gpkg','CANDIDATOS'))
    fixed=coverage(cameras+[r for r in municipal if r[1]['GRUPO']!='RED_ESTRUCTURAL'])
    axes={p['CORREDOR']:g for g,p in records(read_layer(PREVIOUS,'CORREDORES_CONSOLIDADOS'))}
    atoms,totals,base=corridor_atoms(axes,candidates,fixed)
    n,m=len(candidates),len(atoms);rows=[];cols=[];values=[]
    for j,(_,support,_) in enumerate(atoms):
        rows.append(j);cols.append(n+j);values.append(1.)
        for i in support:rows.append(j);cols.append(i);values.append(-1.)
    matrix=coo_matrix((values,(rows,cols)),shape=(m,n+m)).tocsr()
    lengths={key:np.array([0.]*n+[length if kind==key else 0. for kind,_,length in atoms]) for key in KEYS}
    counts=csr_matrix(([1.]*n,([0]*n,list(range(n)))),shape=(1,n+m))
    cycle_before=next(r for r in data['corridors'] if r['ESCENARIO']=='B_ANTERIOR' and r['CORREDOR']==KEYS[2])['CUBIERTO_M']
    ring_final=next(r for r in data['corridors'] if r['ESCENARIO']=='B' and r['CORREDOR']==KEYS[1])['CUBIERTO_M']
    constraints=[LinearConstraint(matrix,-np.inf,0),LinearConstraint(csr_matrix(lengths[KEYS[0]][None,:]),.98*totals[KEYS[0]]-base[KEYS[0]],np.inf),
        LinearConstraint(csr_matrix(lengths[KEYS[2]][None,:]),cycle_before-base[KEYS[2]]-.001,np.inf)]
    integrality=np.array([1]*n+[0]*m)
    output={'purpose':'Diagnostico exclusivo de compromiso, NO sustituye solucion oficial ni cambia cantidades/metodologia',
        'cycleRetentionPct':pct(cycle_before,totals[KEYS[2]]),'mainRingPct':pct(ring_final,totals[KEYS[1]]),'scenarios':[]}
    for label,objective,more in (
        ('24estructurales,conservarCiclovias,maximizarAnillo',-lengths[KEYS[1]],[LinearConstraint(counts,24,24)]),
        ('Minimoestructurales,conservarAnilloyCiclovias',np.array([1.]*n+[0.]*m),[LinearConstraint(counts,24,np.inf),LinearConstraint(csr_matrix(lengths[KEYS[1]][None,:]),ring_final-base[KEYS[1]]-.001,np.inf)])):
        start=time.monotonic()
        solution=milp(objective,integrality=integrality,bounds=Bounds(np.zeros(n+m),np.ones(n+m)),
            constraints=constraints+more,options={'time_limit':180,'mip_rel_gap':1e-6})
        entry={'case':label,'status':int(solution.status),'message':solution.message,'seconds':time.monotonic()-start}
        if solution.x is not None:
            selected=np.flatnonzero(solution.x[:n]>.5).tolist()
            mask=unary_union([fixed]+[candidates[i][0].buffer(200,quad_segs=64) for i in selected])
            entry.update({'structuralCameras':len(selected),'municipalTotal':len(selected)+26,
                'percent':{key:pct(axes[key].intersection(mask).length,totals[key]) for key in KEYS},
                'mipGap':float(solution.mip_gap),'dualBound':float(solution.mip_dual_bound),
                'candidateIds':[candidates[i][1]['ID_CANDIDATO'] for i in selected]})
        output['scenarios'].append(entry);jsave('DIAGNOSTICO_COMPROMISO_CICLOVIAS.json',output)
        print(json.dumps(entry),flush=True)


if __name__=='__main__':main()
