"""Merge the JasensCustoms Sega P1/P2 layouts onto the FrancoB 2L0B panel.

Each layout DXF has its origin at the joystick center, +X toward the buttons,
+Y toward the back, in mm, the same frame as the panel. So each one is copied
across with a plain translation onto that player's joystick circle.

FrancoB's joystick holes are first moved to where DrGuild's 2L16B file puts
them (traced from a real Sega panel scan), which gives the P1 buttons more
room from the start buttons.
"""
import math
import sys
from pathlib import Path

import ezdxf
from ezdxf.math import Matrix44

HERE = Path(__file__).resolve().parent.parent
LAYOUTS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "FightStickLayoutProject" / "dxf"
SRC = HERE / "Sega Layout 2L0B - FrancoB.dxf"
OUT = HERE / "Sega Layout 2L16B - FrancoB + Sega P1-P2.dxf"

# (layout file, FrancoB joystick center, DrGuild joystick center, layer prefix)
PLAYERS = [
    ("sega1_s.dxf", (96.0, 65.0), (70.588, 67.844), "P1"),  # Astro City / Blast City P1, 59 mm lever
    ("sega2_s.dxf", (440.0, 65.0), (429.977, 67.844), "P2"),  # Sega P2 non slanted, 63 mm lever
]
# Layer name in the layout file -> (suffix on the panel, ACI color, plot?)
# The panel already has 24 mm joystick holes, so the layout's own bores are skipped.
# Of the universal plate pattern only the four Sanwa JLF corner holes are kept,
# turned 90 degrees so the plate runs front to back as on a real Sega panel.
LAYER_MAP = {
    "BUTTONS": ("BUTTONS_30", 1, True),
    "GL_PLATE_HOLES": ("JLF_MOUNT_HOLES", 2, True),
    "REFERENCE": ("REFERENCE", 8, False),
}



def is_jlf_corner(e):
    """The 4.5 mm holes at (+-36.5, +-25) from the lever center."""
    if e.dxftype() != "CIRCLE":
        return False
    c = e.dxf.center
    return abs(abs(c.x) - 36.5) < 1e-6 and abs(abs(c.y) - 25.0) < 1e-6 and abs(e.dxf.radius - 2.25) < 1e-6


doc = ezdxf.readfile(SRC)
msp = doc.modelspace()

for name, (ox, oy), (cx, cy), prefix in PLAYERS:
    src = ezdxf.readfile(LAYOUTS / name).modelspace()
    joy = [e for e in msp.query("CIRCLE") if abs(e.dxf.center.x - ox) < 1e-6 and abs(e.dxf.center.y - oy) < 1e-6]
    assert joy and abs(joy[0].dxf.radius - 12.0) < 1e-6, f"no 24 mm joystick hole at {ox},{oy}"
    joy[0].dxf.center = (cx, cy, 0)
    move = Matrix44.translate(cx, cy, 0)
    for e in src:
        if e.dxf.layer not in LAYER_MAP:
            continue
        if e.dxf.layer == "GL_PLATE_HOLES" and not is_jlf_corner(e):
            continue
        suffix, color, plot = LAYER_MAP[e.dxf.layer]
        layer = f"{prefix}_{suffix}"
        if layer not in doc.layers:
            doc.layers.add(layer, color=color).dxf.plot = int(plot)
        c = e.copy()
        c.dxf.layer = layer
        c.dxf.color = 256  # BYLAYER
        c.transform(Matrix44.z_rotate(math.pi / 2) @ move if suffix == "JLF_MOUNT_HOLES" else move)
        msp.add_entity(c)

doc.saveas(OUT)
print("wrote", OUT)
