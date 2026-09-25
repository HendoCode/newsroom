# Moved: the brain now lives in its own repo

The agent brain (voice packs, personas, engine docs, partners, piece drafts — everything that used
to live in this directory) has moved to its own repo:

**[`HendoCode/content-machine-brain`](https://github.com/HendoCode/content-machine-brain)**

`agents/` now consumes it as a read-write git clone rather than a subdirectory of this repo — see
`BRAIN_ROOT` / `BRAIN_REPO_URL` / `BRAIN_DEPLOY_KEY` in `agents/app/config.py` and
`agents/.env.example`. For local dev, clone the brain repo as a sibling of this one:

```bash
cd ..
git clone git@github.com:HendoCode/content-machine-brain.git
```

The default `BRAIN_ROOT` (`../content-machine-brain`) already expects that layout. See
`docs/local-dev.md` and this repo's `AGENTS.md` ("agents/ Git brain / content store") for the full
picture, and `GET /api/brain/status` for which commit of the brain a running `agents/` instance has
checked out.

This directory is kept only as a pointer; it holds no brain content.
