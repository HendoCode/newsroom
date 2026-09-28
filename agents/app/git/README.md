# Brain pin (build/test) vs. the live clone (runtime)

`agents/` consumes the agent brain as a **clone** of its own repo,
[`HendoCode/masthead`](https://github.com/HendoCode/masthead) — see this
repo's `AGENTS.md` ("agents/ Git brain as a clone, not a subdirectory") for the full split. This
doc covers a narrower, downstream concern: **which commit of that brain do we build and test
against**, and how that differs from what the running app tracks.

## Two modes, one function

Everything routes through `ensure_brain_available` (`app/git/__init__.py`), called from
`main.py`'s lifespan on every boot. It has exactly two modes, selected by whether `BRAIN_REF` is
set:

| | `BRAIN_REF` unset (**runtime**) | `BRAIN_REF` set (**build/test**) |
|---|---|---|
| First boot, no clone on disk | `git clone` the repo, left on the default branch | `git clone` + detach HEAD onto `BRAIN_REF` |
| Clone already on disk | `git pull --ff-only` (fast-forward to the branch tip) | fetch `BRAIN_REF` + detach HEAD onto it, **every time** |
| What it tracks | the live branch — a human/agent's hand-nurtured edits land here, and `GitRepo.commit()` pushes back to it | one exact, pinned commit — moving the live branch never moves this |
| Who uses it | `docker compose up`, any real dev/prod boot (`BRAIN_REF` is never set in `docker-compose.yml`) | anything constructing/testing against a **known-good** brain (see below) |

The mechanism is `GitRepo.checkout_ref`/`GitRepo.clone(..., ref=...)` (`app/git/repo.py`): fetch the
ref, detach HEAD onto it. Detached HEAD is deliberate — a build/test clone is disposable and
read-only; it never pushes back (unlike the runtime clone's `GitRepo.commit()` auto-push).

**Nothing defaults `BRAIN_REF` to the pin inside `ensure_brain_available` or `Settings` itself.**
Leaving it unset must always mean "runtime, track the live branch" — the pin only takes effect
when something *sets the env var*, on purpose, for a build/test invocation.

## The pin: `agents/brain.lock`

```json
{
  "repo": "https://github.com/HendoCode/masthead.git",
  "ref": "<40-char commit SHA>",
  "note": "..."
}
```

This is the lockfile: the exact Masthead commit that `agents/` is known to build
and test correctly against — the same discipline as a `package-lock.json`/`poetry.lock`, just for
a brain that lives in its own repo instead of a package registry. `ref` is a full commit SHA (not
a branch), so the pin never silently drifts.

Nothing reads `brain.lock` automatically at runtime or import time. It exists for **humans and
build/test tooling** to read and turn into a `BRAIN_REF` env var — e.g.:

```bash
BRAIN_REF=$(python3 -c "import json; print(json.load(open('agents/brain.lock'))['ref'])")
BRAIN_REPO_URL=$(python3 -c "import json; print(json.load(open('agents/brain.lock'))['repo'])")
```

`scripts/regenerate-brain-fixture.sh` (below) is the one piece of tooling in this repo that
already does this for you.

## The test fixture is a snapshot of the pin

`agents/tests/fixtures/brain/` is a frozen snapshot of Masthead at
`brain.lock`'s pinned `ref` — not an arbitrary capture. The regeneration helper also writes
`.fixture-source.json` into that directory, recording the `repo`/`ref` it used so
`tests/test_brain_fixture.py` can catch a lockfile bump without a matching fixture refresh
**offline**. `tests/conftest.py`'s `brain_repo` fixture copies it into a throwaway git repo per
test, so the Git suite (`tests/test_git.py`, `tests/test_brain_pin.py`, …) runs green with no clone
of the real brain, while still exercising the true on-disk layout at a known-good commit.

Regenerate it from the pin with:

```bash
scripts/regenerate-brain-fixture.sh          # clones brain.lock's pinned ref, replaces the fixture
```

(Pass an explicit ref, e.g. `scripts/regenerate-brain-fixture.sh <sha>`, to preview a fixture for a
ref you're considering bumping the pin to — review the resulting diff before touching `brain.lock`
itself.) Requires network + read access to the private brain repo (ambient SSH/HTTPS credentials,
same as any other clone of it).

## Bump workflow (like `npm update` + committing the lockfile)

1. Pick the newer Masthead commit/tag you want to move to.
2. Regenerate the fixture against it and look at the diff:
   ```bash
   scripts/regenerate-brain-fixture.sh <new-sha>
   git diff --stat -- agents/tests/fixtures/brain
   ```
3. Run the suite against that fixture:
   ```bash
   cd agents && pytest
   ```
4. If green, bump the pin — edit `agents/brain.lock`'s `ref` to `<new-sha>` — and commit the lock
   file bump together with the regenerated fixture, in one reviewed commit. If it's red, the new
   brain commit broke something `agents/` depends on; fix forward on the brain side (or in
   `agents/`) before bumping, exactly like a failing `npm update`/`poetry update` blocks a lockfile
   bump.
5. The running app is unaffected — it never reads `brain.lock` or `BRAIN_REF`. It keeps tracking
   whatever the live branch is, independently of this bump, per the split above.

## Testing the pin mechanism itself

`agents/tests/test_brain_pin.py` proves `GitRepo.checkout_ref`/`clone(ref=...)` and
`ensure_brain_available`'s `BRAIN_REF` branch against a local bare repo (no network) — including
that an *existing* on-disk clone gets re-pinned (not fast-forward-pulled) when `BRAIN_REF` is set,
and that leaving it unset reproduces the pre-pin runtime behavior exactly.
