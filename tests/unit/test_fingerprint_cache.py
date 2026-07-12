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
