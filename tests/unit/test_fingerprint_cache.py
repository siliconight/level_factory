"""Unit tests: build fingerprint + content-addressed cache (TDD 20, 21)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.artifacts.cache import ContentCache
from packages.artifacts.provenance import BuildFingerprint


def _fp(**over):
    base = dict(
        adapter_id="deli_counter", adapter_version="0.1.0", tool_version="0.74.0",
        repository_commit="abc", executable_versions={}, normalized_arguments=["build"],
        input_hashes={"inputs_digest": "sha256:aaa"}, upstream_artifact_hashes=[],
        declared_environment={}, seed=1997, schema_versions={"adapter": "0.1.0"},
        output_contract_version="deli.gameplay.1.21.0",
    )
    base.update(over)
    return BuildFingerprint(**base)


def test_fingerprint_deterministic_and_sensitive():
    assert _fp().digest() == _fp().digest()
    assert _fp(seed=1).digest() != _fp(seed=2).digest()
    assert _fp(input_hashes={"inputs_digest": "sha256:bbb"}).digest() != _fp().digest()
    # Upstream ordering must not matter.
    a = _fp(upstream_artifact_hashes=["x", "y"]).digest()
    b = _fp(upstream_artifact_hashes=["y", "x"]).digest()
    assert a == b


def test_cache_publish_lookup_materialize(tmp_path):
    cache = ContentCache(tmp_path / "cache")
    out_root = tmp_path / "out"
    out_root.mkdir()
    (out_root / "shell.glb").write_bytes(b"glb")
    (out_root / "shell.gameplay.json").write_text('{"schema":"1.21.0"}')

    fp = _fp().digest()
    assert cache.lookup(fp) is None
    manifest = cache.publish(
        fingerprint=fp, adapter_id="deli_counter", job_id="j1",
        output_root=out_root, output_files=[out_root / "shell.glb",
                                            out_root / "shell.gameplay.json"],
        validation_status="PASS",
    )
    assert len(manifest.outputs) == 2

    hit = cache.lookup(fp)
    assert hit is not None

    dest = tmp_path / "dest"
    written = cache.materialize(hit, dest)
    assert (dest / "shell.glb").read_bytes() == b"glb"
    assert len(written) == 2


def test_cache_prune_removes_unreferenced(tmp_path):
    cache = ContentCache(tmp_path / "cache")
    out = tmp_path / "o"; out.mkdir()
    (out / "a.txt").write_text("a")
    cache.publish(fingerprint=_fp().digest(), adapter_id="x", job_id="j",
                  output_root=out, output_files=[out / "a.txt"], validation_status="PASS")
    # Orphan a blob.
    (cache.blobs / "zz").mkdir(parents=True, exist_ok=True)
    (cache.blobs / "zz" / "zzorphan").write_text("orphan")
    result = cache.prune()
    assert result["removed_blobs"] >= 1


# ---------------------------------------------------------------------------
# the evaluator is an input too
# ---------------------------------------------------------------------------
def _lt_job(tmp_path):
    """A laser_tag job spec pointing at a miniature addon tree."""
    addon = tmp_path / "laser_tag_tool"
    (addon / "scripts" / "metrics").mkdir(parents=True)
    (addon / "plugin.cfg").write_text("[plugin]\nname=\"laser_tag_tool\"\n")
    (addon / "scripts" / "metrics" / "LT_MetricsCollector.gd").write_text(
        "func summary():\n\treturn {}\n")
    scene = tmp_path / "level.tscn"
    scene.write_text("[gd_scene format=3]\n")
    return {"seed": 5320, "run_count": 25, "enemy_count": 6,
            "evaluation_scene": str(scene), "addon_dir": str(addon)}, addon


def test_editing_the_laser_tag_addon_invalidates_the_cache(tmp_path):
    """The defect this closes. Laser Tag publishes no VERSION -- the factory
    manifest pins it "unpinned", "reports UNKNOWN by design" -- so `probe()`
    contributes no tool_version or repository_commit, and every other input
    described the MAP. A fingerprint meant to answer "would this job produce
    the same output?" could not see the tool producing it: the addon was
    patched, the run reported success, and the previous grade was served back
    with nothing on disk saying the report predated the change."""
    from adapters.laser_tag import LaserTagAdapter

    spec, addon = _lt_job(tmp_path)
    adapter = LaserTagAdapter()
    before = adapter.fingerprint_inputs(spec, {})

    collector = addon / "scripts" / "metrics" / "LT_MetricsCollector.gd"
    collector.write_text(collector.read_text() + '\t# publish the enemy opening\n')
    after = adapter.fingerprint_inputs(spec, {})

    assert before != after, "editing the evaluator must change its fingerprint"
    assert before["scene_hash"] == after["scene_hash"], "the map did not change"


def test_addon_hashes_are_keyed_by_relative_path_not_bare_filename(tmp_path):
    """Same-named files at different depths must not mask one another — a flat
    filename key would let a change in one silently inherit the other's hash."""
    from adapters.laser_tag import LaserTagAdapter

    spec, addon = _lt_job(tmp_path)
    (addon / "scripts" / "core").mkdir(parents=True)
    (addon / "scripts" / "core" / "LT_MetricsCollector.gd").write_text("# different\n")
    fp = LaserTagAdapter().fingerprint_inputs(spec, {})
    keys = set(fp["addon_hashes"])
    assert "laser_tag_tool/scripts/core/LT_MetricsCollector.gd" in keys
    assert "laser_tag_tool/scripts/metrics/LT_MetricsCollector.gd" in keys
    assert len({fp["addon_hashes"][k] for k in keys if k.endswith(
        "LT_MetricsCollector.gd")}) == 2


def test_editor_and_generated_artifacts_do_not_churn_the_fingerprint(tmp_path):
    """`.godot/` caches, `.uid` sidecars and generated reports are artifacts of
    running the tool, not of its behaviour. Folding them in would invalidate
    every cached grade whenever Godot re-imported, which is a cache that never
    hits rather than a cache that is correct."""
    from adapters.laser_tag import LaserTagAdapter

    spec, addon = _lt_job(tmp_path)
    before = LaserTagAdapter().fingerprint_inputs(spec, {})

    (addon / ".godot").mkdir()
    (addon / ".godot" / "global_script_class_cache.cfg").write_text("list=[]\n")
    (addon / "scripts" / "metrics" / "LT_MetricsCollector.gd.uid").write_text("uid://x")
    assert LaserTagAdapter().fingerprint_inputs(spec, {}) == before


def test_a_missing_addon_dir_does_not_crash_the_fingerprint(tmp_path):
    """Pre-flight owns "there is no addon here". Fingerprinting must degrade to
    silence rather than raising, or a misconfigured path fails as a stack trace
    instead of as the validation message written for it."""
    from adapters.laser_tag import LaserTagAdapter

    spec, _ = _lt_job(tmp_path)
    spec["addon_dir"] = str(tmp_path / "nope")
    fp = LaserTagAdapter().fingerprint_inputs(spec, {})
    assert "addon_hashes" not in fp
