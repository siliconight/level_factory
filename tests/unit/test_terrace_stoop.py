"""An Empty's stoop stands in the terrace's frontage (Level Factory 0.195.0, factory roadmap 240).

Deli Counter 0.211.0 stands every rowhome Empty three steps up, its stoop's colliders 1.74 m in front of
its front face. The terrace reads a house's extent off its collider hulls (`street_line.shell_extents`)
and stands its street edge on the line, `FRONTAGE` behind the sidewalk's back edge -- so, read whole,
the stoop's foot would stand on the line and the house 1.74 m behind it, the row and the plate set back
for nothing. The strip IS where a Philadelphia stoop stands: the house's own extent leaves its stoop
out (`STOOP_COLLIDERS`), the front face stands on the line as it did, and `stoop_reach` holds the stoop
inside the strip.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_fixture import write_glb  # noqa: E402

from packages.pipeline import empties, site_variation, street_line  # noqa: E402

#: a rowhome shell as Deli Counter builds it, in glTF metres (x, height, z; site y = -z): walls from z
#: -6.15 to 6.15, the front face toward +z (the street, site -y), 6 m wide
WALLS = [("ext_col_0_S_seg0-convcolonly", (0.0, 1.55, 6.0), (6.0, 3.1, 0.3)),
         ("ext_col_0_N_seg0-convcolonly", (0.0, 1.55, -6.0), (6.0, 3.1, 0.3)),
         ("ext_col_0_E_seg0-convcolonly", (3.0, 1.55, 0.0), (0.3, 3.1, 12.3)),
         ("ext_col_0_W_seg0-convcolonly", (-3.0, 1.55, 0.0), (0.3, 3.1, 12.3))]
#: Deli Counter 0.211.0's stoop in front of a door at x -1.5: the landing 0.9 m deep, the block under
#: the upper tread, the ramp's hull to its foot 1.738 m out (axis-aligned here, as the reader's hulls are)
STOOP = [("stoop_landing_col-convcolonly", (-1.5, 0.2417, 6.6), (1.5, 0.5834, 0.9)),
         ("stoop_under_1_col-convcolonly", (-1.5, 0.0639, 7.1897), (1.5, 0.2278, 0.2794)),
         ("stoop_ramp-convcolonly", (-1.5, 0.2, 7.469), (1.5, 0.6, 0.838))]
#: the twin's stoop, a volume (`presets.twin`): named `stoop_right`, it is the BUILDING's, as a porch is
TWIN_STOOP = [("stoop_right_col-convcolonly", (2.0, 0.1, 7.35), (1.8, 0.2, 1.2))]
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}


def test_the_house_s_extent_leaves_its_stoop_out(tmp_path):
    plain = street_line.shell_extents(write_glb(tmp_path / "plain.glb", WALLS))
    stooped = tmp_path / "stooped.glb"
    write_glb(stooped, WALLS + STOOP)
    whole = street_line.shell_extents(stooped)
    house = street_line.shell_extents(stooped, skip=street_line.STOOP_COLLIDERS)
    assert abs(plain[2] + 6.15) < 1e-9
    # read whole, the stoop's foot is the street edge; the house's own extent is its walls'
    assert abs(whole[2] + 7.888) < 1e-9
    assert house == plain


def test_a_stoop_s_reach_is_its_depth_in_front_of_the_house(tmp_path):
    stooped = write_glb(tmp_path / "stooped.glb", WALLS + STOOP)
    reach = empties.stoop_reach(street_line.shell_extents(stooped),
                                street_line.shell_extents(stooped, skip=street_line.STOOP_COLLIDERS))
    assert abs(reach - 1.738) < 1e-9
    # inside the strip it stands in
    assert reach <= empties.FRONTAGE
    plain = write_glb(tmp_path / "plain.glb", WALLS)
    assert empties.stoop_reach(street_line.shell_extents(plain),
                               street_line.shell_extents(plain, skip=street_line.STOOP_COLLIDERS)) == 0.0
    assert empties.stoop_reach(None, (0.0, 1.0, -1.0, 1.0)) is None


def test_only_the_empty_s_stoop_is_left_out(tmp_path):
    # a twin's stoop is a volume of its own lot, read as the building's (the street line keeps a
    # porch or a canopy off the walk); the skip names Deli Counter 0.211.0's three colliders only
    twin = write_glb(tmp_path / "twin.glb", WALLS + TWIN_STOOP)
    whole = street_line.shell_extents(twin)
    assert street_line.shell_extents(twin, skip=street_line.STOOP_COLLIDERS) == whole
    assert abs(whole[2] + 7.95) < 1e-9


def test_the_terrace_stands_the_front_face_on_the_line(tmp_path):
    stooped = write_glb(tmp_path / "stooped.glb", WALLS + STOOP)
    house = street_line.shell_extents(stooped, skip=street_line.STOOP_COLLIDERS)
    whole = street_line.shell_extents(stooped)
    rows = [{"id": "gs_empty_rowhome_a"}]
    placed, _need = empties.terrace(rows, {"gs_empty_rowhome_a": house}, site_variation.stream(9080),
                                    [THROUGH], 60.0)
    assert placed
    # the far sidewalk's back edge is y -35.65; the front face 2.0 m behind it, as with no stoop
    assert {p["front"] for p in placed} == {-37.65}
    # and the stoop, turned with the house, ends inside the strip: never on the walk
    reach = empties.stoop_reach(whole, house)
    assert all(p["front"] + reach < -35.65 for p in placed)
    # read whole, the stoop's foot would have stood on the line and the house 1.738 m behind it
    placed_whole, _ = empties.terrace(rows, {"gs_empty_rowhome_a": whole}, site_variation.stream(9080),
                                      [THROUGH], 60.0)
    assert {p["front"] for p in placed_whole} == {-37.65}
    assert all(abs((a["at"][1] - b["at"][1]) - 1.738) < 1e-6 for a, b in zip(placed, placed_whole))
