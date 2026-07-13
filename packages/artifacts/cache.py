"""Content-addressed cache (TDD 20).

Keyed by build fingerprint. A cache entry is a *manifest* that maps a
fingerprint digest to the set of output blobs (each stored once, by content
hash). The cache is immutable: blobs are never rewritten, only added.

Materialization prefers hard links, then falls back to copies (reflinks are not
portable to plain stdlib, so we attempt a hard link then copy — TDD 20.5).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.hashing import hash_file


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class CachedOutput:
    logical_name: str
    relative_path: str  # path relative to the job output root
    content_hash: str
    size_bytes: int

    def as_dict(self) -> dict:
        return {
            "logical_name": self.logical_name,
            "relative_path": self.relative_path,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CachedOutput":
        return cls(**d)


@dataclass
class CacheManifest:
    fingerprint: str
    adapter_id: str
    job_id: str
    outputs: list[CachedOutput]
    validation_status: str
    created_at: str

    def as_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "adapter_id": self.adapter_id,
            "job_id": self.job_id,
            "validation_status": self.validation_status,
            "created_at": self.created_at,
            "outputs": [o.as_dict() for o in self.outputs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CacheManifest":
        return cls(
            fingerprint=d["fingerprint"],
            adapter_id=d["adapter_id"],
            job_id=d["job_id"],
            validation_status=d.get("validation_status", "unknown"),
            created_at=d["created_at"],
            outputs=[CachedOutput.from_dict(o) for o in d["outputs"]],
        )


def _fp_key(fingerprint: str) -> str:
    return fingerprint.split(":", 1)[-1]


class ContentCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs = root / "blobs" / "sha256"
        self.manifests = root / "manifests"
        self.logs = root / "logs"
        self.temp = root / "temp"
        for d in (self.blobs, self.manifests, self.logs, self.temp):
            d.mkdir(parents=True, exist_ok=True)

    # ---- lookup ----------------------------------------------------------
    def _manifest_path(self, fingerprint: str) -> Path:
        return self.manifests / f"{_fp_key(fingerprint)}.json"

    def lookup(self, fingerprint: str) -> CacheManifest | None:
        mp = self._manifest_path(fingerprint)
        if not mp.exists():
            return None
        manifest = CacheManifest.from_dict(json.loads(mp.read_text(encoding="utf-8")))
        # Verify every referenced blob still exists (self-healing miss on prune).
        for out in manifest.outputs:
            if not self._blob_path(out.content_hash).exists():
                return None
        return manifest

    def _blob_path(self, content_hash: str) -> Path:
        h = content_hash.split(":", 1)[-1]
        return self.blobs / h[:2] / h

    # ---- publish ---------------------------------------------------------
    def publish(
        self,
        *,
        fingerprint: str,
        adapter_id: str,
        job_id: str,
        output_root: Path,
        output_files: list[Path],
        validation_status: str,
    ) -> CacheManifest:
        """Store outputs as blobs and write a manifest (TDD 20.4)."""
        cached: list[CachedOutput] = []
        for f in output_files:
            content_hash = hash_file(f)
            blob = self._blob_path(content_hash)
            if not blob.exists():
                blob.parent.mkdir(parents=True, exist_ok=True)
                # Copy into cache immutably. The temp name MUST be unique per
                # writer: parallel jobs that produce byte-identical outputs (e.g.
                # deterministic Deli candidates) hash to the SAME blob, and a
                # shared "<hash>.part" name makes them clobber each other's temp
                # and fail the rename on Windows (WinError 32). Blobs are
                # content-addressed and immutable, so if another worker publishes
                # the same blob first, our copy is redundant — discard it.
                tmp = self.temp / f"{blob.name}.{os.getpid()}.{uuid.uuid4().hex}.part"
                shutil.copy2(f, tmp)
                published = False
                for attempt in range(5):
                    if blob.exists():  # another worker won the race
                        break
                    try:
                        os.replace(tmp, blob)  # atomic; replaces if dest exists
                        published = True
                        break
                    except OSError:
                        # Transient lock (a concurrent replace of the same blob
                        # on Windows). Back off briefly and retry.
                        time.sleep(0.05 * (attempt + 1))
                if not published:
                    tmp.unlink(missing_ok=True)
            rel = f.relative_to(output_root).as_posix()
            cached.append(
                CachedOutput(
                    logical_name=rel,
                    relative_path=rel,
                    content_hash=content_hash,
                    size_bytes=blob.stat().st_size,
                )
            )
        manifest = CacheManifest(
            fingerprint=fingerprint,
            adapter_id=adapter_id,
            job_id=job_id,
            outputs=sorted(cached, key=lambda o: o.relative_path),
            validation_status=validation_status,
            created_at=_now(),
        )
        self._manifest_path(fingerprint).write_text(
            pretty_dumps(manifest.as_dict()), encoding="utf-8"
        )
        return manifest

    # ---- materialize -----------------------------------------------------
    def materialize(self, manifest: CacheManifest, dest_root: Path) -> list[Path]:
        """Realize cached outputs into ``dest_root`` (hard link, else copy)."""
        dest_root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for out in manifest.outputs:
            src = self._blob_path(out.content_hash)
            dst = dest_root / out.relative_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst.unlink()
            try:
                os.link(src, dst)  # hard link when possible
            except OSError:
                shutil.copy2(src, dst)  # fallback copy
            written.append(dst)
        return written

    # ---- maintenance -----------------------------------------------------
    def inspect(self) -> dict:
        manifests = list(self.manifests.glob("*.json"))
        blobs = [p for p in self.blobs.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in blobs)
        return {
            "manifest_count": len(manifests),
            "blob_count": len(blobs),
            "total_bytes": total,
        }

    def prune(self) -> dict:
        """Remove blobs not referenced by any manifest."""
        referenced: set[str] = set()
        for mp in self.manifests.glob("*.json"):
            manifest = CacheManifest.from_dict(json.loads(mp.read_text(encoding="utf-8")))
            for out in manifest.outputs:
                referenced.add(out.content_hash.split(":", 1)[-1])
        removed = 0
        freed = 0
        for blob in list(self.blobs.rglob("*")):
            if blob.is_file() and blob.name not in referenced:
                freed += blob.stat().st_size
                blob.unlink()
                removed += 1
        return {"removed_blobs": removed, "freed_bytes": freed}
