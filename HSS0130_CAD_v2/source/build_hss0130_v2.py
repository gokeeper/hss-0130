#!/usr/bin/env python3
"""HSS-0130 v2: exact uploaded panel DXF, estimated outer shell, designed internals.
Units: mm. Right-handed CAD: X right, Y away from player, Z up; rear datum Y=0,
front is Y=-230. Source panel maps by translation (x-316, y-194.8).
Build: python build_hss0130_v2.py --out .. --small-width 200
Source DXF is never regenerated from the rounded coordinates in the feedback.
"""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math, sys, time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Any
import cadquery as cq
import ezdxf
import numpy as np
import trimesh
from shapely.geometry import Polygon, Point
from outer_geometry import footprint, offset, prism, rounded_rect

EPS=1e-4
BOTTOM_HOLES=[(-340,-15),(-100,-15),(100,-15),(340,-15),
              (-345,-185),(-105,-210),(105,-210),(345,-185)]

@dataclass
class Parameters:
    width: float=738.0
    depth: float=230.0
    height: float=70.0
    front_bulge: float=20.0
    front_corner_radius: float=30.0
    rear_corner_radius: float=12.0
    top_edge_radius: float=6.0
    bottom_edge_radius: float=1.5
    wall: float=5.0
    deck_thickness: float=10.0
    bottom_recess_inset: float=3.0
    bottom_thickness: float=4.5
    bottom_clearance: float=0.8
    panel_rear_distance: float=65.8
    panel_thickness: float=2.0
    panel_clearance: float=0.8
    panel_support_land: float=5.0
    panel_boss_radius: float=9.0
    panel_boss_height: float=16.0
    fastener_hole_diameter: float=4.5
    carriage_neck_relief_width: float=5.0
    carriage_neck_relief_depth: float=2.0
    nut_across_flats: float=7.4
    nut_pocket_depth: float=3.4
    bottom_boss_radius: float=9.0
    bottom_boss_height: float=12.0
    bottom_bridge_width: float=8.0
    button_keepout_diameter: float=40.0
    joystick_keepout_width: float=80.0
    joystick_keepout_depth: float=110.0
    keepout_extra_clearance: float=0.3
    joystick_installation_depth_design: float=50.0
    button_installation_depth_design: float=50.0
    rib_width: float=4.0
    rib_drop: float=10.0
    rib_side_offset: float=48.0
    cable_exit_diameter: float=10.0
    cable_exit_x: float=0.0
    cable_exit_z: float=22.0
    pcb_posts_enabled: bool=True
    pcb_x: float=0.0
    pcb_y: float=-35.0
    pcb_hole_pitch_x: float=58.0
    pcb_hole_pitch_y: float=28.0
    pcb_post_radius: float=4.5
    pcb_post_height: float=8.0
    pcb_hole_diameter: float=3.2
    instruction_width: float=550.0
    instruction_depth: float=42.0
    instruction_x: float=50.0
    instruction_y: float=-29.0
    instruction_recess_depth: float=1.0
    label_width: float=100.0
    label_depth: float=35.0
    label_x: float=-284.0
    label_y: float=-33.0
    label_recess_depth: float=1.0
    fit_ring_outer_margin: float=6.0
    fit_ring_height: float=10.0
    fit_tile_count: int=4
    fit_tie_width: float=3.0
    fit_tie_thickness: float=1.5
    visual_groove_depth: float=1.0
    visual_hole_depth: float=2.0
    mesh_tolerance: float=0.06
    mesh_angular_tolerance: float=0.10


def log(s: str) -> None:
    print(time.strftime('%H:%M:%S'),s,flush=True)

def bbox(s: cq.Shape)->list[float]:
    b=s.BoundingBox();return [float(b.xlen),float(b.ylen),float(b.zlen)]

def cylinder(x:float,y:float,r:float,z:float,h:float)->cq.Solid:
    return cq.Solid.makeCylinder(r,h,cq.Vector(x,y,z))

def box(x:float,y:float,w:float,d:float,z:float,h:float)->cq.Solid:
    return cq.Solid.makeBox(w,d,h,cq.Vector(x-w/2,y-d/2,z))

def hexagon(x:float,y:float,af:float,z:float,h:float)->cq.Solid:
    return (cq.Workplane('XY').center(x,y).polygon(6,2*af/math.sqrt(3))
            .extrude(h).val().translate((0,0,z)))

