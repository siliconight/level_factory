"""The greybox census reads the bake's import cache (0.181.0, factory roadmap 239).

Profiled on cold run 9248's export (430.7 s): the cache was dropped straight after the light bake,
and the census three steps later imported the whole package again to read it -- 100.4 s, the fifth
import of the same files in one export. The cache now stays until the census has run and goes
before the closure verdict and the manifest walk the tree, which is what keeps the shipped package
cache-free. Order is the whole fix, so order is what this pins: the drop must not reappear between
the bake and the census, and must still come before the verdict.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EXPORT = ROOT / "packages" / "exporting" / "export.py"


def _export_mission_body():
    text = EXPORT.read_text(encoding="utf-8")
    start = text.index("def export_mission(")
    end = text.find("\ndef ", start + 1)
    return text[start:end if end != -1 else len(text)]


def _calls(body, needle):
    """Every offset of `needle` in the body's code lines (comments skipped)."""
    out, offset = [], 0
    for line in body.splitlines(keepends=True):
        code = line.split("#", 1)[0]
        i = code.find(needle)
        if i != -1:
            out.append(offset + i)
        offset += len(line)
    return out


def test_the_cache_is_dropped_once_after_the_census_and_before_the_verdict():
    """The export drops the cache in three places, and two are not this: the occluder bake's
    and the Empties merge's failures clean up before they raise. The one the package ships
    through is the drop that says so."""
    body = _export_mission_body()
    drops = _calls(body, "if drop_cache(export_dir):")
    census = _calls(body, "greybox_skin.measure(")
    verdict = _calls(body, "_closure_verdict(export_dir)")
    assert len(drops) == 1, "one drop on the way to shipping, found %d" % len(drops)
    assert census and verdict, "the census and the verdict are where this test looks"
    assert census[0] < drops[0] < verdict[0], (census, drops, verdict)


def test_nothing_drops_the_cache_between_the_bake_and_the_census():
    body = _export_mission_body()
    bake = _calls(body, "_bake_lights(")
    census = _calls(body, "greybox_skin.measure(")
    assert bake and census
    between = body[bake[0]:census[0]]
    assert not _calls(between, "drop_cache("), "a drop before the census costs a whole import"
    assert not _calls(between, "rmtree("), "and so does removing the cache any other way"
