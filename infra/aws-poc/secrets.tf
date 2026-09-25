# SSM Parameter Store (SecureString), not Secrets Manager — standard tier is free, which matters
# for "cheap" (scoping report §3). Every value the app actually reads through its secrets shim
# (agents/app/secrets/, web/lib/secrets/ — SECRETS_BACKEND=aws) lives under var.ssm_prefix with
# the EXACT name the shim requests (f"{prefix}{NAME}"): ANTHROPIC_API_KEY, MONGO_URL,
# BRAIN_REPO_URL, BRAIN_DEPLOY_KEY (the brain-as-clone bootstrap credential names — see
# agents/app/config.py's brain_repo_url/brain_deploy_key properties; BRAIN_DEPLOY_KEY holds an SSH
# deploy-key private key, repo-scoped read-write, the least-privilege machine-push credential —
# see agents/app/git/ssh_auth.py and this directory's README "Brain push credential" section for
# generate/install/store), and GOOGLE_OAUTH_CLIENT_ID/_CLIENT_SECRET/_REFRESH_TOKEN (the Drive/Docs
# grant — agents/app/config.py's google_oauth_* properties; a SEPARATE credential from
# GOOGLE_CLIENT_ID/_SECRET below, which serve `web`'s NextAuth sign-in, never these). A few more
# params live alongside them under the same prefix for things the shim does NOT cover — Mongo's
# own root credentials, and (since the CloudFront edge lock, edge_cloudfront.tf) ORIGIN_VERIFY_SECRET
# — fetched directly by user-data at boot (see templates/user-data.sh.tpl); sharing one prefix
# means one IAM statement (iam.tf) covers every read site.
#
# Real-secret placeholders (Anthropic key, brain repo URL/push token, the Google OAuth grant) are
# written once with a placeholder value and then ignored by every later apply
# (`lifecycle { ignore_changes = [value] }`) so the captain can safely overwrite them via
# `aws ssm put-parameter --overwrite` without a subsequent `tofu apply` reverting them back to the
# placeholder. Never pass a real secret value into this module — not as a variable, not on the
# CLI, not in a committed .tfvars.

locals {
  mongo_root_username = "cmw_app"
  mongo_url           = "mongodb://${local.mongo_root_username}:${random_password.mongo_root_password.result}@mongo:27017/content_machine?authSource=admin"
}

resource "random_password" "nextauth_secret" {
  length  = 48
  special = false # keep alnum-only: this value transits a bash heredoc + a compose .env file
}

resource "random_password" "mongo_root_password" {
  length  = 32
  special = false
}

# The origin-lock secret (README "Origin lock: prefix list + secret header") — CloudFront injects
# this as a custom origin header (edge_cloudfront.tf's origin.custom_header) on every request it
# forwards, and the generated Caddyfile (templates/user-data.sh.tpl) rejects anything missing it.
# Terraform-generated rather than a captain-populated placeholder: nothing outside this stack ever
# needs to know the value, unlike ANTHROPIC_API_KEY.
resource "random_password" "origin_verify_secret" {
  length  = 40
  special = false # transits a bash heredoc into the generated Caddyfile — keep alnum-only
}

# --- Resolved by the app's own secrets shim at runtime (SECRETS_BACKEND=aws) ------------------

