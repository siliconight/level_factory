"""Unit tests: canonical JSON, hashing, ids, state machines (TDD 37.1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.core import states
from packages.core.canonical import canonical_dumps
from packages.core.hashing import hash_json, hash_text, short
from packages.core.ids import candidate_id, job_id, namespaced_anchor, slugify


def test_canonical_is_order_independent():
    assert canonical_dumps({"b": 1, "a": 2}) == canonical_dumps({"a": 2, "b": 1})


def test_hash_json_stable_across_key_order():
    assert hash_json({"x": 1, "y": [2, 3]}) == hash_json({"y": [2, 3], "x": 1})


def test_hash_text_and_short():
    h = hash_text("delco")
    assert h.startswith("sha256:")
    assert len(short(h)) == 12


def test_ids():
    assert candidate_id("m1", 1997) == "m1.candidate.seed_1997"
    assert job_id("m1", "deli_generate") == "m1.deli_generate"
    assert namespaced_anchor("m1", "vault") == "m1/vault"
    assert namespaced_anchor("m1", "m1/vault") == "m1/vault"
    assert slugify("Bank Block 99!") == "bank_block_99"


def test_mission_rank_and_progression():
    assert states.mission_rank(states.DRAFT) == 0
    assert states.mission_rank(states.INVALIDATED) == -1
    assert states.is_at_least(states.FUNCTIONAL_SHELL_LOCKED, states.CANDIDATE_SELECTED)
    assert not states.is_at_least(states.DRAFT, states.HANDOFF_READY)
    assert states.next_mission_state(states.DRAFT) == states.BRIEF_APPROVED


def test_job_transitions():
    assert states.job_can_transition(states.PLANNED, states.QUEUED)
    assert states.job_can_transition(states.RUNNING, states.SUCCEEDED)
    assert not states.job_can_transition(states.SUCCEEDED, states.RUNNING)
    assert states.job_succeeded(states.SKIPPED_CACHE_HIT)
