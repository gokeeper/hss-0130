"""Render the actual exported BREP geometry. No generated/reference-photo imagery."""
from pathlib import Path
import json
import cadquery as cq
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
PRE=ROOT/'preview';PRE.mkdir(exist_ok=True)
parts={n:cq.Shape.importBrep(str(ROOT/'reference'/'brep'/(n+'.brep'))) for n in ['shell','bottom','panel_source_DXF']}
colors={'shell':(.86,.865,.84),'bottom':(.42,.46,.49),'panel_source_DXF':(.47,.55,.60)}

def polydata(sh):
    vv,ff=sh.tessellate(.12,.12)
    v=np.asarray([p.toTuple() for p in vv]);f=np.asarray(ff,dtype=np.int64)
    pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(v,deep=True))
    ca=vtk.vtkCellArray();aa=np.hstack([np.full((len(f),1),3,dtype=np.int64),f]).ravel()
    ca.SetCells(len(f),numpy_to_vtkIdTypeArray(aa,deep=True))
    pd=vtk.vtkPolyData();pd.SetPoints(pts);pd.SetPolys(ca)
    cl=vtk.vtkCleanPolyData();cl.SetInputData(pd);cl.Update();return cl.GetOutput()

def render(name,shapes,camera,focus,up=(0,0,1),scale=220,size=(1800,670),edges=True):
    ren=vtk.vtkRenderer();ren.SetBackground(.967,.976,.983)
    for label,sh in shapes:
        pd=polydata(sh)
        normal=vtk.vtkPolyDataNormals();normal.SetInputData(pd);normal.SetFeatureAngle(45);normal.ConsistencyOn();normal.Update()
        mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(normal.GetOutputPort());mapper.ScalarVisibilityOff()
        ac=vtk.vtkActor();ac.SetMapper(mapper);p=ac.GetProperty();p.SetColor(*colors.get(label,colors['shell']));p.SetAmbient(.30);p.SetDiffuse(.7);p.SetSpecular(.16);p.SetSpecularPower(26)
        ren.AddActor(ac)
        if edges:
            edge=vtk.vtkFeatureEdges();edge.SetInputData(pd);edge.BoundaryEdgesOn();edge.FeatureEdgesOn();edge.SetFeatureAngle(35);edge.ManifoldEdgesOff();edge.NonManifoldEdgesOff();edge.Update()
            em=vtk.vtkPolyDataMapper();em.SetInputConnection(edge.GetOutputPort());em.ScalarVisibilityOff()
            ea=vtk.vtkActor();ea.SetMapper(em);ea.GetProperty().SetColor(.19,.24,.27);ea.GetProperty().SetLineWidth(.65);ea.GetProperty().LightingOff();ren.AddActor(ea)
    cam=ren.GetActiveCamera();cam.SetPosition(*camera);cam.SetFocalPoint(*focus);cam.SetViewUp(*up);cam.ParallelProjectionOn();cam.SetParallelScale(scale)
    ren.ResetCameraClippingRange()
    win=vtk.vtkRenderWindow();win.SetOffScreenRendering(1);win.AddRenderer(ren);win.SetSize(*size);win.SetMultiSamples(4);win.Render()
    cap=vtk.vtkWindowToImageFilter();cap.SetInput(win);cap.SetInputBufferTypeToRGB();cap.ReadFrontBufferOff();cap.Update()
    writer=vtk.vtkPNGWriter();writer.SetFileName(str(PRE/name));writer.SetInputConnection(cap.GetOutputPort());writer.Write();win.Finalize()

render('assembly_actual.png',list(parts.items()),(380,-900,620),(0,-110,32),scale=174)
render('shell_inside_actual.png',[('shell',parts['shell'])],(230,-720,-620),(0,-110,38),up=(0,0,-1),scale=190)
render('top_actual.png',list(parts.items()),(0,-115,1000),(0,-115,0),up=(0,1,0),scale=155,size=(1800,740))
render('exploded_actual.png',[
 ('bottom',parts['bottom'].translate((0,0,-25))),
 ('shell',parts['shell']),('panel_source_DXF',parts['panel_source_DXF'].translate((0,0,38)))],
 (380,-900,620),(0,-110,34),scale=207,size=(1800,760))
font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
def ft(s):return ImageFont.truetype(font,s)
canvas=Image.new('RGB',(1800,1590),'#f7fafc');d=ImageDraw.Draw(canvas)
d.text((54,25),'HSS-0130  /  CAD v2',font=ft(40),fill='#243440')
d.text((55,82),'面板依据上传 DXF 重建 · 外壳曲面与高度仍为估算',font=ft(25),fill='#465766')
canvas.paste(Image.open(PRE/'assembly_actual.png'),(0,125))
d.text((54,720),'原尺寸 738 × 230 × 70 mm    |    面板 632 × 129 × 2 mm',font=ft(26),fill='#243440')
canvas.paste(Image.open(PRE/'shell_inside_actual.png'),(0,810))
d.text((54,1500),'底部视角：六个面板承托点、底板螺母座、局部加强筋及按钮避让',font=ft(25),fill='#465766')
d.text((54,1544),'预览来自实际实体模型；不含摇杆、按钮和电子元件。',font=ft(20),fill='#637786')
canvas.save(PRE/'HSS0130_CAD_v2_preview.png')
print('renders complete')
