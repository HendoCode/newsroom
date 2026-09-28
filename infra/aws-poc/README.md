# AWS POC deploy — newsroom

OpenTofu for a single-EC2 "kick the tires" deploy: one `t3.medium`, running the same
three-container stack (`web` / `agents` / `mongo`) as local dev, plus a Caddy container
that's the ONLY thing on that instance able to talk to `web` — reached exclusively through a
CloudFront + AWS WAF edge in front of it (see "Edge: CloudFront + AWS WAF" below), never directly
from the internet. The app's own sign-in (`docs/auth.md`) remains the innermost access gate; an
edge basic-auth password used to sit in front of that too until `cmw-remove-edge-basic-auth`
removed it as redundant. Built from `firstmate/data/cmw-aws-deploy-scope/report.md`
(architecture/cost/decisions), the actual secrets-shim contract landing in the sibling PR "Add
provider-agnostic, just-in-time secrets shim" (`agents/app/secrets/`, `web/lib/secrets/`), and
`firstmate/data/cmw-architecture/security/vpo-app-hardening-options.md` (the CloudFront/WAF/
origin-lock hardening below).

**This directory describes the hardened, live deployment.** The original deploy (no
CloudFront/WAF, origin SG open to `0.0.0.0/0`) was applied and later compromised via a direct hit
on that open origin — see "Edge: CloudFront + AWS WAF" below. The CloudFront/WAF/origin-lock changes
in this Terraform (`waf.tf`, `edge_cloudfront.tf`, the
`security.tf`/`secrets.tf`/`templates/` edits alongside them), plus the subsequent move to
Cloudflare-managed DNS on `hendocode.com` (managed in the separate `dns-infra` project). The AWS
POC code here is retained as a sanitized reference with fake placeholders; see
"DNS posture: Cloudflare + OpenTofu on `hendocode.com`" below.

**This directory is now a historical / portfolio artifact.** The live edge and DNS posture has
moved to Cloudflare + GitHub Pages (`hendocode.com`, via the `dns-infra` project). The Route53
zone ID and AWS account identifiers in this tree have been replaced with placeholders; do not
attempt a real `tofu apply` from these files as written.

## What this creates

- 1× `aws_instance` (`t3.medium`, Amazon Linux 2023, no SSH key — shell access is SSM Session
  Manager only), given its own public IPv4 on launch (`associate_public_ip_address`) — no Elastic
  IP; see "Edge: CloudFront + AWS WAF" below, "EIP removed" for what that trades away.
- 1× security group: `var.edge_port` (default `80`) open ONLY to AWS's CloudFront-origin-facing
  managed prefix list — **not** `0.0.0.0/0` (see "Edge: CloudFront + AWS WAF" below for why that
  changed, and for the secret-header second half of the origin lock). No SSH ingress.
- CloudFront distribution + AWS WAF v2 web ACL in front of the instance, with ACM TLS — see "Edge:
  CloudFront + AWS WAF" below for the full design.
- Legacy Route53 records (`dns.tf`) are retained as a sanitized reference only. The live DNS
  posture is Cloudflare-managed OpenTofu on `hendocode.com`; see the `dns-infra` project and
  "DNS posture: Cloudflare + OpenTofu on `hendocode.com`" below.
- 1× separate, persistent `aws_ebs_volume` for Mongo's data directory (NOT the root volume) +
  `aws_volume_attachment`, so work-state survives an instance replacement — `prevent_destroy`
  means a plain `tofu destroy` will refuse to delete it (see "Teardown").
- IAM instance role: `AmazonSSMManagedInstanceCore` (Session Manager) +
  `AmazonEC2ContainerRegistryReadOnly` (image pulls) + one inline policy scoped to
  `ssm:GetParameter` on exactly `var.ssm_prefix*` (default `/newsroom/*`).
