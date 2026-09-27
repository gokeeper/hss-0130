"""V1 outer-envelope construction retained unchanged; not measured shell surfaces."""
import math
import cadquery as cq

def footprint(w: float, d: float, bulge: float, rf: float, rb: float) -> cq.Wire:
    """有直后边、前部浅圆弧和相切前角的闭合平面线框。

    bulge 为浅圆弧在 x=±(w/2-rf) 处相对中部的退距。
    前圆角与浅圆弧作解析相切，避免折线逼近和接缝尖角。
    """
    if not (w > 4*rf > 0 and 0 < rb < d/3 and 0 < bulge < d/3):
        raise ValueError('轮廓参数不合理。')
    a = w/2-rf
    big_r = (a*a + bulge*bulge)/(2*bulge)
    big_cy = d-big_r
    dist = big_r-rf
    if dist <= a:
        raise ValueError('前圆角与前弧无法构造内切关系。')
    side_cy = big_cy + math.sqrt(dist*dist-a*a)
    if side_cy <= rb:
        raise ValueError('侧边长度不足。')
    px = big_r*a/dist
    py = big_cy + big_r*(side_cy-big_cy)/dist
    theta = math.atan2(py-side_cy, px-a)
    right_mid = (a+rf*math.cos(theta/2), side_cy+rf*math.sin(theta/2))
    left_mid = (-right_mid[0], right_mid[1])
    q = math.sqrt(0.5)
    result = (cq.Workplane('XY')
        .moveTo(-w/2+rb, 0).lineTo(w/2-rb, 0)
        .threePointArc((w/2-rb+rb*q, rb-rb*q), (w/2, rb))
        .lineTo(w/2, side_cy)
        .threePointArc(right_mid, (px, py))
        .threePointArc((0, d), (-px, py))
        .threePointArc(left_mid, (-w/2, side_cy))
        .lineTo(-w/2, rb)
        .threePointArc((-w/2+rb-rb*q, rb-rb*q), (-w/2+rb, 0))
        .close().val())
    if not isinstance(result, cq.Wire) or not result.isValid():
        raise RuntimeError('生成轮廓失败。')
    return result

def offset(wire: cq.Wire, amount: float) -> cq.Wire:
    result = wire.offset2D(amount, 'arc')
    if len(result) != 1 or not result[0].isValid():
        raise RuntimeError(f'轮廓偏移失败，距离={amount}。')
    return result[0]

def prism(wire: cq.Wire, z: float, height: float) -> cq.Solid:
    w = wire.translate((0, 0, z))
    return cq.Solid.extrudeLinear(w, [], cq.Vector(0, 0, height))

def rounded_rect(width: float, depth: float, radius: float,
                 x: float, y: float, z: float, height: float) -> cq.Shape:
    return (cq.Workplane('XY').center(x,y).rect(width,depth).extrude(height)
            .edges('|Z').fillet(radius).val().translate((0,0,z)))

