# syntax=docker/dockerfile:1
# web/ service — Next.js (App Router) UI + BFF (docs/design.md §6).
# Multi-stage build producing Next's standalone server for a lean runtime image.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Optional npm registry mirror (e.g. a LAN package cache), passed as the BuildKit secret
# npm_registry (compose `build.secrets`): unset/empty (the default) means the public registry. A
# secret rather than a build arg because arg values are part of the layer cache key; secret
# contents aren't, so builds with and without the mirror share cached layers. npm rewrites the lockfile's
# registry.npmjs.org `resolved` URLs to the configured registry (replace-registry-host=npmjs).
# The cache mount keeps npm's tarball cache in the builder (never in the image), so a lockfile
# change only downloads the packages that actually changed (not used under `--no-cache`).
RUN --mount=type=cache,target=/root/.npm \
    --mount=type=secret,id=npm_registry,env=NPM_REGISTRY,required=false \
    npm ci --prefer-offline --no-audit --no-fund ${NPM_REGISTRY:+--registry="$NPM_REGISTRY"}

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# Next's incremental build cache (webpack/SWC artifacts) on a cache mount: a rebuild after a small
# source change reuses it instead of compiling from scratch. Only .next/standalone + .next/static
# are copied into the runner, so nothing from the mount reaches the image. The id is scoped to
# this project so other Next apps on the same builder don't share (and thrash) one cache.
RUN --mount=type=cache,target=/app/.next/cache,id=newsroom-web-next-cache \
    npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

ARG BUILD_COMMIT=unknown
RUN mkdir -p public/.well-known && \
    printf '{"component":"web","commit":"%s","shortCommit":"%s","builtAt":"%s"}\n' \
      "$BUILD_COMMIT" \
      "$(echo "$BUILD_COMMIT" | cut -c1-7)" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > public/.well-known/newsroom-build.json

# Non-root runtime user.
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# The standalone server (CMD below) never invokes npm — drop it (and its bundled,
# vulnerable node-tar, /usr/local/lib/node_modules/npm/node_modules/tar) to clear
# CVE-2026-59873 and shrink the runtime attack surface. corepack/yarn ride along
# for the same reason: neither is used at runtime either.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-v*

# Standalone server + static assets + public files.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Bake build metadata (overwrites any source copy). Uses build-arg BUILD_COMMIT passed at `docker build`.
ARG BUILD_COMMIT=unknown
RUN mkdir -p public/.well-known && \
    printf '{"component":"web","commit":"%s","shortCommit":"%s","builtAt":"%s"}\n' \
      "$BUILD_COMMIT" \
      "$(echo "$BUILD_COMMIT" | cut -c1-7)" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > public/.well-known/newsroom-build.json && \
    chown -R nextjs:nodejs public/.well-known

USER nextjs
EXPOSE 3000

# The container always listens on the fixed internal port 3000; the host-side port is
# parameterized in docker-compose.yml for parallel isolated instances.
CMD ["node", "server.js"]
