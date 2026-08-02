"""The dressing build must resolve the same Pixelcoat library the kit does.

THE DEFECT. Zoo's material factory resolves a Pixelcoat pack per material kind
(`skins.find_pack(dir, kind, theme)` -> `<kind>_<theme>/` before bare
`<kind>/`). With no library set, `make_material` falls back to a flat colour
and says nothing. The kit job passed `skins_dir`; the DRESSING job did not, and
the adapter's dress branch never forwarded `--theme` even when it was in the
spec. So on `category5_baie_dore_001` the walls carried a real
`concrete_polished_casino` pack while the 2255 cover meshes sitting ON those
walls shipped as one material, `M_Cover_concrete`, baseColorFactor
0.50/0.49/0.46, zero images.

`--skins` and `--theme` are ONE input here, not two: a themed library resolves
only under its own theme, so passing the directory without the theme finds no
pack and degrades to exactly the same flat colour. Both assertions below exist
because either one alone leaves the defect in place.

Pixelcoat's README draws the line this restores: it "owns the themed skin
library that Zoo kits resolve against. It does not decide geometry or
placement." Patina places; Pixelcoat skins.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402


def _argv(job_spec, tmp_path):
    cmds = ZooAdapter().plan_commands(
        job_spec, {"repository": str(tmp_path), "work_dir": str(tmp_path)})
    return [a for c in cmds for a in c.argv()]


def _dress_spec(tmp_path, **over):
    man = tmp_path / "shell.patina.dressing.json"
    man.write_text("{}", encoding="utf-8")
    spec = {"mode": "dress", "manifest_path": str(man), "seed": 5421,
            "theme": "polished_casino", "skins_dir": str(tmp_path / "skins")}
    spec.update(over)
    return spec


def test_dress_forwards_the_skin_library(tmp_path):
    argv = _argv(_dress_spec(tmp_path), tmp_path)
    assert "--skins" in argv, argv


def test_dress_forwards_the_theme_the_library_is_keyed_by(tmp_path):
    """Without this the library is present and every lookup still misses."""
    argv = _argv(_dress_spec(tmp_path), tmp_path)
    assert "--theme" in argv, argv
    assert argv[argv.index("--theme") + 1] == "polished_casino"


def test_dress_forwards_the_seed(tmp_path):
    """Cover wear/variation is seeded; an unseeded dressing is not reproducible."""
    argv = _argv(_dress_spec(tmp_path), tmp_path)
    assert "--seed" in argv
    assert argv[argv.index("--seed") + 1] == "5421"


def test_dress_without_a_library_still_plans(tmp_path):
    """A mission with no Pixelcoat stage must not crash -- it degrades to flat."""
    argv = _argv(_dress_spec(tmp_path, skins_dir="", theme=""), tmp_path)
    assert "--skins" not in argv and "--theme" not in argv
    assert "--dress" in argv


def test_kit_and_dress_agree_on_the_library(tmp_path):
    """Same library, same theme -- a cover is the same concrete as its wall.

    The two branches are separate code paths that must not drift: this asserts
    they emit the same (--skins, --theme) pair from the same spec fields.
    """
    slots = tmp_path / "shell.slots.json"
    slots.write_text("{}", encoding="utf-8")
    kit = _argv({"mode": "kit", "slots_path": str(slots), "seed": 5421,
                 "theme": "polished_casino",
                 "skins_dir": str(tmp_path / "skins")}, tmp_path)
    dress = _argv(_dress_spec(tmp_path), tmp_path)

    def pair(argv):
        return (argv[argv.index("--skins") + 1], argv[argv.index("--theme") + 1])

    assert pair(kit) == pair(dress)
