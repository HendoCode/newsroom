"""Offline guards for the checked-in brain fixture snapshot.

The fixture under ``agents/tests/fixtures/brain`` is intentionally not a live clone, so the normal
suite cannot ask Git which upstream commit it represents. The regeneration helper stamps that
source metadata into the fixture; these tests make a lockfile bump without a matching regeneration
fail locally, without touching the network.
"""

from __future__ import annotations

import json
from pathlib import Path

AGENTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_BRAIN = Path(__file__).resolve().parent / "fixtures" / "brain"


def _read_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_brain_fixture_source_matches_lockfile() -> None:
    lock = _read_json(AGENTS_ROOT / "brain.lock")
    source = _read_json(FIXTURE_BRAIN / ".fixture-source.json")

    assert source["repo"] == lock["repo"]
    assert source["ref"] == lock["ref"]


def test_brain_fixture_draft_prompt_states_editorial_contract() -> None:
    prompt = (FIXTURE_BRAIN / "engine" / "2-draft.md").read_text(encoding="utf-8")

    assert 'class="editorial"' in prompt
    assert "literal bytes of" in prompt
    assert "Write ONLY draft.html's contents" in prompt
    assert "no markdown code fences" in prompt