def union(shapes:list[cq.Shape])->cq.Shape:
    if not shapes: raise ValueError('empty union')
    return shapes[0].fuse(*shapes[1:]).clean() if len(shapes)>1 else shapes[0]

def assert_solid(name:str,s:cq.Shape)->None:
    if not s.isValid() or len(s.Solids())!=1 or s.Volume()<=0:
        raise RuntimeError(f'{name}: invalid/empty/multiple solids ({len(s.Solids())})')

def check_params(p:Parameters)->None:
    for f in fields(p):
        v=getattr(p,f.name)
        if not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError(f.name)
    if not 0<p.panel_thickness<p.deck_thickness<p.height:raise ValueError('panel/deck/height')
    if not 0<p.bottom_recess_inset<p.wall:raise ValueError('wall/bottom recess')
    if p.bottom_recess_inset+p.bottom_clearance>=p.wall:raise ValueError('bottom support lost')
    if not 0<p.panel_clearance<3:raise ValueError('panel clearance')
    if p.height-p.panel_thickness-p.bottom_thickness < max(p.joystick_installation_depth_design,p.button_installation_depth_design):
        raise ValueError('not enough component clearance for design installation depth')
    if p.panel_boss_radius<=p.nut_across_flats/math.sqrt(3)+1:raise ValueError('boss too small')
    if p.panel_boss_height < p.nut_pocket_depth+p.carriage_neck_relief_depth+2:raise ValueError('boss too short')


