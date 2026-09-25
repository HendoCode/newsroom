"""Structural final-vs-published diff (cmw-context-assembly report §9(c)/(d)2).

The lessons call should reason about *what changed*, not re-derive it from two whole documents —
"the pre-computed diff, not two full documents... cheaper and sharper" (context report §9-d-2). We
compute that diff with ``git`` itself rather than a naive line-diff, since it is the well-tested
tool already trusted for every other revision in this codebase (D2/D4).

Neither side needs to be a real Git revision for this: ``git diff --no-index`` works over two
arbitrary blobs, so the human's published/edited text (which never becomes a Piece Revision — it
was edited outside the machine, e.g. after posting) can be diffed directly against the machine's
last committed revision without polluting the piece's Git history.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class DiffError(RuntimeError):
    """``git diff --no-index`` failed for a reason other than "differences found"."""


def compute_diff(
    final_text: str,
    published_text: str,
    *,
    final_label: str = "final-machine-draft",
    published_label: str = "published-human-version",
) -> str:
    """Unified diff of ``final_text`` (machine, post-council, pre-human) → ``published_text``
    (the author's actually-published/edited version). Returns ``""`` when the two are identical —
    a signal callers use to skip the lessons call entirely (no meaningful change, no lesson to
    learn).
    """
    with tempfile.TemporaryDirectory() as tmp:
        final_path = Path(tmp) / final_label
        published_path = Path(tmp) / published_label
        final_path.write_text(final_text, encoding="utf-8")
        published_path.write_text(published_text, encoding="utf-8")
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--", str(final_path), str(published_path)],
            capture_output=True,
            text=True,
            check=False,  # --no-index exits 1 when differences are found — not a failure
        )
        if proc.returncode not in (0, 1):
            raise DiffError(
                f"git diff --no-index failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc.stdout
