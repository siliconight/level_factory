"""The light bake's marks reach each model before its import (0.187.0, reshaped by 0.189.0).

0.187.0 wrote the bake's marks into the sidecars before the export's second import pass, so the
bake no longer imported every model a third time. 0.189.0 imports every model once, its final
settings on it from its first import -- the marks are `_write_import_sidecars`' model defaults and
whole sidecars now -- and `tests/unit/test_models_import_once.py` holds what the tests here that
counted passes held: every model's import carries its light baking, a spawned one Dynamic, and
the bake's own marking then finds nothing to change. What stays here is the wiring.
"""
import ast
from pathlib import Path


def test_the_export_passes_the_bakes_spawned_models_when_it_bakes():
    """The wiring, read off the source: `export_mission` hands the sidecar step the list the
    bake is handed, and only when it bakes. A keyword nobody passes is a check that cannot fire."""
    from packages.exporting import export
    tree = ast.parse(Path(export.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "export_mission")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_write_import_sidecars"]
    assert len(calls) == 1
    kw = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
    assert kw.get("bake_spawned") == (
        "responder_vehicle_scenes(themed_site_dir) if profile.bake_lights else None"), kw