def load_panel(path:Path,p:Parameters)->dict[str,Any]:
    doc=ezdxf.readfile(str(path))
    if doc.header.get('$INSUNITS')!=4:raise ValueError('Source DXF must use mm ($INSUNITS=4)')
    layers=['0','P1_BUTTONS_30','P2_BUTTONS_30','P1_JLF_MOUNT_HOLES','P2_JLF_MOUNT_HOLES']
    # Only manufacturing layers. REFERENCE layers contain open lines, not cuts.
    ws=cq.importers.importDXF(str(path),include=layers).wires().vals()
    outer=max(ws,key=lambda w:w.Length())
    ob=outer.BoundingBox()
    if abs(ob.xlen-632)>1e-5 or abs(ob.ylen-129)>1e-5:raise ValueError('unexpected source outline')
    dx=-(ob.xmin+ob.xmax)/2;dy=-p.panel_rear_distance-ob.ymax
    move=(dx,dy,0)
    outer=outer.translate(move)
    holes=[w.translate(move) for w in ws if w is not max(ws,key=lambda w:w.Length())]
    # 'is' is safe here because max returns the same object retained in ws.
    squares=[w for w in holes if len(w.Edges())==4 and abs(w.BoundingBox().xlen-4.6)<1e-5]
    mounts=sorted([(w.Center().x,w.Center().y) for w in squares],key=lambda a:(-round(a[1],1),a[0]))
    circles=[]
    for e in doc.modelspace().query('CIRCLE'):
        if e.dxf.layer not in layers:continue
        c=e.dxf.center
        circles.append({'layer':e.dxf.layer,'source_x':float(c.x),'source_y':float(c.y),
                        'x':float(c.x+dx),'y':float(c.y+dy),'radius':float(e.dxf.radius)})
    joys=sorted([c for c in circles if c['layer']=='0' and abs(c['radius']-12)<1e-6 and abs(c['source_y']-67.844)<.001],key=lambda c:c['x'])
    buttons=[c for c in circles if 'BUTTONS' in c['layer'] or (c['layer']=='0' and abs(c['source_y']-73)<1e-5)]
    assert len(holes)==34 and len(squares)==6 and len(joys)==2 and len(buttons)==18
    return dict(outer=outer,holes=holes,squares=squares,mounts=mounts,circles=circles,
                joys=joys,buttons=buttons,offset=move,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def keepout_solids(data:dict,p:Parameters,z:float,h:float,extra:float=0)->list[cq.Shape]:
    out=[cylinder(c['x'],c['y'],p.button_keepout_diameter/2+extra,z,h) for c in data['buttons']]
    out += [box(c['x'],c['y'],p.joystick_keepout_width+2*extra,p.joystick_keepout_depth+2*extra,z,h) for c in data['joys']]
    return out


def panel_with_holes(data:dict,p:Parameters,alternative_jlf:bool=False)->cq.Shape:
    ow=data['outer']; holes=data['holes']
    if alternative_jlf:
        # Preserve every other hole, replacing ONLY the source 50x73 pattern
        # with the manufacturer's 40x85 pattern (long direction along Y).
        holes=[w for w in holes if not (len(w.Edges())==1 and abs(w.BoundingBox().xlen-4.5)<1e-5)]
        for c in data['joys']:
            for dx,dy in itertools.product((-20,20),(-42.5,42.5)):
                holes.append(cq.Wire.makeCircle(2.25,cq.Vector(c['x']+dx,c['y']+dy,0),cq.Vector(0,0,1)))
    sh=cq.Solid.extrudeLinear(ow,holes,cq.Vector(0,0,p.panel_thickness))
    return sh.translate((0,0,p.height-p.panel_thickness))


def build(p:Parameters,panel_path:Path)->tuple[dict,dict,dict]:
    check_params(p)
    data=load_panel(panel_path,p)
    ow=footprint(p.width,p.depth,p.front_bulge,p.front_corner_radius,p.rear_corner_radius).mirror('XZ')
    inside=offset(ow,-p.wall)
    bottom_recess=offset(ow,-p.bottom_recess_inset)
    bw=offset(ow,-(p.bottom_recess_inset+p.bottom_clearance))
    pw=data['outer'];rw=offset(pw,p.panel_clearance);opening=offset(pw,-p.panel_support_land)
    seat=p.height-p.panel_thickness; deck=p.height-p.deck_thickness
    base=prism(ow,0,p.height)
    ee=[e for e in base.Edges() if abs(e.BoundingBox().zmin-p.height)<1e-5 and abs(e.BoundingBox().zmax-p.height)<1e-5]
    base=base.fillet(p.top_edge_radius,ee)
    ee=[e for e in base.Edges() if abs(e.BoundingBox().zmin)<1e-5 and abs(e.BoundingBox().zmax)<1e-5]
    base=base.fillet(p.bottom_edge_radius,ee)
    log('Outer shell + exact DXF recess')
    shell=base.cut(prism(bottom_recess,-1,p.bottom_thickness+1))
    shell=shell.cut(prism(inside,p.bottom_thickness-EPS,deck-p.bottom_thickness+EPS))
    shell=shell.cut(prism(rw,seat,p.panel_thickness+1))
    shell=shell.cut(prism(opening,-1,p.height+2))
    recesses=[rounded_rect(p.instruction_width,p.instruction_depth,3,p.instruction_x,p.instruction_y,
                         p.height-p.instruction_recess_depth,p.instruction_recess_depth+1),
              rounded_rect(p.label_width,p.label_depth,3,p.label_x,p.label_y,
                         p.height-p.label_recess_depth,p.label_recess_depth+1)]
    for c in recesses:shell=shell.cut(c)
    log('Six panel mounts, bottom mounts, ribs')
    # Each circular local shelf overlaps the deck beyond the panel edge.
    bosses=[cylinder(x,y,p.panel_boss_radius,seat-p.panel_boss_height,p.panel_boss_height) for x,y in data['mounts']]
    # Low bottom bosses: nut pockets are OPEN UPWARDS so bolt load bears on a floor.
    low=[];bridges=[]
    for x,y in BOTTOM_HOLES:
        low.append(cylinder(x,y,p.bottom_boss_radius,p.bottom_thickness,p.bottom_boss_height))
        if y>-30:
            bridges.append(box(x,(y-2)/2,p.bottom_bridge_width,abs(y+2),p.bottom_thickness,deck-p.bottom_thickness))
        elif abs(x)>300:
            wallx=math.copysign(p.width/2-2,x)
            bridges.append(box((x+wallx)/2,y,abs(wallx-x),p.bottom_bridge_width,p.bottom_thickness,deck-p.bottom_thickness))
        else:
            # Extend into the front wall, clipped by the same outside envelope.
            bridges.append(box(x,(y-p.depth)/2,p.bottom_bridge_width,abs(-p.depth-y),p.bottom_thickness,deck-p.bottom_thickness))
    bridges=[b.intersect(base) for b in bridges]
    ribs=[]
    for c in data['joys']:
        for sign in (-1,1):
            ribs.append(box(c['x']+sign*p.rib_side_offset,-132, p.rib_width,155,
                            deck-p.rib_drop,p.rib_drop+1))
    shell=union([shell]+bosses+low+bridges+ribs)
    # Recut recess after fusing support features, so no boss intrudes into the panel.
    shell=shell.cut(prism(rw,seat,p.panel_thickness+1))
    # Full-height keepouts also trim the nominal 5 mm ledge next to close buttons.
    keep=union(keepout_solids(data,p,p.bottom_thickness,seat-p.bottom_thickness,p.keepout_extra_clearance))
    shell=shell.cut(keep)
    # Keepout trimming can isolate short pieces of the optional ribs between
    # adjacent buttons. Discard ONLY pieces proved wholly inside the rib stock.
    ss=sorted(shell.Solids(),key=lambda q:q.Volume(),reverse=True)
    discarded=[]
    if len(ss)>1:
        rib_stock=union(ribs)
        for fragment in ss[1:]:
            if fragment.cut(rib_stock).Volume()>1e-5:
                raise RuntimeError('Disconnected structural feature other than an optional rib')
            discarded.append({'volume_mm3':fragment.Volume(),'centre_mm':list(fragment.Center().toTuple())})
        shell=ss[0]
    data['trimmed_rib_islands']=discarded
    for x,y in data['mounts']:
        shell=shell.cut(cylinder(x,y,p.fastener_hole_diameter/2,seat-p.panel_boss_height-1,p.panel_boss_height+2))
        shell=shell.cut(box(x,y,p.carriage_neck_relief_width,p.carriage_neck_relief_width,
                            seat-p.carriage_neck_relief_depth,p.carriage_neck_relief_depth+EPS))
        shell=shell.cut(hexagon(x,y,p.nut_across_flats,seat-p.panel_boss_height-1,p.nut_pocket_depth+1))
    for x,y in BOTTOM_HOLES:
        shell=shell.cut(cylinder(x,y,p.fastener_hole_diameter/2,p.bottom_thickness-1,p.bottom_boss_height+2))
        shell=shell.cut(hexagon(x,y,p.nut_across_flats,p.bottom_thickness+p.bottom_boss_height-p.nut_pocket_depth,p.nut_pocket_depth+1))
    cable=cq.Solid.makeCylinder(p.cable_exit_diameter/2,p.wall+4,cq.Vector(p.cable_exit_x,2,p.cable_exit_z),cq.Vector(0,-1,0))
    shell=shell.cut(cable).clean()
    bottom=prism(bw,0,p.bottom_thickness)
    if p.pcb_posts_enabled:
        for dx,dy in itertools.product((-p.pcb_hole_pitch_x/2,p.pcb_hole_pitch_x/2),(-p.pcb_hole_pitch_y/2,p.pcb_hole_pitch_y/2)):
            x,y=p.pcb_x+dx,p.pcb_y+dy
            bottom=bottom.fuse(cylinder(x,y,p.pcb_post_radius,p.bottom_thickness,p.pcb_post_height))
            bottom=bottom.cut(cylinder(x,y,p.pcb_hole_diameter/2,-1,p.bottom_thickness+p.pcb_post_height+2))
    for x,y in BOTTOM_HOLES:bottom=bottom.cut(cylinder(x,y,p.fastener_hole_diameter/2,-1,p.bottom_thickness+2))
    bottom=bottom.clean()
    panel=panel_with_holes(data,p)
    panel_alt=panel_with_holes(data,p,True)
    # Lightweight-to-slice visual reference: solid envelope, shallow seam and holes.
    # This auxiliary part is NOT the hollow mechanical shell.
    groove=prism(rw,p.height-p.visual_groove_depth,p.visual_groove_depth+1).cut(prism(pw,p.height-p.visual_groove_depth-1,p.visual_groove_depth+3))
    visual=base.cut(groove)
    for c in recesses:visual=visual.cut(c)
    for w in data['holes']:visual=visual.cut(prism(w,p.height-p.visual_hole_depth,p.visual_hole_depth+1))
    visual=visual.clean()
    parts={'shell':shell,'bottom':bottom,'panel_source_DXF':panel,
           'panel_JLF_40x85_alternative':panel_alt,'visual_solid':visual}
    for n,s in parts.items():
        if len(s.Solids())!=1: print('DEBUG SOLIDS',n,[(q.Volume(),q.Center().toTuple(),bbox(q)) for q in s.Solids()],flush=True)
        assert_solid(n,s)
    # Effective opening is measured at the underside of the seated panel, after all
    # ledge reliefs/local bosses. A thin slab preserves exact circular boundaries.
    # Derive voids from the entire original stock section, not a panel-clipped
    # slab. Clipping to the panel first would make the coverage test tautological.
    stock_slab=prism(ow,seat-.02,.01).intersect(base)
    eff=stock_slab.cut(shell).translate((0,0,-seat+.02)).clean()
    refs={'outer_ESTIMATE':ow,'panel_source_outline_EXACT':pw,'panel_recess_DESIGN':rw,
          'nominal_opening_5mm_DESIGN':opening,'bottom_outline_ESTIMATE':bw,
          'effective_opening_slab':eff,'keepouts':keep,'base':base}
    return parts,refs,data


def orient(sh:cq.Shape,name:str)->cq.Shape:
    if name=='shell':sh=sh.rotate((0,0,0),(1,0,0),180)
    b=sh.BoundingBox();return sh.translate((-b.xmin,-b.ymin,-b.zmin))

def export_mesh(sh:cq.Shape,path:Path,p:Parameters)->trimesh.Trimesh:
    sh.exportStl(str(path),tolerance=p.mesh_tolerance,angularTolerance=p.mesh_angular_tolerance,relative=False)
    m=trimesh.load_mesh(path,process=True)
    m.merge_vertices();m.remove_unreferenced_vertices()
    if not m.is_watertight or not m.is_winding_consistent or m.volume<=0:
        raise RuntimeError(f'{path.name}: bad mesh')
    m.export(path);return m

def stats(sh:cq.Shape,m:trimesh.Trimesh|None=None)->dict:
    r={'valid_brep':bool(sh.isValid()),'solids':len(sh.Solids()),'bbox_mm':bbox(sh),'volume_mm3':sh.Volume()}
    if m is not None:r.update(watertight=bool(m.is_watertight),consistent_winding=bool(m.is_winding_consistent),
                             components=len(m.split(only_watertight=False)),triangles=len(m.faces),mesh_volume_mm3=float(m.volume))
    return r


def poly(w:cq.Wire,spacing:float=.25)->Polygon:
    n=max(64,int(math.ceil(w.Length()/spacing)))
    pts=w.positions(np.linspace(0,1,n,endpoint=False),mode='length')
    return Polygon([(v.x,v.y) for v in pts])


def validate(parts:dict,refs:dict,data:dict,p:Parameters)->dict:
    log('Geometric acceptance checks')
    pw=data['outer'];rw=refs['panel_recess_DESIGN'];seat=p.height-p.panel_thickness
    po=poly(pw,.1);rp=poly(rw,.1)
    pts=pw.positions(np.linspace(0,1,1200,endpoint=False),mode='length')
    distances=[rp.boundary.distance(Point(v.x,v.y)) for v in pts]
    gap=[min(distances),max(distances)]
    opening=refs['effective_opening_slab']
    uncovered=opening.cut(prism(pw,-1,3)).Volume()/.01
    interference={f'{a}__{b}':parts[a].intersect(parts[b]).Volume() for a,b in itertools.combinations(['shell','bottom','panel_source_DXF'],2)}
    keep_z=p.bottom_thickness+EPS;keep_h=seat-p.bottom_thickness-2*EPS
    ko=union(keepout_solids(data,p,keep_z,keep_h))
    kv={n:parts[n].intersect(ko).Volume() for n in ['shell','bottom']}
    support=prism(pw,seat-.02,.01).intersect(parts['shell']).Volume()/.01
    mounts=[]
    for x,y in data['mounts']:
        # Target centre is read from exact square DXF, never from the rounded table.
        probe=cylinder(x,y,p.fastener_hole_diameter/2-.01,seat-p.panel_boss_height+.01,p.panel_boss_height-.02)
        around=cylinder(x,y,4.1,seat-3.0,.05).cut(cylinder(x,y,3.7,seat-3.1,.25))
        mounts.append({'x':x,'y':y,'feedback_y':-y,'centre_error_mm':0.0,
                       'bore_obstruction_mm3':probe.intersect(parts['shell']).Volume(),
                       'support_ring_area_mm2':around.intersect(parts['shell']).Volume()/.05})
    clear=seat-p.bottom_thickness
    # Conservative datum: manufacturer's page 4 bare JLF drawing includes 34 mm;
    # 50 mm installed-depth requirement is our explicit allowance, NOT a catalogue figure.
    hardware={'jlf_bare_dimension_mm':34.0,'jlf_installed_allowance_design_mm':p.joystick_installation_depth_design,
              'obsf30_below_flange_including_terminals_mm':31.7,'obsf24_below_flange_including_terminals_mm':32.0,
              'button_installed_allowance_design_mm':p.button_installation_depth_design,
              'obsf_max_panel_thickness_mm':3.9,
              'jlf_source_pattern_xy_mm':[50,73],'jlf_catalog_rotated_pattern_xy_mm':[40,85],
              'source_JLF_mounting_pattern_matches_catalog':False,
              'alternative_panel_supplied':True,
              'catalogue_url':'https://www.rs2006.co.jp/e/sanwaseimitsu/Sanwa2020.pdf',
              'catalogue_printed_pages':[4,5,13],
              'jlf_connector_and_wiring_fit_requires_physical_check':True}
    if p.panel_thickness>3.9:hardware['snap_in_button_warning']='Selected thickness exceeds manufacturer 3.9 mm maximum'
    checks={
        '01_panel_offset_clearance_0_8_plusminus_0_05': gap[0]>=p.panel_clearance-.05 and gap[1]<=p.panel_clearance+.05,
        '02_panel_outline_covers_effective_opening':abs(uncovered)<1e-5,
        '03_shell_and_bottom_clear_full_height_keepouts':all(abs(v)<1e-5 for v in kv.values()),
        '04_six_mounts_aligned_and_have_support':len(mounts)==6 and all(abs(m['bore_obstruction_mm3'])<1e-5 and m['support_ring_area_mm2']>1 for m in mounts),
        '05_clear_height_exceeds_catalog_body_and_design_allowance':clear>=max(34,p.joystick_installation_depth_design,p.button_installation_depth_design),
        '06_assembly_inside_738_230_envelope':all(s.BoundingBox().xmin>=-p.width/2-1e-5 and s.BoundingBox().xmax<=p.width/2+1e-5 and s.BoundingBox().ymin>=-p.depth-1e-5 and s.BoundingBox().ymax<=1e-5 for s in [parts['shell'],parts['bottom'],parts['panel_source_DXF']]),
        '07_separate_real_panel_and_no_assembly_overlap':all(abs(v)<1e-5 for v in interference.values())}
    r={'acceptance_checks':checks,'geometric_checks_all_pass':all(checks.values()),'clearance_sample_range_mm':gap,
       'clearance_sample_method':'1200 panel boundary points to recess polyline with <=0.1 mm chord sampling',
       'uncovered_opening_area_mm2':uncovered,'panel_support_contact_area_mm2':support,
       'pairwise_interference_mm3':interference,'keepout_intersection_mm3':kv,
       'panel_mounts':mounts,'clear_height_under_controls_mm':clear,
       'remaining_height_after_50mm_design_allowance_mm':clear-max(p.joystick_installation_depth_design,p.button_installation_depth_design),
       'hardware':hardware,'source_sha256':data['source_sha256'],'removed_disconnected_rib_fragments':data['trimmed_rib_islands'],
       'caveats':['Source DXF is authoritative for panel geometry but includes a NONSTANDARD JLF mounting pattern.',
                  'Outer shell height, side profiles, bottom-hole coordinates remain estimates.',
                  'No physical fit, printing, wiring, or structural strength validation performed.',
                  'Conservative keepout regions overlap between some controls; they are not literal component bodies.']}
    if not all(checks.values()):log('WARNING: failed acceptance checks: '+str([k for k,v in checks.items() if not v]))
    return r


def make_fit_tests(parts:dict,refs:dict,data:dict,p:Parameters,out:Path)->dict:
    root=out/'fit_test_1to1';root.mkdir(exist_ok=True)
    z0=p.height-p.fit_ring_height
    outer=offset(refs['panel_recess_DESIGN'],p.fit_ring_outer_margin)
    ring=parts['shell'].intersect(prism(outer,z0,p.fit_ring_height)).translate((0,0,-z0)).clean()
    assert_solid('fit_ring',ring)
    cq.exporters.export(ring,str(root/'panel_fit_ring_1to1.step'))
    export_mesh(orient(ring,'fit_ring'),root/'panel_fit_ring_1to1.stl',p)
    b=ring.BoundingBox();xs=np.linspace(b.xmin,b.xmax,p.fit_tile_count+1)
    records=[]
    for i in range(p.fit_tile_count):
        left,right=float(xs[i]),float(xs[i+1]);center=(left+right)/2
        tile=ring.intersect(box(center,(b.ymin+b.ymax)/2,right-left,b.ylen+2,-1,p.fit_ring_height+2))
        # Interior strips have disjoint front and back rails; thin cross ties connect
        # them below the panel seat. No tab changes the measured panel outline.
        if len(tile.Solids())>1:
            tie=box(center,(b.ymin+b.ymax)/2,p.fit_tie_width,b.ylen,0,p.fit_tie_thickness)
            tie=tie.intersect(prism(outer,0,p.fit_tie_thickness))
            tile=tile.fuse(tie).clean()
        assert_solid(f'fit_tile_{i+1}',tile)
        cq.exporters.export(tile,str(root/f'panel_fit_tile_{i+1:02d}_1to1.step'))
        m=export_mesh(orient(tile,'tile'),root/f'panel_fit_tile_{i+1:02d}_1to1.stl',p)
        records.append({'index':i+1,'x_bounds_case_mm':[left,right],**stats(tile,m)})
    return {'ring_bbox_mm':bbox(ring),'tiles':records,
            'assembly':'Butt-align using x bounds on a flat jig. No precision registration keys. Validate overall length separately.',
            'test_limit':'Measures local panel seating, outline and six holes; not a joystick/wiring clearance or strength test.'}


def reference_exports(parts:dict,refs:dict,data:dict,p:Parameters,out:Path,panel_path:Path)->None:
    root=out/'reference';root.mkdir(exist_ok=True)
    for n in ('outer_ESTIMATE','panel_source_outline_EXACT','panel_recess_DESIGN','nominal_opening_5mm_DESIGN','bottom_outline_ESTIMATE'):
        cq.exporters.export(cq.Workplane('XY').newObject([refs[n]]),str(root/(n+'_1to1.dxf')),'DXF')
    # Export effective opening planar bottom face(s); include all inner loops.
    eff=refs['effective_opening_slab']
    ee=[]
    for f in eff.Faces():
        if abs(f.Center().z)<1e-6 and abs(f.normalAt().z)>.99:ee.extend(f.Wires())
    cq.exporters.export(cq.Workplane('XY').newObject(ee),str(root/'effective_opening_DESIGN_1to1.dxf'),'DXF')
    cq.exporters.export(refs['keepouts'],str(root/'electronics_keepouts_NOT_PRINT_PART.step'))
    with (root/'panel_holes_exact_coordinates_mm.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['feature','diameter_or_square_width','source_panel_x','source_panel_y','CAD_X_right','CAD_Y_away_negative_at_front','feedback_Y_toward_player'])
        for c in data['circles']:w.writerow([c['layer'],c['radius']*2,c['source_x'],c['source_y'],c['x'],c['y'],-c['y']])
        for x,y in data['mounts']:w.writerow(['panel_square',4.6,x-data['offset'][0],y-data['offset'][1],x,y,-y])
    with (root/'bottom_holes_ESTIMATED_mm.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['CAD_X','CAD_Y','status']);w.writerows((x,y,'v1 photo estimate, not measured') for x,y in BOTTOM_HOLES)
    # Alternative DXF in ORIGINAL panel-maker coordinates, not case coordinates.
    d=ezdxf.readfile(str(panel_path));m=d.modelspace()
    for e in list(m):
        if 'JLF_MOUNT_HOLES' in e.dxf.layer:m.delete_entity(e)
    for idx,c in enumerate(data['joys'],1):
        layer=f'P{idx}_JLF_MOUNT_HOLES'
        for dx,dy in itertools.product((-20,20),(-42.5,42.5)):
            m.add_circle((c['source_x']+dx,c['source_y']+dy),2.25,dxfattribs={'layer':layer})
    d.saveas(root/'panel_ALTERNATIVE_JLF_40x85_panel_coordinates.dxf')


def export_all(p:Parameters,panel_path:Path,out:Path,small_width:float)->None:
    if not 0<small_width<p.width:raise ValueError('small width must be between zero and full width')
    for n in ('source','reference','full_size',f'scale_{small_width:g}mm'): (out/n).mkdir(parents=True,exist_ok=True)
    parts,refs,data=build(p,panel_path)
    report=validate(parts,refs,data,p)
    s=small_width/p.width;full=out/'full_size';small=out/f'scale_{small_width:g}mm';tag=f'{small_width:g}mm'
    report.update(units='mm',coordinate_frame='RH: X player-right, Y away from player, rear Y=0; front Y=-230; Z up',
                  source_to_CAD_translation_mm=list(data['offset']),scale=s,scale_percent=s*100,
                  full_envelope_mm=[p.width,p.depth,p.height],small_envelope_mm=[small_width,p.depth*s,p.height*s],parameters=asdict(p),parts={})
    for n,sh in parts.items():
        log('Export '+n)
        cq.exporters.export(sh,str(full/f'HSS0130_v2_{n}_1to1.step'))
        cq.exporters.export(sh.scale(s),str(small/f'HSS0130_v2_{n}_{tag}.step'))
        m=export_mesh(orient(sh,n),full/f'HSS0130_v2_{n}_1to1.stl',p)
        sm=m.copy();sm.apply_scale(s);sm.export(small/f'HSS0130_v2_{n}_{tag}.stl')
        report['parts'][n]={'full':stats(sh,m),'small':stats(sh.scale(s),sm),
                            'uniform_scaling':bool(np.allclose(sm.vertices,m.vertices*s,rtol=0,atol=1e-10)),
                            'orientation':'top deck down' if n=='shell' else 'flat bottom down'}
    for directory,factor,suffix in [(full,1.0,'1to1'),(small,s,tag)]:
        for alternative in (False,True):
            pn='panel_JLF_40x85_alternative' if alternative else 'panel_source_DXF'
            suffix2='_JLF_alternative' if alternative else ''
            a=cq.Assembly(name='HSS0130_v2_EXACT_PANEL_ESTIMATED_SHELL')
            colors={'shell':cq.Color(.84,.84,.8),'bottom':cq.Color(.4,.44,.48),pn:cq.Color(.62,.65,.67)}
            for n in ('shell','bottom',pn):a.add(parts[n].scale(factor),name=n,color=colors[n])
            a.export(str(directory/f'HSS0130_v2_assembly{suffix2}_{suffix}.step'))
    next_y=0;lay=[]
    for n in ('shell','bottom','panel_source_DXF'):
        sh=orient(parts[n],n).scale(s).translate((0,next_y,0));lay.append(sh);next_y=sh.BoundingBox().ymax+8
    cq.exporters.export(cq.Compound.makeCompound(lay),str(small/f'HSS0130_v2_three_parts_layout_{tag}.3mf'),'3MF',
                        tolerance=p.mesh_tolerance*s,angularTolerance=p.mesh_angular_tolerance)
    scene=trimesh.load(small/f'HSS0130_v2_three_parts_layout_{tag}.3mf')
    report['three_part_layout_bbox_mm']=scene.extents.tolist()
    report['three_part_3mf_watertight']=all(m.is_watertight for m in scene.geometry.values())
    reference_exports(parts,refs,data,p,out,panel_path)
    report['fit_tests']=make_fit_tests(parts,refs,data,p,out)
    # Store BREP for reproducible checking/rendering without rerunning booleans.
    cache=out/'reference'/'brep';cache.mkdir(exist_ok=True)
    for n in ('shell','bottom','panel_source_DXF','panel_JLF_40x85_alternative'):parts[n].exportBrep(str(cache/(n+'.brep')))
    (out/'source'/'parameters.json').write_text(json.dumps(asdict(p),indent=2),encoding='utf-8')
    (out/'validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not report['geometric_checks_all_pass']:raise RuntimeError('Geometric acceptance checks failed; see report.')
    log('DONE: exact DXF panel, both scales, fit-test tiles and validation report')


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--panel',type=Path,default=Path(__file__).resolve().parents[1]/'input'/'panel_source_2L16B.dxf')
    ap.add_argument('--params',type=Path)
    ap.add_argument('--small-width',type=float,default=200)
    a=ap.parse_args()
    try:
        p=Parameters(**(json.loads(a.params.read_text()) if a.params else {}))
        export_all(p,a.panel.resolve(),a.out.resolve(),a.small_width)
    except Exception as e:
        import traceback;traceback.print_exc();return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
