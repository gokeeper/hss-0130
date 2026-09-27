#!/usr/bin/env python3
"""Re-import exported STEP/STL files and independently verify delivered geometry."""
from pathlib import Path
import json, math
import cadquery as cq
import ezdxf
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parents[1]

def getshape(path):
    return cq.importers.importStep(str(path)).val()

def dims(sh):
    b=sh.BoundingBox()
    return [b.xlen,b.ylen,b.zlen]

def cylindrical_axes(sh,radius):
    points=[]
    for f in sh.Faces():
        if f.geomType() != 'CYLINDER':
            continue
        c=f._geomAdaptor().Cylinder()
        if abs(c.Radius()-radius)>1e-5 or abs(c.Axis().Direction().Z())<.99999:
            continue
        a=c.Axis().Location()
        xy=(a.X(),a.Y())
        if all(math.dist(xy,p)>1e-5 for p in points):
            points.append(xy)
    return points

def main():
    r={}
    for folder,tag,factor in [('full_size','1to1',1),('scale_200mm','200mm',200/738)]:
        sh=getshape(ROOT/folder/f'HSS0130_v2_assembly_{tag}.step')
        ss=sh.Solids()
        r[folder]={'valid':bool(sh.isValid()),'solids':len(ss),'bbox_mm':dims(sh),
                    'volumes_mm3':sorted(s.Volume() for s in ss)}
        assert sh.isValid() and len(ss)==3
        assert np.allclose(dims(sh),np.array([738,230,70])*factor,atol=2e-5)
        for i in range(3):
            for j in range(i+1,3):
                assert abs(ss[i].intersect(ss[j]).Volume())<1e-5
    assert np.allclose(np.array(r['full_size']['volumes_mm3'])*(200/738)**3,
                       r['scale_200mm']['volumes_mm3'],rtol=2e-8,atol=1e-6)
    r['STEP_uniform_volume_scaling_verified']=True
    layers=['0','P1_BUTTONS_30','P2_BUTTONS_30','P1_JLF_MOUNT_HOLES','P2_JLF_MOUNT_HOLES']
    ws=cq.importers.importDXF(str(ROOT/'input/panel_source_2L16B.dxf'),include=layers).wires().vals()
    ow=max(ws,key=lambda w:w.Length());inn=[w for w in ws if w is not ow]
    b=ow.BoundingBox();translation=(-(b.xmin+b.xmax)/2,-65.8-b.ymax,68)
    expected=cq.Solid.extrudeLinear(ow,inn,cq.Vector(0,0,2)).translate(translation)
    actual=getshape(ROOT/'full_size/HSS0130_v2_panel_source_DXF_1to1.step')
    diff=abs(actual.cut(expected).Volume())+abs(expected.cut(actual).Volume())
    r['exact_source_panel']={'DXF_outer_edges':len(ow.Edges()),'DXF_internal_wires':len(inn),
                             'symmetric_difference_after_STEP_roundtrip_mm3':diff,
                             'outer_curve_types':[e.geomType() for e in ow.Edges()]}
    assert diff<1e-5 and len(inn)==34 and len(ow.Edges())==10
    alt=getshape(ROOT/'full_size/HSS0130_v2_panel_JLF_40x85_alternative_1to1.step')
    axes_source=cylindrical_axes(actual,2.25)
    axes_alt=cylindrical_axes(alt,2.25)
    r['JLF_holes_source_xy']=sorted(axes_source)
    r['JLF_holes_alternative_xy']=sorted(axes_alt)
    assert len(axes_source)==8 and len(axes_alt)==8
    for pts,dx,dy in [(axes_source,50,73),(axes_alt,40,85)]:
        for xo in [-245.412,113.977]:
            sel=[p for p in pts if abs(p[0]-xo)<30]
            assert len(sel)==4
            assert abs((max(p[0] for p in sel)-min(p[0] for p in sel))-dx)<1e-5
            assert abs((max(p[1] for p in sel)-min(p[1] for p in sel))-dy)<1e-5
    r['all_delivered_STLs_closed_and_positive']=True
    r['STL_count']=0
    for p in ROOT.rglob('*.stl'):
        m=trimesh.load_mesh(p,process=True)
        assert m.is_watertight and m.is_winding_consistent and m.volume>0,p
        r['STL_count']+=1
    tiles=[]
    for p in sorted((ROOT/'fit_test_1to1').glob('*tile*.stl')):
        m=trimesh.load_mesh(p,process=True)
        assert m.extents[0]<200 and m.extents[1]<200 and len(m.split())==1
        tiles.append({'file':p.name,'bbox_mm':m.extents.tolist()})
    r['fit_tiles']=tiles
    layout=trimesh.load(ROOT/'scale_200mm/HSS0130_v2_three_parts_layout_200mm.3mf')
    r['3MF']={'parts':len(layout.geometry),'bbox_mm':layout.extents.tolist()}
    assert len(layout.geometry)==3 and all(s<220 for s in layout.extents[:2])
    r['physical_print_fit_and_load_test']='NOT PERFORMED'
    (ROOT/'export_roundtrip_check.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
