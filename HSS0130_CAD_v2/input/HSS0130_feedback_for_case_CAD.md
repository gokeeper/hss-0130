# Feedback on HSS0130_CAD_v1: fitting a real 2L16B control panel

**For:** the model/author that generated `HSS0130_CAD_v1` (`source/build_hss0130.py`, `parameters.json`).
**From:** the user, who is building a 2-player Sega-style control panel and wants to use your case.
**Units:** mm throughout.

Please update the case so it fits the actual panel below. The outer shell (738 × 230 from Sega's data) can stay as it is. What needs to change is the centre panel area, which your README describes as a visual placeholder ("面板凹槽 … 仅为视觉占位").

Files that come with this feedback:
- `Sega Layout 2L16B - FrancoB + Sega P1-P2.dxf`: the panel, 1:1 mm, `$INSUNITS = 4`. Its outline is on layer `0`.
- `HSS0130 case vs 2L16B panel.png`: an overlay of your current recess and opening against this panel.

---

## 1. The problem: the panel falls through the case

I overlaid the panel on your `reference/*_ESTIMATE.dxf` outlines, centred in the recess:

| | Width | Depth | Front shape |
|---|---:|---:|---|
| Your `panel_recess` | 650.0 | 150.0 | Arc bulge 15, front corners R22, rear R6 |
| Your `panel_blank` (recess offset −0.8) | 648.4 | 148.4 | same |
| Your `panel_opening` (recess offset −8 ledge) | **634.0** | **134.0** | same |
| **Real panel** | **632.0** | **129.0** | Straight centre with angled sides, front R30, rear R5 |

- **The panel is smaller than your through-opening in both directions.** It drops straight through, and there is no ledge for it to rest on. About 2,296 mm² of the opening is left uncovered.
- **Even in the recess it would rattle.** The gaps are 9 mm on each side, 8 mm at the rear and 13 mm at the front centre, and larger at the front corners.
- **The front shapes don't match.** Your recess front is one continuous arc. The panel front is a straight centre section with two straight angled sides.

## 2. The real panel outline (please use this exactly)

These are in the **panel's own coordinates**, as in the DXF: origin at the front-left, +x to the player's right, and +y **away from the player** (y = 0 is the player-side edge).

| Element | Geometry |
|---|---|
| Rear edge | Line (5, 129) → (627, 129) |
| Rear corners | R5 arcs, centres (5, 124) and (627, 124) |
| Left / right sides | Lines x = 0 and x = 632, from y = 124 down to y = 41.17 |
| Front corners | R30 arcs, centres (30, 41.17) and (602, 41.17). Left arc 180° → 264.33°, right arc 275.67° → 360° |
| Angled front edges | Lines (27.04, 11.32) → (141, 0) and (491, 0) → (604.96, 11.32) |
| Straight front centre | Line (141, 0) → (491, 0) |

The overall size is 632 × 129. Please import the outline from the DXF (layer `0`) rather than approximating it with your `footprint()` arc construction.

**Converting to your case coordinates** (X = 0 on the centreline, Y = 0 at the rear, +Y toward the player). This assumes the panel rear edge sits 0.8 mm in front of your current recess rear, at Y = 65.8:

```
X_case = x_panel − 316
Y_case = 65.8 + (129 − y_panel)
```

The X values in this document are **as seen from the player, looking down**: P1 is on the left (−X). Your README says your X axis is mirrored relative to that view ("从玩家方向俯视时左右相反"). Everything here is left/right symmetric except the button clusters, so please mirror them if you keep your convention. Better still, switch the CAD to player-view top-down, so that a DXF from the panel maker drops straight in.

## 3. What needs to change

### 3.1 Recess and opening (required)
- **Recess** = the real panel outline offset **+0.8** (your existing `clearance_per_side`), which is about 633.6 × 130.6.
- **Through-opening** = the real panel outline offset **inward** by a support ledge. The ledge width is limited by what hangs under the panel (see 3.4):
  - Three 30 mm button holes come within **7.2–7.7 mm** of the panel edge. Their snap-in bodies and switches hang below the panel and must not hit the ledge.
    - P2 rear buttons at (207.5, 88.0) and (243.5, 88.0)
    - P1 button at (−146.4, 88.5)
  - A uniform 8 mm ledge therefore collides. Use about 5 mm as the general ledge, and add local tabs or bosses only at the mounting points in 3.2.
  - Or use a variable-width ledge, and check it against the hole list in section 4.
- Make `panel_recess_depth` equal to a **`panel_thickness` parameter set by the user** (the panel may be steel, aluminium, acrylic or plywood), so the panel ends up flush with the top deck. Don't hard-code 5 mm recess / 4.5 mm panel.

### 3.2 Panel mounting points (required)
Your README lists "原装面板六个安装点" (the original panel's six mounting points) as not restored. The real panel has them: six **4.6 × 4.6 mm square cutouts**, which look like square-neck carriage-bolt holes.

| # | Case X | Case Y | Distance from panel edge |
|---|---:|---:|---:|
| 1 | −310.0 | 71.8 | 3.2 |
| 2 | 0.0 | 71.8 | 3.7 |
| 3 | 310.0 | 71.8 | 3.2 |
| 4 | −310.0 | 156.8 | 3.1 |
| 5 | 310.0 | 156.8 | 3.1 |
| 6 | 0.0 | 188.5 | 4.0 (front centre) |

At each of these points, add a boss or local ledge under the panel with a through-hole or nut trap. It needs to extend at least about 8 mm in from the panel edge so a bolt and nut or washer fits. Please leave the fastener size as a parameter (e.g. M4 default). The user hasn't confirmed the original bolt size.

### 3.3 Vertical space under the panel (please check and report)
With the current parameters (height 70, recess 5, bottom plate 4.5) the panel underside sits at Z = 65 and the bottom plate top at about Z = 4.5, leaving roughly **60 mm** of clear height. That space has to hold:
- **2 × Sanwa JLF joysticks.** The mounting plate bolts to the underside of the panel; the lever body, microswitch PCB and 5-pin harness hang below it.
- **16 × 30 mm snap-in buttons plus 2 × 24 mm start buttons**, with microswitches and quick-disconnect wiring.
- **An encoder/PCB and cables.**

Please take the depth figures from Sanwa datasheets, not estimates. If about 60 mm is too little, change `height` or the recess, report which, and keep the change parametric. Please also leave room under each joystick, with no internal ribs in its way.

### 3.4 Keep-out zones inside the shell (required)
No ribs, bosses or bottom-plate standoffs are allowed under any of these areas, which extend down the full interior height:
- **Each JLF:** a rectangle of about 60 × 95 mm (X × Y) centred on the stick. That is the plate footprint plus margin; the plate runs **front to back** on this panel. Please confirm against the JLF datasheet.
- **Each button:** a Ø 40 mm circle centred on the hole, to leave room for the switch and wiring.

Centres in section 4.

### 3.5 Things a working controller needs (recommended)
- **Bosses or screws joining the shell and bottom plate.** Your README says there are none and that the model can't take real stick forces. This will be a real, used joystick, so it needs them, plus ribs near the joysticks.
- **A cable or USB exit** in the rear wall, and a mounting spot for an encoder PCB, e.g. a 4-post pattern as a parameter.
- **A 1:1 panel-fit test print**: a single thin plate of the recess and opening outline with the 6 mounting points, so the fit can be checked before printing the full shell.

## 4. Hole list in case coordinates (player view, P1 = −X)

The joystick bore is Ø24, start buttons Ø24, action buttons Ø30 and JLF holes Ø4.5.

| Item | Ø | Case X | Case Y |
|---|---:|---:|---:|
| P1 joystick | 24 | −245.4 | 127.0 |
| P2 joystick | 24 | 114.0 | 127.0 |
| Start 1 / Start 2 | 24 | −17.0 / 17.0 | 121.8 |
| P1 JLF holes | 4.5 | −270.4 / −220.4 | 90.5 / 163.5 |
| P2 JLF holes | 4.5 | 89.0 / 139.0 | 90.5 / 163.5 |
| P1 buttons | 30 | (−186.4, 141.0) (−179.4, 102.5) (−153.4, 127.0) (−146.4, 88.5) (−117.4, 133.0) (−110.9, 94.5) (−83.4, 148.0) (−76.9, 109.5) | |
| P2 buttons | 30 | (177.0, 108.0) (177.0, 147.0) (207.5, 88.0) (207.5, 127.0) (243.5, 88.0) (243.5, 127.0) (279.0, 97.0) (279.0, 136.0) | |

The P1 joystick is not centred on its side of the panel. Its position follows a real Sega panel scan.

## 5. Acceptance checks to add to `validation_report.json`

1. The panel outline from the DXF fits the recess with 0.8 ± 0.05 clearance all round.
2. The panel fully covers the through-opening, with no uncovered area.
3. The ledge and bosses don't intersect any keep-out zone from 3.4.
4. All 6 mounting bosses sit directly under the 6 square cutouts.
5. The clear height under the panel is reported and is at least the JLF depth from its datasheet.
6. The whole case, panel included, still fits inside the 738 × 230 envelope.
7. The assembly STEP includes the real panel outline, with its holes, as a separate solid, so an interference check can run against the shell.

## 6. Keep as is

- The 738 × 230 outer envelope and the clear separation of sourced dimensions from estimated ones in the README. That labelling is exactly right, so please keep it up to date.
- The parametric CadQuery source and the matching 1:1 and scaled outputs.
