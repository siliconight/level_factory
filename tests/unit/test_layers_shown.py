"""The output layers, shown: the light apart from the art (0.213.0, the factory's roadmap 257).

Light has been a layer of its own since 0.35.0 and `export --mode art-unlit` since 0.36.0, and every package
recorded it in `LF_MANIFEST.json` and `output_layers.json`. What a reader met first did not say so: the README's
Output layers section, the package's own label (spelled from `("art", "gameplay")` here and from the whole set in
the planner), HANDOFF.md and the export's log. These pin each.
"""
from __future__ import annotations

from pathlib import Path

from packages.exporting import export as EX
from packages.pipeline.planner import LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT, label_for_layers

ROOT = Path(EX.__file__).resolve().parents[2]


def test_the_label_has_one_spelling_the_planners():
    full = {LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT}
    rec = EX.output_layers_record(full)
    assert rec["label"] == label_for_layers(full) == "graybox+art+light+gameplay"
    assert rec["layers"] == sorted(full)
    assert rec["schema"] == "level_factory.output_layers.v0.1"
    assert EX.output_layers_record({LAYER_ART, LAYER_GAMEPLAY})["label"] == "graybox+art+gameplay"
    assert EX.output_layers_record(())["label"] == "graybox"


def test_the_handoff_says_what_the_package_carries_and_keeps_the_light_apart():
    lit = EX.handoff_layers_text({LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT}, EX.MODE_PORTABLE)
    for words in ("the ART layer", "the LIGHT layer", "the GAMEPLAY layer", "APART FROM THE ART",
                  "art-unlit", "LuxEmit", "output_layers.json"):
        assert words in lit, words
    unlit = EX.handoff_layers_text({LAYER_ART, LAYER_GAMEPLAY}, EX.MODE_ART_UNLIT)
    assert "the LIGHT layer" not in unlit
    assert "exported `art-unlit`" in unlit and "no Lux result" in unlit
    bare = EX.handoff_layers_text((), EX.MODE_PORTABLE)
    assert "carries no light layer" in bare and "the ART layer" not in bare
    # the export's log line reads the record's strings, so the layer's name is pinned
    assert LAYER_LIGHT == "light"


def test_the_export_writes_the_record_and_the_paragraph():
    src = Path(EX.__file__).read_text(encoding="utf-8")
    assert "record = output_layers_record(layers)" in src
    assert "HANDOFF_LANGUAGE + handoff_layers_text(layers, profile.mode)" in src
    assert '"label": "+".join(parts)' not in src


def test_the_readme_and_the_design_doc_show_the_light_layer():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "three independent, optional layers" in readme
    section = readme.split("## Output layers", 1)[1]
    for words in ("**Light**", "--unlit", "art-unlit", "LuxEmit"):
        assert words in section, words
    doc = (ROOT / "docs" / "RENDER_PASS_SPLIT.md").read_text(encoding="utf-8")
    assert "BUILT in 0.35.0 and 0.36.0" in doc
