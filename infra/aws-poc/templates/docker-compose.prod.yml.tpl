# Rendered by Terraform (compute.tf) into user-data, which writes it to the app directory as
# docker-compose.yml and runs `docker compose --env-file .env up -d`. NOT a `-f docker-compose.yml
# -f docker-compose.prod.yml` overlay of the repo-root compose file: the root file's `build:` context
# doesn't apply here (images are pre-built and pulled from ECR — see README), so this is a
# self-contained equivalent instead, matching the same three services + one addition (the edge
# reverse proxy) per the scoping report §6/§1.
#
# Doubled-dollar tokens below (NEXTAUTH_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
# MONGO_ROOT_USERNAME, MONGO_ROOT_PASSWORD) are DELIBERATELY escaped Terraform interpolation —
# they must reach disk as a literal single-dollar reference, resolved by `docker compose` itself
# from the `.env` file user-data writes AFTER fetching the real secret values from SSM (never
# baked in by Terraform — see secrets.tf).
#
# Only `edge` publishes a host port, matching the security group's single open ingress rule:
# web/agents/mongo are reachable only over the internal compose network, never the host.

name: cmw-poc

services:
  web:
    image: ${web_image}
    environment:
      AGENTS_URL: http://agents:8000
      NODE_ENV: production
      # See README "Why web doesn't use SECRETS_BACKEND=aws": NEXTAUTH_SECRET and the two Google
      # OAuth creds are pre-materialized here by user-data (fetched once from SSM) rather than
      # resolved live via the aws backend, because that backend's AWS SDK is Node-only and
      # web/auth.ts is bundled for the Edge runtime by middleware.ts (web/AGENTS.md's own
      # documented sharp edge on this point).
      SECRETS_BACKEND: env
      NEXTAUTH_SECRET: $${NEXTAUTH_SECRET}
      # Google is active only when both are non-blank (docs/auth.md) — GOOGLE_CLIENT_ID/SECRET are
      # populated out-of-band in SSM (secrets.tf deliberately does not manage them), so on a fresh
      # apply before that happens these resolve to empty strings and web/auth.ts falls back to the
      # identity-declaration login, same as local dev with no creds.
      GOOGLE_CLIENT_ID: $${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: $${GOOGLE_CLIENT_SECRET}
      AUTH_ALLOWED_EMAIL_DOMAIN: ${auth_allowed_email_domain}
      # Pinned OAuth callback base URL — see docker-compose.yml (repo root) for why this can't be
      # left to request-based inference (a token-exchange host mismatch, found by diagnosis).
      AUTH_URL: ${auth_url}
    depends_on:
      agents:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://127.0.0.1:3000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 25s
    restart: unless-stopped

  agents:
    image: ${agents_image}
    environment:
      ENVIRONMENT: production
      # Resolved live from SSM via the instance role (agents/app/secrets/) — the real values for
      # ANTHROPIC_API_KEY / MONGO_URL / BRAIN_REPO_URL / BRAIN_DEPLOY_KEY never land in this file,
      # an image layer, or `docker inspect` output.
      SECRETS_BACKEND: aws
      SECRETS_AWS_SSM_PREFIX: ${ssm_prefix}
      # This image's botocore build only honors AWS_DEFAULT_REGION, not AWS_REGION (confirmed via
      # boto3.client("ssm") in the built image) — set both so boto3 always resolves a region and
      # future SDK builds that do honor AWS_REGION keep working too.
      AWS_REGION: ${aws_region}
      AWS_DEFAULT_REGION: ${aws_region}
      # No bind-mounted host clone here (unlike local dev's docker-compose.yml): every
      # GitBrain/GitContentStore commit auto-pushes to BRAIN_REPO_URL's remote (best-effort;
      # cmw-brain-split's GitRepo.commit), so the durable copy of any edit is the GitHub repo, not
      # this container's filesystem — a plain in-container path re-clones correctly on every
      # restart via app.git.ensure_brain_available (main.py's lifespan). Left unset in SSM
      # (brain_repo_url_placeholder's default), this just no-ops exactly like local dev with no
      # brain configured.
      BRAIN_ROOT: /brain
      # Not a secret — a plain resource identifier (app/publish/README.md). The instance role's
      # own s3:PutObject grant (iam.tf) is what actually authorizes the upload; boto3 resolves
      # ambient credentials via IMDS exactly like the aws secrets backend above.
      PUBLISHED_ASSETS_BUCKET: ${published_assets_bucket}
      PUBLISHED_ASSETS_REGION: ${aws_region}
      # Not a secret — a plain resource identifier (agents/app/drive/README.md), same treatment as
      # PUBLISHED_ASSETS_BUCKET above. Blank degrades cleanly: Docs land loose at the Drive root.
      GOOGLE_SHARED_DRIVE_ID: ${google_shared_drive_id}
      # LLM backend selection (agents/app/config.py) — plain config, not a secret. "openrouter"
      # is the OpenAI-compatible path pointed at OpenRouter (OPENAI_API_KEY via the SSM shim;
      # OPENAI_BASE_URL optional — quoted so a blank value renders as an empty string, which is
      # what applies the backend's own endpoint default).
      LLM_BACKEND: ${llm_backend}
      OPENAI_BASE_URL: "${openai_base_url}"
      OPENROUTER_DEFAULT_MODEL_ID: ${openrouter_default_model_id}
    depends_on:
      mongo:
        condition: service_healthy
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  mongo:
    # Pinned to an explicit patch tag, not the floating `mongo:7`, so a redeploy can't silently
    # pull a different image (P0 hardening, cmw-security-p0). Bump this deliberately to the latest
    # 7.0.x patch; Mongo publishes no host port (internal compose network only), so its CVE
    # surface is not internet-reachable.
    image: mongo:7.0.40
    environment:
      MONGO_INITDB_ROOT_USERNAME: $${MONGO_ROOT_USERNAME}
      MONGO_INITDB_ROOT_PASSWORD: $${MONGO_ROOT_PASSWORD}
    volumes:
      # The persistent, instance-replacement-surviving EBS volume mounted by user-data — NOT a
      # plain named/anonymous Docker volume, which would be lost on instance replacement.
      - ${mongo_mount_path}/db:/data/db
    healthcheck:
      test:
        [
          "CMD",
          "mongosh",
          "--quiet",
          "-u",
          "$${MONGO_ROOT_USERNAME}",
          "-p",
          "$${MONGO_ROOT_PASSWORD}",
          "--authenticationDatabase",
          "admin",
          "--eval",
          "db.adminCommand('ping').ok",
        ]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped

  edge:
    image: caddy:2-alpine
    # Only ${edge_port} (plain HTTP) is published — CloudFront (infra/aws-poc/edge_cloudfront.tf)
    # terminates the public TLS connection with an ACM cert and forwards here over HTTP, inside
    # the security group's CloudFront-origin-facing-prefix-list lock. Caddy no longer serves public
    # TLS at all, so there's no cert-bearing HTTPS port to publish and no ACME state to persist
    # (see templates/user-data.sh.tpl's generated Caddyfile — auto_https is explicitly off).
    ports:
      - "${edge_port}:${edge_port}"
    volumes:
      # Written by user-data alongside this file — see templates/user-data.sh.tpl.
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on:
      web:
        condition: service_healthy
    restart: unless-stopped