resource "aws_ssm_parameter" "anthropic_api_key" {
  name        = "${var.ssm_prefix}ANTHROPIC_API_KEY"
  description = "Real value populated out-of-band by the captain — this apply only reserves the parameter."
  type        = "SecureString"
  value       = var.anthropic_api_key_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "mongo_url" {
  name  = "${var.ssm_prefix}MONGO_URL"
  type  = "SecureString"
  value = local.mongo_url
}

# SSM rejects empty-string parameter values, and both placeholders default to "" (unlike the
# Anthropic key's non-empty placeholder above) — so these two are created only when a real value
# is supplied. A missing parameter degrades exactly like a blank one: agents/app/config.py's
# _secret() catches SecretNotFoundError and returns "", and app.git.ensure_brain_available no-ops
# on an empty brain_repo_url. Populate via `aws ssm put-parameter` out-of-band, or re-apply with a
# non-blank *_placeholder var, to create the parameter.
resource "aws_ssm_parameter" "brain_repo_url" {
  count = var.brain_repo_url_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}BRAIN_REPO_URL"
  description = "Populate in SSM to have the agents container clone HendoCode/content-machine-brain into BRAIN_ROOT on boot (app.git.ensure_brain_available). Left blank, the brain-dependent screens stay empty/503 — the same graceful degradation as today."
  type        = "SecureString"
  value       = var.brain_repo_url_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "brain_deploy_key" {
  count = var.brain_deploy_key_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}BRAIN_DEPLOY_KEY"
  description = "SSH deploy-key PRIVATE key (ed25519, repo-scoped, read-write — see README 'Brain push credential') for authenticated clone/pull/push against BRAIN_REPO_URL, since the instance has no ambient SSH credential. Populate alongside BRAIN_REPO_URL. The matching public key must be installed on HendoCode/content-machine-brain (Settings -> Deploy keys -> Allow write access) before this takes effect."
  type        = "SecureString"
  value       = var.brain_deploy_key_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

# Google Docs/Drive OAuth grant for `agents` (agents/app/config.py: google_oauth_client_id/
# _client_secret/_refresh_token, resolved live via the secrets shim exactly like BRAIN_REPO_URL/
# BRAIN_DEPLOY_KEY above — never as a container env var, so a rotated refresh token takes effect
# on the next secrets-cache TTL with no redeploy). This is a SEPARATE grant from GOOGLE_CLIENT_ID/
# GOOGLE_CLIENT_SECRET below, which serve `web`'s NextAuth sign-in — never conflate the two. Same
# SSM-rejects-empty-string reasoning as the brain params: all three are created only when their
# placeholder var is non-blank, so the default blank leaves the parameters absent entirely and the
# Drive connector / finalize / review Google Docs export stay degraded exactly as they are today
# (see agents/app/connectors/README.md and agents/app/render/README.md). Populate all three in SSM
# the same way as the Anthropic key to enable them; the grant needs both the `drive.readonly` and
# `drive.file` scopes (connector reads + the Docs export's writes/comments).
resource "aws_ssm_parameter" "google_oauth_client_id" {
  count = var.google_oauth_client_id_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}GOOGLE_OAUTH_CLIENT_ID"
  description = "Google OAuth 2.0 client id for the Drive connector + Google Docs export grant (see agents/app/connectors/README.md). Populate in SSM out-of-band, never here."
  type        = "SecureString"
  value       = var.google_oauth_client_id_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "google_oauth_client_secret" {
  count = var.google_oauth_client_secret_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}GOOGLE_OAUTH_CLIENT_SECRET"
  description = "Google OAuth 2.0 client secret paired with GOOGLE_OAUTH_CLIENT_ID. Populate in SSM out-of-band, never here."
  type        = "SecureString"
  value       = var.google_oauth_client_secret_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "google_oauth_refresh_token" {
  count = var.google_oauth_refresh_token_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}GOOGLE_OAUTH_REFRESH_TOKEN"
  description = "Offline refresh token from the one-time OAuth consent (scoped to both drive.readonly and drive.file). Populate in SSM out-of-band, never here; a later rotation is another put-parameter --overwrite, no tofu apply or redeploy needed."
  type        = "SecureString"
  value       = var.google_oauth_refresh_token_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

# OpenAI API key (agents/app/secrets shim: OPENAI_API_KEY) — used when LLM_BACKEND=openai.
# Blank by default; the openai backend degrades to an unconfigured provider (same graceful
# degradation as brain_repo_url above). Populate in SSM out-of-band to enable.
resource "aws_ssm_parameter" "openai_api_key" {
  count = var.openai_api_key_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}OPENAI_API_KEY"
  description = "OpenAI API key for the gpt-5.6-terra model (LLM_BACKEND=openai). Populate in SSM out-of-band to enable."
  type        = "SecureString"
  value       = var.openai_api_key_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

# Slack bot token (agents/app/secrets shim: SLACK_BOT_TOKEN) — used by the Slack connector
# for reading channel history. Blank by default; the Slack connector raises a ConnectorError
# when used without a token (same graceful degradation as the other optional credentials above).
resource "aws_ssm_parameter" "slack_bot_token" {
  count = var.slack_bot_token_placeholder != "" ? 1 : 0

  name        = "${var.ssm_prefix}SLACK_BOT_TOKEN"
  description = "Slack bot token (scopes: channels:history, channels:read, groups:history) for the Slack connector (agents/app/connectors/slack.py). Populate in SSM out-of-band to enable."
  type        = "SecureString"
  value       = var.slack_bot_token_placeholder

  lifecycle {
    ignore_changes = [value]
  }
}

# --- Fetched directly by user-data at boot (not shim-covered: Mongo and the edge proxy have no
# app code / no secrets-shim integration) -------------------------------------------------------

resource "aws_ssm_parameter" "mongo_root_username" {
  name  = "${var.ssm_prefix}MONGO_ROOT_USERNAME"
  type  = "String"
  value = local.mongo_root_username
}

resource "aws_ssm_parameter" "mongo_root_password" {
  name  = "${var.ssm_prefix}MONGO_ROOT_PASSWORD"
  type  = "SecureString"
  value = random_password.mongo_root_password.result
}

# NEXTAUTH_SECRET is a shim-covered name (web/auth.ts), but is deliberately fetched by user-data
# and pre-materialized as a literal env var for the `web` container instead of resolved live via
# SECRETS_BACKEND=aws — see README "Why web doesn't use SECRETS_BACKEND=aws" for the Edge-runtime
# reason (web/AGENTS.md's own documented sharp edge on this exact point).
resource "aws_ssm_parameter" "nextauth_secret" {
  name  = "${var.ssm_prefix}NEXTAUTH_SECRET"
  type  = "SecureString"
  value = random_password.nextauth_secret.result
}

# Fetched by user-data the same way, and baked literally into the generated Caddyfile (never
# passed to `agents`/`web` — this is edge-only, checked by Caddy before anything reaches the app).
resource "aws_ssm_parameter" "origin_verify_secret" {
  name  = "${var.ssm_prefix}ORIGIN_VERIFY_SECRET"
  type  = "SecureString"
  value = random_password.origin_verify_secret.result
}
