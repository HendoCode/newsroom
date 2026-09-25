# syntax=docker/dockerfile:1
# agents/ service — Python FastAPI + uvicorn (docs/design.md §6).
# Pinned to -bookworm (Debian 12), not the floating python:3.12-slim tag: that tag has since moved
# to Debian 13 "trixie", which the pinned Playwright release below (1.49.0) doesn't recognize —
# its `install --with-deps` OS detection falls back to an unrelated package list and fails
# (missing ttf-unifont/ttf-ubuntu-font-family). Bookworm is a release Playwright officially
# supports; bump this pin deliberately together with the Playwright version, not independently.
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# git + openssh-client: app/git/repo.py shells out to git for the brain/content stores (lessons,
# interview engine, draft/finalize revisions) — without git the lifespan's open_brain() call
# raises FileNotFoundError and the service never becomes healthy. openssh-client provides the
# `ssh` binary GIT_SSH_COMMAND invokes when a BRAIN_DEPLOY_KEY is configured (app/git/ssh_auth.py).
#
# `apt-get upgrade` pulls Debian's latest security-patched versions of every base-image package at
# build time (P0 security hardening, cmw-security-p0): the pinned base digest freezes packages at
# whenever it was cut, so a rebuild without this ships known-fixed OS CVEs unnecessarily. It cannot
# clear Debian "no fix available" CVEs (those need a base-OS bump, blocked here by the Playwright /
# bookworm pin above) — only everything that already has a patched version.
RUN apt-get update && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Playwright's own Chromium download, plus its OS-level dependencies (--with-deps), for the
# finalize PDF format (app/render/pdf.py's ChromiumPdfRenderer). Without this the import there
# guards cleanly (HTML/Doc formats still work) but PDF raises PdfRenderError on every render.
RUN playwright install --with-deps chromium

# App source.
COPY pyproject.toml ./
COPY app ./app

# Bake build metadata (static file read by the minimal /build route). Uses build-arg BUILD_COMMIT.
ARG BUILD_COMMIT=unknown
RUN printf '{"component":"agents","commit":"%s","shortCommit":"%s","builtAt":"%s"}\n' \
      "$BUILD_COMMIT" \
      "$(echo "$BUILD_COMMIT" | cut -c1-7)" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > /app/cmw-build.json

EXPOSE 8000

# The container always listens on the fixed internal port 8000; the host-side port is
# parameterized in docker-compose.yml for parallel isolated instances.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