- SSM Parameter Store (SecureString) under that prefix: `ANTHROPIC_API_KEY` (placeholder —
  captain populates the real value, see below), `NEXTAUTH_SECRET`, `MONGO_URL`,
  `MONGO_ROOT_USERNAME`/`MONGO_ROOT_PASSWORD`, `ORIGIN_VERIFY_SECRET` (Terraform-generated, the
  CloudFront origin-lock secret — see "Edge: CloudFront + AWS WAF" below),
  `BRAIN_REPO_URL`/`BRAIN_DEPLOY_KEY` (SSM rejects empty-string values, so these two are only
  created when `brain_repo_url_placeholder`/`brain_deploy_key_placeholder` are non-blank — the
  default blank leaves the parameter absent entirely, which the app's secrets shim treats the same
  as a blank value: a fully-degraded no-op, same as local dev with no brain configured. Set the var
  or `put-parameter` out-of-band, then re-apply, to enable the `HendoCode/masthead`
  clone-on-boot `cmw-brain-split` added). `BRAIN_DEPLOY_KEY` holds an SSH deploy-key private key,
  not a PAT — see "Brain push credential" below for generate/install/store steps.
  `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`/`GOOGLE_OAUTH_REFRESH_TOKEN` (the Drive
  connector + Google Docs export grant `agents` resolves live via the secrets shim, same
  blank-by-default/opt-in-parameter convention as the two brain params above — see "Google
  Docs/Drive OAuth grant for `agents`" below; **not** the same credential as `GOOGLE_CLIENT_ID`/
  `GOOGLE_CLIENT_SECRET` just below, which are `web`'s sign-in grant). `GOOGLE_CLIENT_ID`
  / `GOOGLE_CLIENT_SECRET` are **not created by this Terraform at all** — they're populated
  out-of-band (like the Anthropic key) and merely read by `user-data`; see "Auth: Google OAuth
  restricted to a single domain" below.
- 2× `aws_ecr_repository` (`cmw-poc-web`, `cmw-poc-agents`, `force_delete = true`).
- 1× `aws_s3_bucket.published_assets` (`publish_bucket.tf`) for the `finalized → published` HITL
  button's durable outputs (see `agents/app/publish/README.md`) — versioned, `prevent_destroy`
  (same durable-storage idiom as `aws_ebs_volume.mongo_data` below), **unconditional** (not
  `count`-gated on any variable, unlike the five optional SSM secrets below — a captain
  requirement). Deliberately **generally public by bucket policy**: `s3:GetObject` for anyone,
  bucket listing (`s3:ListBucket`) never granted, no signed URLs/unguessable keys (Hendo's
  explicit v1 call — see "Sharp edges" below for why that's harder to walk back than it looks).
  The instance role gets a matching `s3:PutObject`-only inline policy (`iam.tf`) — reads never go
  through the role, only through the public policy.
- `user_data` that installs Docker, pulls the two images from ECR, mounts the persistent Mongo
  volume, and runs a self-contained prod compose file (`templates/docker-compose.prod.yml.tpl`:
  `web` + `agents` + `mongo` + a Caddy edge proxy that serves plain HTTP only, checking every
  request for the CloudFront origin-lock secret header before proxying to `web` — see "Edge:
  CloudFront + AWS WAF" below) with `SECRETS_BACKEND=aws` on `agents` so it resolves its secrets
  from SSM via the instance role.

## Edge: CloudFront + AWS WAF

**Why this exists:** the original deploy put Caddy directly on the open internet — the origin SG
accepted `0.0.0.0/0` on 80/443, with only the app's own Google OAuth gate in front, no WAF, no rate
limiting, no origin hiding. The instance was compromised via a **direct hit on that open origin**
(a Next.js middleware-bypass CVE walked straight through the only gate). App-layer auth alone
proved insufficient. Full options analysis:
`firstmate/data/cmw-architecture/security/vpo-app-hardening-options.md` — this implements Option 2
("AWS-native, if staying off Cloudflare"), the single highest-value change from that doc
independent of everything else in it: **stop the origin being directly reachable from the whole
internet.**

**What's new** (`waf.tf`, `edge_cloudfront.tf`, plus the `security.tf`/`secrets.tf`/`templates/`
edits alongside them):

- **AWS WAF v2 web ACL** (`scope = CLOUDFRONT`, so it's created via the us-east-1 API endpoint
  regardless of `var.region` — same reasoning as the ACM cert below): AWS managed rule groups
  `AWSManagedRulesCommonRuleSet` + `AWSManagedRulesKnownBadInputsRuleSet` +
  `AWSManagedRulesAmazonIpReputationList`, plus a per-IP rate-based rule
  (`var.waf_rate_limit_per_5min`, default 2000 req / ~5 min) — the pattern that preceded the
  original compromise. CloudWatch metrics + sampled requests enabled on every rule.
- **CloudFront distribution** fronting the app, with that web ACL attached and an ACM certificate
  (us-east-1, DNS-validated) for `var.edge_domain`. Caching is fully disabled
  (`Managed-CachingDisabled`) and every viewer header/cookie/query string is forwarded unmodified
  (`Managed-AllViewer`) — this is a dynamic, authenticated app (session cookies, an OAuth
  redirect round-trip), never a static site; caching or dropping headers here would silently break
  sign-in.
- **Origin lock** (`security.tf`): the origin SG's ingress on `var.edge_port` is restricted to the
  `com.amazonaws.global.cloudfront.origin-facing` managed prefix list — **not** `0.0.0.0/0` — and
  `var.edge_https_port` is no longer opened at all. Because that prefix list is shared across
  **every** CloudFront customer's origins, not just this one, it alone only proves "some
  CloudFront distribution somewhere," not "our distribution" — so CloudFront also injects a secret
  custom origin header (`X-Origin-Verify`, `random_password.origin_verify_secret` in `secrets.tf`,
  stored in SSM under `ORIGIN_VERIFY_SECRET` the same way `NEXTAUTH_SECRET` is), and the generated
  Caddyfile (`templates/user-data.sh.tpl`) 403s any request missing it, before it ever reaches
  `web`. Both halves are load-bearing; either alone is insufficient.

### DNS posture: Cloudflare + OpenTofu on `hendocode.com` (live); Route53 placeholder here

The **current** Content Machine DNS story lives in the separate **`dns-infra`** project:
Cloudflare-managed records for `hendocode.com`, driven by OpenTofu, with plan-only gating
and credentials kept out of code. See `dns-infra/README.md` for the zone inventory,
record types, import strategy, and exact `tofu plan`/`apply` commands.

This AWS POC stack retains the historical Route53 resources in `dns.tf` as an
illustrative artifact, but the real zone ID and account identifiers have been replaced
with clearly fake placeholders (`<ROUTE53_ZONE_ID>`, `<AWS_ACCOUNT_ID>`). The Route53
path is no longer the live posture; do not copy these identifiers into a real deploy.

The original design in `dns.tf` looked up an `aws_route53_zone` by zone ID and wrote
ACM-validation CNAMEs, a public CloudFront ALIAS, and an origin A record. That flow has
been superseded by the Cloudflare/GitHub Pages setup in `dns-infra`; what remains here is
a sanitized snapshot for reference only.

### TLS / origin-protocol approach (resolved)

Locking the SG to CloudFront's prefix list breaks Caddy's existing public Let's Encrypt HTTP-01
flow outright — port 80 is no longer world-reachable, and HTTP-01 needs it to be. Two real options
existed: keep Caddy doing TLS somehow (a Cloudflare-style origin cert, or DNS-01 ACME needing a
DNS-provider API credential this repo doesn't have), or stop asking Caddy to do public TLS at all.
**Chosen: the latter.** CloudFront terminates the public TLS connection with the ACM certificate
above and forwards to the origin over **plain HTTP** (`custom_origin_config.origin_protocol_policy
= "http-only"`), inside the now-locked SG + the secret header. Caddy's generated config
(`templates/user-data.sh.tpl`) drops automatic HTTPS entirely (`auto_https off`, no more `email`/
`https_port` global options) and just listens on a bare `:$EDGE_PORT` address — no domain name in
the site block at all, so there's nothing left that could trigger Caddy to attempt ACME again even
by accident. The app's own Google OAuth gate (`docs/auth.md`) is untouched — this is
defense-in-depth layered in front of it, not a replacement for it. `AUTH_URL` is derived from
`var.edge_domain` (`compute.tf`: `"https://${var.edge_domain}"`) since that's still the hostname
real users and the OAuth callback see; only the origin's own inbound protocol changed.

### EIP removed (origin now tracks the instance's own public IP)

Before Route53 owned DNS for this domain (pre-PR #98), `origin.<edge_domain>` was pointed at a
pre-existing, reused Elastic IP (`data "aws_eip"` + `aws_eip_association`) specifically so a
stop/start or instance replacement never needed a follow-up DNS change — nothing here re-wrote the
record automatically back then. Now that every public-IP change already flows through a `tofu
apply` that rewrites `aws_route53_record.origin` to match (`dns.tf`), the EIP's only remaining
value — surviving an IP change with no apply — no longer applies, so it's gone: `compute.tf`'s
`aws_instance.app` gets a plain, ephemeral public IPv4 on launch (`associate_public_ip_address`),
and `dns.tf`'s `aws_route53_record.origin` A-records `origin.<edge_domain>` to
`aws_instance.app.public_ip` directly — no `data "aws_eip"`, no `aws_eip_association`, no
`eip_allocation_id` variable.

**What this trades away**: the EIP made an instance-IP change self-healing with no apply at all —
a manual stop/start, or AWS retiring the underlying host, kept the same address. Without it, any
IP change that does **not** go through `tofu apply` leaves `origin.<edge_domain>` pointing at a
dead address until the next apply; only a `tofu apply`-driven instance replacement (e.g.
`-replace=aws_instance.app`) rewrites the record automatically. The record's 300s TTL also means an
apply-driven instance replacement has a brief window (up to 300s) where CloudFront's origin still
resolves to the old, now-dead IP before resolvers catch up.
- To point this at a different domain later: update `var.edge_domain`, then `tofu apply` — `dns.tf`
  writes the new records automatically (as long as the new domain is the root `example.com` zone or
  a subdomain of it; a genuinely different root zone would need `dns.tf`'s zone lookup updated too).

### Follow-up not done here (documented, not built — see task brief's "optional stretch")

Moving `cmw-poc-published-assets` (`publish_bucket.tf`) behind a second CloudFront distribution +
Origin Access Control (private bucket, no public bucket policy) would let the account-level S3
Block-Public-Access be fully locked — closing the one caveat `publish_bucket.tf`'s own comments
already flag ("a one-way door in practice"). Left as a follow-up rather than folded into this PR:
it's a materially separate distribution/OAC/bucket-policy change from the app-origin lock above,
and bundling it here would roughly double this PR's review surface for a bucket that isn't what
compromised the instance.

> Before any real apply below, run the mandatory security scan gate —
> [`deploy/README.md`](../../deploy/README.md).

## Apply sequence (for whoever runs this — captain-present, per the launch brief)

Requires `tofu` and AWS credentials for the target account/region (the account IAM identity used
also needs write access to the `example.com` zone in the separate `vpo-aws-account-baseline`
project for step 3's Route53 records — see "DNS + ACM: fully automated via Route53" above). Read
"Edge: CloudFront + AWS WAF" above (including "DNS + ACM: fully automated via Route53" and "TLS /
origin-protocol approach") before starting — DNS/ACM is fully Terraform-managed, so there's no
separate manual DNS step folded into this sequence.

1. **Create just the ECR repos first** (the instance's first boot needs images to already exist,
   so bootstrap them before the instance that will pull them):
   ```
   cd infra/aws-poc
   tofu init
   tofu apply -target=aws_ecr_repository.web -target=aws_ecr_repository.agents
   ```
2. **Build and push both images** (from the repo root). The instance is `x86_64` — building on an
   Apple Silicon (arm64) machine needs an explicit `--platform linux/amd64` or the image you push
   has no amd64 manifest at all, and the instance's later `docker compose pull` fails with `no
   matching manifest for linux/amd64 in the manifest list entries` (see AGENTS.md Sharp edges):
   ```
   WEB_REPO=$(tofu output -raw web_ecr_repository_url)
   AGENTS_REPO=$(tofu output -raw agents_ecr_repository_url)
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${WEB_REPO%/*}"

    docker buildx build --platform linux/amd64 --build-arg BUILD_COMMIT=$(git rev-parse HEAD) -t "$WEB_REPO:latest" --push ./web
    docker buildx build --platform linux/amd64 --build-arg BUILD_COMMIT=$(git rev-parse HEAD) -t "$AGENTS_REPO:latest" --push ./agents
    ```
The `BUILD_COMMIT` arg bakes only the non-sensitive commit SHA (plus short form and UTC build time) into static metadata files inside each image (`web/public/.well-known/cmw-build.json` and `agents/cmw-build.json`). After deploy the public unauthenticated endpoints `https://<edge-domain>/.well-known/cmw-build.json` (web only) and `https://<edge-domain>/api/build` (aggregated web+agents) expose exactly those fields. See AGENTS.md for the safety note.
3. **Full apply** (everything else — instance, SG, IAM, secrets, the persistent
   volume, the WAF web ACL, the CloudFront distribution, and — since DNS/ACM are now fully
   Terraform-managed via the account's `example.com` zone (see "DNS + ACM: fully automated via
   Route53" above) — the ACM cert's DNS validation record(s) and both the public ALIAS and the
   origin A record, no manual DNS step):
   ```
   tofu apply
   ```
   `aws_acm_certificate_validation` blocks until ACM sees its validation record resolve, and the
   CloudFront distribution itself takes several minutes to leave `InProgress` — size your apply
   window for both; neither is a hang.
4. **Populate the real secrets** (placeholders only exist so far):
   ```
   aws ssm put-parameter --name /newsroom/ANTHROPIC_API_KEY \
     --type SecureString --overwrite --value "sk-ant-..."
   ```
   `agents`' secrets shim caches for `SECRETS_CACHE_TTL_SECONDS` (default 300s) — no restart
   needed, just wait up to 5 minutes. Optionally also populate `BRAIN_REPO_URL`/`BRAIN_DEPLOY_KEY`
   the same way (see "Brain push credential" below for how to generate/install the deploy key
   first) to have the instance clone `HendoCode/masthead` on next restart
   (`app.git.ensure_brain_available`) — leaving them blank is a fully-supported no-op (brain-
   dependent screens just stay empty/503, same as local dev with no brain configured). Same story
   for `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`/`GOOGLE_OAUTH_REFRESH_TOKEN` — see
   "Google Docs/Drive OAuth grant for `agents`" below.

   **Before re-running `tofu apply` after any of `brain_repo_url_placeholder`,
   `brain_deploy_key_placeholder`, `google_oauth_client_id_placeholder`,
   `google_oauth_client_secret_placeholder`, or `google_oauth_refresh_token_placeholder` has ever
   been set non-blank once (to create the parameter): pass that same non-blank placeholder value
   again on every subsequent apply, or omit it only once you've confirmed the plan shows no change
   to that parameter.** Each of these five is `count = var.x_placeholder != "" ? 1 : 0` — a bare
   `tofu apply` with no `-var` flags falls back to the codified default (blank), which computes
   `count = 0` and proposes **destroying** any of these that already exist for real, even though
   the real value lives safely in SSM and was never touched. This is exactly the "plan shows
   destroy of an existing resource" case to always stop and double-check before approving — review
   the plan in full, and if it proposes destroying any of these, re-run with `-var` flags
   reproducing the non-blank value used to originally create them (the value itself doesn't matter
   post-creation, since `ignore_changes` means `tofu` never overwrites the real one — any non-blank
   placeholder satisfies `count = 1`).
5. Share `tofu output app_url` with reviewers — they sign in with a `example.com` Google Workspace
   account (`docs/auth.md`); there is no separate shared password to distribute. Confirm it's
   actually going through CloudFront (e.g. a `Via` or `X-Cache` response header from CloudFront)
   before considering the deploy complete.

Re-running step 2 (image build/push) followed by step 3 after bumping
`web_image_tag`/`agents_image_tag` replaces the instance's user-data and requires a fresh `tofu
apply` — instance user-data only runs on first boot, so redeploying a new image version means
either tainting the instance (`tofu apply -replace=aws_instance.app`) or SSM-ing in and re-running
the pull/up commands by hand. This is a POC trade-off (no CI/CD pipeline in scope here); the
persistent Mongo volume survives either path. Neither path touches the CloudFront
distribution/WAF/ACM cert — those are untouched by an instance replacement.

## Populating the real secrets

`ANTHROPIC_API_KEY` and (for real sign-in) `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` need real
values from the captain to make the app usable — everything else (`NEXTAUTH_SECRET`, Mongo creds)
is generated by Terraform itself via `random_password`. Drive/Docs
access for `agents` (`GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`/
`GOOGLE_OAUTH_REFRESH_TOKEN`) and the brain clone (`BRAIN_REPO_URL`/`BRAIN_DEPLOY_KEY`) are
optional — every screen that depends on them degrades cleanly, never crashes, while unpopulated.
`aws_ssm_parameter.anthropic_api_key` (and the brain-split and Google OAuth placeholders) carry
`lifecycle { ignore_changes = [value] }`, so overwriting them in SSM directly is safe — a later
`tofu apply` will never revert them back to the placeholder, **as long as that apply's `-var`
flags still make each parameter's `count` evaluate to `1`** — see the warning in "Apply sequence"
step 4 above; unlike `anthropic_api_key` (always created), the brain and Google OAuth params are
opt-in and a bare re-apply can silently propose destroying them. `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET` have no Terraform-managed parameter at all (see "Auth: Google OAuth
restricted to a single domain" below), so there's nothing for `tofu apply` to revert regardless —
`put-parameter --overwrite` is the only way either value ever changes. Leaving them unpopulated is
fully supported: `web` falls back to the identity-declaration login until they're set.

## LLM backend (OpenRouter)

`agents`'s inference backend is plain (non-secret) config threaded through as Terraform
variables — `llm_backend` (default `bedrock`), `openai_base_url` (default blank),
`openrouter_default_model_id` (default `z-ai/glm-5`) — rendered into the agents container's
environment by `compute.tf` (see `variables.tf`). `LLM_BACKEND=openrouter` routes every
pipeline step through the OpenAI-compatible provider pointed at OpenRouter; `OPENAI_API_KEY`
(an OpenRouter key) resolves through the SSM secrets shim exactly like the other provider keys,
so no Terraform/SSM change is needed to switch backends — just an apply with
`-var llm_backend=openrouter` (and optionally `-var openai_base_url=...`). `openai_base_url`
blank keeps each backend's own endpoint default (OpenRouter for `openrouter`, api.openai.com /
the openai SDK's native `OPENAI_BASE_URL` read for `openai`). Because this threads through
`templates/docker-compose.prod.yml.tpl`, a backend switch is a `user_data` change — deploy it
with `tofu apply -replace=aws_instance.app` carrying those `-var` flags, not a plain apply
(see "Apply sequence"). The
step-tier model slug is `OPENROUTER_DEFAULT_MODEL_ID` (default `z-ai/glm-5` — the same GLM-5
tier as the bedrock backend, under OpenRouter's vendor/model slug); cost readouts price it at
the GLM-5 rates in `agents/app/llm/pricing.py`, so a different slug needs its rates added there
or the readout shows 0.0.

## Brain push credential (SSH deploy key)

`BRAIN_DEPLOY_KEY` is an SSH **deploy key** — a repo-scoped, read-write credential authorizing
push/pull against exactly `HendoCode/masthead` and nothing else (least-privilege:
compare to a classic PAT, which is scoped to every repo the token's user can see). The private key
never touches this Terraform config, an image layer, or `.git/config` — `agents/app/git/ssh_auth.py`
resolves it through the secrets shim at runtime and materializes it into a process-local, mode-0600
file for the lifetime of the container.

1. **Generate a dedicated ed25519 keypair** (do this once, not on the instance — a laptop or CI
   runner is fine; nothing here needs the instance to have generated it):
   ```
   ssh-keygen -t ed25519 -C "cmw-brain-deploy-key" -f ./cmw-brain-deploy-key -N ""
   ```
   This writes `cmw-brain-deploy-key` (private) and `cmw-brain-deploy-key.pub` (public).
2. **Install the public key on the brain repo** — `HendoCode/masthead` → Settings →
   Deploy keys → Add deploy key → paste `cmw-brain-deploy-key.pub` → check **Allow write access**
   (unchecked defaults to read-only, which breaks `GitRepo.commit()`'s auto-push) → Add key.
3. **Store the private key in SSM** (never in a committed file, never as a `tofu` variable/CLI
   argument):
   ```
   aws ssm put-parameter --name /newsroom/BRAIN_DEPLOY_KEY \
     --type SecureString --overwrite --value "$(cat ./cmw-brain-deploy-key)"
   ```
   Also populate `BRAIN_REPO_URL` with the **SSH** clone URL (not HTTPS):
   ```
   aws ssm put-parameter --name /newsroom/BRAIN_REPO_URL \
     --type SecureString --overwrite --value "git@github.com:HendoCode/masthead.git"
   ```
   Then delete the local private key file (`rm ./cmw-brain-deploy-key*`) — SSM is its only home
   from here on.
4. Restart/replace the `agents` container (or wait for the next boot) to pick up the new
   credential — `ensure_brain_available` clones/pulls over SSH using
   `GIT_SSH_COMMAND` with strict host-key checking pinned to GitHub's own published host keys (no
   interactive prompt, no trust-on-first-use).

**Upgrading later**: a deploy key is single-repo and long-lived (no built-in expiry or audit
trail beyond GitHub's own deploy-key log). If short-lived tokens or per-installation audit ever
matter more than this POC needs, the next step up is a **GitHub App** installed on just this repo,
minting short-lived installation tokens the secrets shim would resolve the same way (a new
provider branch in `agents/app/git`, out of scope here).

## Google Docs/Drive OAuth grant for `agents`

**A different credential from the "Auth" section below** — this one authorizes `agents` itself
(the Google Drive connector's reads, `agents/app/connectors/`, plus the finalize/review Google
Docs export's writes, `agents/app/render/` and `agents/app/review/`), not `web`'s sign-in. See
`agents/app/connectors/README.md` for the full consent-flow walkthrough; this section covers only
the SSM half.

1. **In Google Cloud Console**, create (or reuse) an OAuth 2.0 client (type: Web application) in
   the project tied to the company Workspace, and complete a one-time **offline** consent granting
   **both** scopes — `https://www.googleapis.com/auth/drive.readonly` (the connector's reads) and
   `https://www.googleapis.com/auth/drive.file` (the Docs export's writes/comments; also what the
   review round-trip needs). Requesting both up front avoids a second consent pass later — the
   same client id/secret/refresh token serve every one of these features.
2. **Store all three values in SSM** (never in a committed file, never as a `tofu`
   variable/CLI argument):
   ```
   aws ssm put-parameter --name /newsroom/GOOGLE_OAUTH_CLIENT_ID \
     --type SecureString --overwrite --value "<client id>"
   aws ssm put-parameter --name /newsroom/GOOGLE_OAUTH_CLIENT_SECRET \
     --type SecureString --overwrite --value "<client secret>"
   aws ssm put-parameter --name /newsroom/GOOGLE_OAUTH_REFRESH_TOKEN \
     --type SecureString --overwrite --value "<refresh token>"
   ```
   Unlike `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` below, `agents` resolves these three **live**
   through the secrets shim (`SECRETS_BACKEND=aws`, same as `ANTHROPIC_API_KEY`/`BRAIN_REPO_URL`)
   rather than as a pre-materialized container env var — no restart needed, just wait up to
   `SECRETS_CACHE_TTL_SECONDS` (default 300s). This also means **rotating** the refresh token later
   is the same `put-parameter --overwrite` command with no redeploy.
3. Leaving any of the three unpopulated is fully supported: the Drive connector reports a clear
   per-source error on refresh instead of crashing (`app/connectors/refresh.py`), and the
   finalize/review Google Docs export routes return a clean 503 ("not configured") instead of
   attempting a call (`app/review/routes.py`, `app/render/docs_export.py`).

## Google Shared Drive for per-piece folders

`var.google_shared_drive_id` (`GOOGLE_SHARED_DRIVE_ID` on `agents`) is the Shared Drive that every
piece's Drive folder (`agents/app/drive/README.md`) gets created under. Unlike the OAuth trio
above, this is **not a secret** — a plain resource id, same treatment as `published_assets_bucket`
— so it's a real Terraform variable with its actual value as the default, not an SSM parameter.
The Shared Drive itself, and the OAuth grant's Google account being a member of it, are provisioned
out-of-band (never by this Terraform or this code) — see that README's "Configuration" section.
Blank degrades exactly like an unset `PUBLISHED_ASSETS_BUCKET`: Docs land loose at the Drive root,
no folder pointers are ever written onto a `Piece`. Changing it takes effect on the next
`agents` restart/replace (it's pre-materialized into the compose file at render time, not resolved
live via the secrets shim).

## Auth: Google OAuth restricted to a single domain

**A different credential from "Google Docs/Drive OAuth grant for `agents`" above** — this one is
`web`'s sign-in grant, never read by `agents`. Sign-in (`web/auth.ts`, `docs/auth.md`) is Google
Workspace OAuth restricted to
`var.auth_allowed_email_domain` (default `example.com`) whenever `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET` are both configured — which, on this deploy, means whenever the captain has
populated the two SSM parameters below. Left unpopulated, `web` falls back to the local-dev
identity-declaration login (the same graceful degradation as every other optionally-populated
secret in this config), so a fresh apply never bricks sign-in while waiting on Google credentials.

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` are SSM SecureString parameters populated
  **out-of-band**, exactly like `ANTHROPIC_API_KEY` — **this Terraform never declares them as
  `aws_ssm_parameter` resources** (unlike `NEXTAUTH_SECRET`/Mongo creds, which Terraform generates
  itself). Declaring them here would fight the out-of-band value on every `tofu apply`, the same
  reason `brain_repo_url_placeholder`/`brain_deploy_key_placeholder` are opt-in rather than always
  written. Populate them the same way as the Anthropic key:
  ```
  aws ssm put-parameter --name /newsroom/GOOGLE_CLIENT_ID \
    --type SecureString --overwrite --value "<client id>"
  aws ssm put-parameter --name /newsroom/GOOGLE_CLIENT_SECRET \
    --type SecureString --overwrite --value "<client secret>"
  ```
- `user-data` fetches both by name at boot (`templates/user-data.sh.tpl`'s
  `get_param_optional` — tolerant of the parameter being entirely absent, not just blank) and
  pre-materializes them into the `web` container's environment
  (`templates/docker-compose.prod.yml.tpl`), the same treatment as `NEXTAUTH_SECRET` and for the
  same reason — see "Why web doesn't use SECRETS_BACKEND=aws" below. A fresh apply before the
  params are populated resolves both to empty strings, which `web/auth.ts` treats as "Google not
  configured" (never a crash).
- `AUTH_ALLOWED_EMAIL_DOMAIN` is **not** a secret — it's `var.auth_allowed_email_domain`
  (`variables.tf`, default `example.com`), baked into the generated compose file directly.
- The registered redirect URI for this deploy is `https://<var.edge_domain>/api/auth/callback/google`
  (default `https://example.com/api/auth/callback/google`) — must be added to the Google
  Cloud OAuth 2.0 Web client's authorized redirect URIs alongside the local-dev ones (see
  `docs/auth.md`).
- Restarting/replacing the `web` container (or waiting for the next boot) after populating the two
  params picks them up — same "restart to refresh a pre-materialized secret" caveat as
  `NEXTAUTH_SECRET`, since nothing here re-fetches them live.

## Cost (us-east-1, per the scoping report §7 + the CloudFront/WAF hardening-options doc)

Running continuously: **~$41-55/mo** — the original ~$36-40/mo (EC2 `t3.medium` ~$30.37, EBS gp3
root 30GB + data 20GB ~$4, a public IPv4 address ~$3.65, light data transfer, ECR storage, SSM
Parameter Store free) **plus ~$5-15/mo for CloudFront + WAF**: WAF is ~$5/mo base web ACL + ~$1/mo
per rule (4 rules here: 3 managed groups + 1 rate rule ≈ $9/mo) + ~$0.60 per million requests
inspected; CloudFront is ~$0.085/GB data transfer out + ~$0.0075 per 10k HTTPS requests (both
`PriceClass_100`-scoped, US/Canada/Europe edge locations only — see `var.cloudfront_price_class`).
Drop `instance_type` to `t3.small` (~$21-23/mo total before the edge) only if a working PDF
finalize format isn't needed — see the scoping report §7 for why `t3.medium`'s headroom matters
(Next.js + FastAPI + Mongo + headless Chromium colocated).

## Teardown

```
tofu destroy
```

...will **refuse** to run at all: `aws_ebs_volume.mongo_data` AND `aws_s3_bucket.published_assets`
both carry `prevent_destroy = true` (deliberately — the volume for the "retained on instance
replacement" persistence this deploy asked for, the bucket because it may hold outputs a real
public link already points at), and OpenTofu aborts the entire destroy plan up front rather than
destroying everything else first. Two supported paths:

- **Tear down compute, keep the data volume around** (cheapest way to pause without losing
  work-state — the orphaned 20GB gp3 volume costs ~$1.60/mo on its own). **No Elastic IP backs the
  origin anymore** (see "EIP removed" above) — `aws_route53_record.origin` now depends directly on
  `aws_instance.app.public_ip`, so destroying the instance cascades to destroying that DNS record
  too (Terraform includes a target's dependents in a `-target` destroy); `origin.<edge_domain>`
  will not resolve at all while compute is torn down, and a later `tofu apply` recreates both the
  instance and the record together. This does NOT tear down CloudFront/WAF/the ACM cert (they have
  no dependency on the instance) — add
  `-target=aws_cloudfront_distribution.app -target=aws_wafv2_web_acl.cloudfront
  -target=aws_acm_certificate_validation.cloudfront -target=aws_acm_certificate.cloudfront` if you
  want those gone too (note: deleting a CloudFront distribution first requires it to be disabled,
  which can itself take several minutes — `tofu destroy` will wait; the public ALIAS
  (`aws_route53_record.app`) and the ACM validation record(s) (`aws_route53_record.cert_validation`)
  both depend on the distribution/cert respectively, so `tofu destroy` cascades to remove them too —
  no separate `-target` needed for either; the same cascade is why `aws_route53_record.origin`
  doesn't need its own `-target` below either, now that it depends on `aws_instance.app`):
  ```
  tofu destroy -target=aws_instance.app -target=aws_volume_attachment.mongo_data
  ```
  Add `-target=aws_iam_role_policy.publish_bucket_write` to also tear down compute without
  touching `published_assets` at all (the bucket itself has no attachment to the instance, so it
  is untouched by this command either way — only its write-access grant is).
- **Full wipe** (matches "throwaway," per the scoping report): remove the `lifecycle` block from
  `aws_ebs_volume.mongo_data` in `compute.tf` (or comment it out), then `tofu destroy` normally.
  **Do the same separately and deliberately for `aws_s3_bucket.published_assets`
  (`publish_bucket.tf`) if you genuinely intend to delete published outputs** — unlike the Mongo
  volume (losing it only costs re-deriving work-state), deleting this bucket breaks every
  `published_html_url`/`published_pdf_url` link anyone has ever been given, permanently. Tightening
  the bucket's *access* later (signed URLs, a CDN, per-object ACLs) is cheap and reversible; deleting
  the bucket, or a link's key inside it, is not — see `agents/app/publish/README.md`.

The two ECR repos have `force_delete = true`, so a normal `tofu destroy` removes them (and their
images) with no separate cleanup step.

## Why `web` doesn't use `SECRETS_BACKEND=aws`

`agents` gets `SECRETS_BACKEND=aws` directly (a plain FastAPI/uvicorn process — boto3 over
IMDS-forwarded instance-role credentials works with no caveats). `web` does not, on purpose:
`web/AGENTS.md`'s own documented sharp edge notes that `middleware.ts` bundles `auth.ts` for the
Next.js **Edge runtime** by default, and the AWS/Azure secrets backends there use Node-only SDKs
that aren't verified to work from edge-bundled middleware. Rather than touch application code
(out of scope for this ticket) to force `middleware.ts` onto the Node runtime, `user-data`
pre-materializes `NEXTAUTH_SECRET` (and, for the same reason, `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET` — see "Auth: Google OAuth restricted to a single domain" above) itself: it
fetches each value from SSM once at boot (same instance-role credentials, same source of truth)
and injects it as a literal env var with `SECRETS_BACKEND=env` for the `web` container — the `env`
backend is a plain `process.env` read, which **is** edge-safe. Net effect is identical (the value
still originates from SSM, resolved via the instance role); only *when* it's fetched differs from
`agents`.

## Relationship to the root `docker-compose.prod.yml` overlay

The repo root also has a production compose overlay (`docker-compose.prod.yml` + `deploy/
Caddyfile`, `docs/deploy.md`) that fronts `web` with the same kind of Caddy reverse proxy. This
deploy deliberately does **not** reuse it: that overlay is layered on top of the base
`docker-compose.yml` with `-f docker-compose.yml -f docker-compose.prod.yml`, which still needs
the base file's `build:` context — i.e. this `newsroom` repo checked out on the
host. This EC2 instance never gets a checkout or credential for **that** repo (§2 of the scoping
report) and instead pulls prebuilt `web`/`agents` images from ECR, so
`infra/aws-poc/templates/` carries its own self-contained compose file + Caddyfile that doesn't
depend on a checkout being present. Both converge on `admin off` and neither adds a gate beyond
the app's own sign-in (`docs/auth.md`) — an edge basic-auth password used to sit in front of both
until `cmw-remove-edge-basic-auth` removed it as redundant. They now also converge on `auto_https
off`, though for different reasons: the root overlay serves a bare IP with no domain, so ACME was
never viable there in the first place; this deploy has a real domain but, since the CloudFront edge
lock ("Edge: CloudFront + AWS WAF" above), Caddy here no longer has a public port to serve ACME
challenges on at all — CloudFront + ACM terminates public TLS instead. Before that lock, this
deploy's Caddy DID run automatic Let's Encrypt HTTPS directly; that's no longer the case. The root
overlay's own local `tls internal` opt-in path for **dev** HTTPS is unrelated to both of these —
see `docs/local-dev.md`.

## Debugging / direct access

No SSH key exists for logging into this instance — that's a separate thing from the
`BRAIN_DEPLOY_KEY` SSH deploy key above, which authenticates only outbound `agents` container
traffic to GitHub, never inbound access to the box itself. Shell access:

```
aws ssm start-session --target "$(tofu output -raw instance_id)" --region us-east-1
```

`web`/`agents`/`mongo` publish no host ports at all (only `edge` does, matching the security
group's single open rule) — to reach one directly for debugging, port-forward through SSM instead
of opening a port:

```
aws ssm start-session --target "$(tofu output -raw instance_id)" --region us-east-1 \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
```

User-data's own log is at `/var/log/cmw-poc-user-data.log` on the instance.

## Sharp edges

- **Nitro instances rename EBS devices.** `t3.medium` is Nitro-based, so the `/dev/sdf` device
  name given to `aws_volume_attachment` is not honored inside the guest — the kernel exposes an
  NVMe device instead (typically `/dev/nvme1n1`, but the exact number isn't guaranteed).
  `user-data.sh.tpl` resolves the real device via the stable
  `/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume-id-no-dashes>` symlink instead of
  assuming a fixed path — this is the standard AWS-documented approach and is necessary for the
  mount step to work at all.
- **First-boot chicken-and-egg.** If the instance boots before the images have been pushed to ECR
  (i.e. step 3a above ran before step 2), `user-data`'s `docker pull` fails and the stack never
  comes up. Recovery: push the images, then SSM in and re-run the pull/`docker compose up`
  commands by hand (or `tofu apply -replace=aws_instance.app` to re-run user-data from scratch).
- **IMDS hop limit.** `agents` (and `web`, at boot-time only) needs ambient AWS credentials from
  the instance metadata service, but a container is one network hop further from IMDS than the
  host itself — `metadata_options.http_put_response_hop_limit` is set to `2` (not the default `1`)
  specifically so containers can reach it. If this regresses, `SECRETS_BACKEND=aws` calls in
  `agents` will fail with credential errors even though the instance role is correctly attached.
- **IAM propagation delay.** The instance role's policies are attached moments before the instance
  launches (`depends_on` in `compute.tf`), but IAM permissions can take a few seconds to propagate
  account-wide. If user-data's first `aws ssm get-parameter`/`aws ecr get-login-password` call
  fails with `AccessDenied` on a freshly-applied stack, SSM in and re-run the failed command(s) —
  it's a timing issue, not a policy bug.
- **`terraform.tfstate` holds every secret value in plaintext** — Terraform's own limitation, not
  specific to this config (see `versions.tf`). State lives remotely in a dedicated, versioned,
  encrypted, public-access-blocked S3 bucket (`versions.tf`'s `backend "s3"` block), bootstrapped
  as its own separate stack in `infra/aws-poc-state-backend/` (see that directory's README for why
  it's separate) to avoid a chicken-and-egg dependency on itself; never committed (`.gitignore`).
  Locking is OpenTofu 1.10+'s native S3 conditional-write locking (`use_lockfile`) — no DynamoDB
  table. The retired local `terraform.tfstate`/`.backup` (kept briefly on the operator's machine as
  a migration fallback) were deleted on 2026-08-07 after independently verifying the S3 backend was
  authoritative and drift-free against real infrastructure and that an external checksummed backup
  of their content existed; see `infra/aws-poc-state-backend/README.md`'s "Protecting this stack's
  own state" for the same durability question applied to the *bootstrap* stack's own (still-local,
  deliberately unbacked-up) state file.
- **The `agents` image's botocore build only honors `AWS_DEFAULT_REGION`, not `AWS_REGION`** —
  `docker-compose.prod.yml.tpl` sets both on the `agents` service so `boto3.client("ssm")` always
  resolves a region regardless of SDK version.
- **`aws_s3_bucket.published_assets`'s public-read policy is a one-way door in practice, even
  though the Terraform itself is trivially reversible.** Tightening the bucket policy later
  (signed URLs, a CDN, per-object ACLs) is a cheap, ordinary `tofu apply` — but it does nothing to
  un-share a `published_html_url`/`published_pdf_url`/Doc link a human has already copy-pasted
  into Slack/email/a deck. Treat every published link as permanent from the moment it's minted,
  not just from the moment anyone notices it's public; this is a policy/process caveat, not
  something a future code change can retroactively fix.
- **`scope = CLOUDFRONT` WAF web ACLs and CloudFront's own ACM viewer cert MUST be created via the
  us-east-1 API endpoint, full stop — not "us-east-1 by convention," an AWS-enforced requirement
  independent of `var.region`.** `edge_cloudfront.tf` declares an explicit `provider = aws.us_east_1`
  alias for exactly this reason, used by `aws_acm_certificate`/`aws_acm_certificate_validation`
  (`edge_cloudfront.tf`) and `aws_wafv2_web_acl` (`waf.tf`) — even though `var.region` already
  defaults to `"us-east-1"` for this whole stack, that default is override-able, and without the
  alias a future region change would silently try to create these two in the wrong region and fail
  at apply time with an opaque error, not a config-time one.
- **The CloudFront-origin-facing managed prefix list is shared across every AWS customer's
  CloudFront distributions, not just this one — restricting the origin SG to it alone would only
  prove "traffic came from some CloudFront distribution somewhere," never "came from OUR
  distribution."** This is exactly why the secret `X-Origin-Verify` header exists
  (`random_password.origin_verify_secret` in `secrets.tf`, checked by the generated Caddyfile in
  `templates/user-data.sh.tpl`) — the prefix list narrows the network, the header proves identity
  within it. Removing either half (opening the SG wider "just to debug," or letting Caddy skip the
  header check "temporarily") reopens exactly the direct-origin-access gap this whole ticket exists
  to close — don't, even for a quick manual test; use the SSM port-forwarding pattern in
  "Debugging / direct access" instead, which never touches the SG at all.
- **`aws_acm_certificate_validation` genuinely blocks `tofu apply` until ACM reports the
  certificate issued** — even though `dns.tf`'s `aws_route53_record.cert_validation` writes the
  validation record automatically (no manual DNS step anymore, since the `example.com` zone is
  in-account — see "DNS + ACM: fully automated via Route53" above), ACM still needs real time to
  see that record resolve and issue the cert. This will look exactly like a hung apply to anyone
  who doesn't know to expect it; it isn't hung, it's waiting on DNS propagation + ACM's own check
  interval, not a human.
- **Rotating `ORIGIN_VERIFY_SECRET` needs BOTH a `tofu apply` (to change CloudFront's origin
  custom header to the new value) AND the `agents`/`edge` stack to re-render its Caddyfile from the
  new SSM value** (next instance boot, or `tofu apply -replace=aws_instance.app`) — `random_password.
  origin_verify_secret` only regenerates on an explicit `-replace`/taint, it does not rotate on a
  plain `tofu apply` the way you might expect a "secret" to. Until both sides update, CloudFront
  will be sending a header value Caddy doesn't recognize, and every real request will 403 at the
  edge — treat a rotation as a two-step, not a one-step, change.

## Not in scope here (sibling/pre-existing work)

- **Moving `published_assets` behind CloudFront + OAC** (so account-level S3 Block-Public-Access
  can be fully locked) — see "Edge: CloudFront + AWS WAF" → "Follow-up not done here" above for why
  it's deliberately not bundled into the CloudFront/WAF PR that added this section.
- **The agent-brain-mount hold resolved differently than the scoping report's §5 recommendation
  predicted** — not "bake into the image at build," but `cmw-brain-split`'s brain-as-its-own-repo
  clone-on-boot (`HendoCode/masthead`, `app.git.ensure_brain_available`). This
  Terraform provisions exactly what that mechanism needs (`BRAIN_REPO_URL`/`BRAIN_DEPLOY_KEY` in
  SSM, `BRAIN_ROOT=/brain` on the `agents` container) — see "Brain push credential" above for
  generate/install/store, then restart `agents` to pick up a real brain; leave the two placeholder
  vars blank (the params then simply aren't created) and the voice-kit/interview/lessons screens
  stay empty/503, same graceful degradation as local dev with no brain configured.
- Similarly, the `.env.example` `NEXTAUTH_SECRET=` empty-string fallback bug (scoping report §0) is
  already fixed upstream ("Fix MissingSecret on sign-in under the Docker production build") — not a
  concern for this deploy either way, since `NEXTAUTH_SECRET` here is always populated with a real
  generated value, never left empty.
- **Real Anthropic key, connector credentials**: connectors (Google Drive/Slack) are deliberately
  left unprovisioned per the scoping report's decision #5 — they degrade gracefully per-source,
  never crash the app.
