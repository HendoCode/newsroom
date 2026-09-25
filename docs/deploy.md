# Production deployment: edge reverse proxy

A build deployed on a public IP can run behind a lightweight Caddy reverse proxy that sits in
front of `web`, on top of (not instead of) the app's own [email-identity login](auth.md). There
is no additional gate in front of that proxy — the app's own sign-in is the access control
(previously there was a shared basic-auth password ahead of it too; that was removed 2026-08-08
since the app's own sign-in already gates every route — see `middleware.ts` and `auth.md`).

This lives entirely in a **compose overlay** — [`docker-compose.prod.yml`](../docker-compose.prod.yml)
— layered on top of the base [`docker-compose.yml`](../docker-compose.yml) with two explicit `-f`
flags (below). **Local dev is unaffected:** that explicit `-f docker-compose.yml -f
docker-compose.prod.yml` invocation never picks up `docker-compose.override.yml` (Compose only
auto-loads an override file with no `-f` at all), so local dev's own HTTPS edge
(`docker-compose.override.yml`) plays no part here — this overlay's `edge` is a distinct,
unrelated Caddy service.

## Topology

```
                    ┌─── docker-compose.prod.yml overlay ───┐
browser ──────────────▶ edge (Caddy, :80/EDGE_PORT) ──▶ web (Next.js) ──▶ agents ──▶ mongo
```

`web` is **not** directly published when the prod overlay is used — only `edge` is. `web`'s
own sign-in (identity-declaration today, real Google Workspace SSO later — [`auth.md`](auth.md))
is completely unchanged; the proxy is just a pass-through in front of it, not a second gate.

## Running the gated stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

`EDGE_PORT` (default `80`) is the one public port; override it if `80` is already in use on
the host. `WEB_PORT` has no effect under this overlay (`web` isn't published at all).

Tear down:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
```

## Validating the proxy

```bash
# Passes through to web (which then applies its own sign-in, e.g. redirecting to /signin):
curl -i http://<host>:${EDGE_PORT:-80}/
```

Config sanity check (no stack needs to be running):

```bash
docker run --rm -v "$(pwd)/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile               # Caddyfile is valid
```
