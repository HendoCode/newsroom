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
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# BUILD SPEED. Layers run cheapest-to-invalidate last: OS packages, then Playwright + its Chromium
# download (its own pin file, so other dependency bumps don't re-download ~260 MB), then the rest
# of requirements.txt, then app source. Every download-heavy step also uses a BuildKit cache mount
# (apt archives/lists, pip's wheel cache, Playwright's browser download). Cache mounts live in the
# builder, never in the image, so a step that re-runs reuses what it already fetched. NOTE:
# `--no-cache` bypasses cache mounts too; for a fast forced rebuild, invalidate layers another way
# (e.g. change a build arg the early apt step reads) so the mounts are kept. The optional *_MIRROR / PIP_INDEX_URL build args (compose
# `build.args`, empty by default) route the downloads that do happen through LAN caches.

# git + openssh-client: app/git/repo.py shells out to git for the brain/content stores (lessons,
# interview engine, draft/finalize revisions) — without git the lifespan's open_brain() call
# raises FileNotFoundError and the service never becomes healthy. openssh-client provides the
# `ssh` binary GIT_SSH_COMMAND invokes when a BRAIN_DEPLOY_KEY is configured (app/git/ssh_auth.py).
#
# `apt-get upgrade` pulls Debian's latest security-patched versions of every base-image package at
# build time (P0 security hardening, cmw-security-p0): the pinned base digest freezes packages at
# whenever it was cut, so a rebuild without this ships known-fixed OS CVEs unnecessarily. It cannot
# clear Debian "no fix available" CVEs (those need a base-OS bump, blocked here by the Playwright /
# bookworm pin above) — only everything that already has a patched version. The apt cache mounts
# don't weaken this: `apt-get update` still refreshes the lists every build; only already-downloaded
# .debs are reused.
#
# Optional Debian mirror (e.g. a LAN apt cache): a base URL that replaces `http://deb.debian.org` in
# the image's deb822 sources (so it must serve /debian and /debian-security beneath it). The image's
# `docker-clean` apt hook (which deletes downloaded .debs, defeating the cache mount) and, when a
# mirror is set, its original sources are set aside here and restored after the last apt use (the
# Playwright step below), so the shipped image is apt-wise identical to an unmirrored build.
ARG APT_MIRROR=
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    mv /etc/apt/apt.conf.d/docker-clean /tmp/docker-clean.orig \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/zz-build-keep-debs \
    && if [ -n "$APT_MIRROR" ]; then \
      cp /etc/apt/sources.list.d/debian.sources /tmp/debian.sources.orig \
      && sed -i "s|http://deb.debian.org|${APT_MIRROR%/}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends git openssh-client

# Optional PyPI mirror (e.g. a LAN package cache). Unset/empty (the default) means public PyPI.
ARG PIP_INDEX_URL=

# Playwright's own Chromium download, plus its OS-level dependencies (install-deps), for the
# finalize PDF format (app/render/pdf.py's ChromiumPdfRenderer). Without this the import there
# guards cleanly (HTML/Doc formats still work) but PDF raises PdfRenderError on every render.
# The browser downloads into a per-Playwright-version directory on a cache mount, then is copied
# to the default runtime path (/root/.cache/ms-playwright; the service runs as root), so a rebuild
# reuses the download and a version bump never drags old browser builds into the image.
# PLAYWRIGHT_DOWNLOAD_MIRROR, when set, becomes PLAYWRIGHT_DOWNLOAD_HOST (a mirror of Playwright's
# browser CDN). install-deps runs apt-get, so it also goes through APT_MIRROR.
ARG PLAYWRIGHT_DOWNLOAD_MIRROR=
COPY requirements-playwright.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} -r requirements-playwright.txt
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,target=/root/.cache/playwright-downloads \
    playwright install-deps chromium \
    && dl="/root/.cache/playwright-downloads/$(playwright --version | awk '{print $2}')" \
    && env ${PLAYWRIGHT_DOWNLOAD_MIRROR:+PLAYWRIGHT_DOWNLOAD_HOST="$PLAYWRIGHT_DOWNLOAD_MIRROR"} \
      PLAYWRIGHT_BROWSERS_PATH="$dl" playwright install chromium \
    && mkdir -p /root/.cache/ms-playwright \
    && cp -a "$dl"/. /root/.cache/ms-playwright/ \
    && rm -rf /root/.cache/ms-playwright/.links \
    && rm -f /etc/apt/apt.conf.d/zz-build-keep-debs \
    && mv /tmp/docker-clean.orig /etc/apt/apt.conf.d/docker-clean \
    && if [ -f /tmp/debian.sources.orig ]; then \
      mv /tmp/debian.sources.orig /etc/apt/sources.list.d/debian.sources; \
    fi

# The rest of the Python deps (requirements.txt includes requirements-playwright.txt, already
# installed above).
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} -r requirements.txt

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
