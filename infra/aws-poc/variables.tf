# See README.md for the full rationale behind each default. Every value here is safe to apply
# as-is except the two *_placeholder secrets, which the captain must overwrite in SSM out-of-band
# after the first apply (see README — "Populating the real secrets").

variable "region" {
  description = "AWS region for the POC. Trivial to change; no real trade-off (scoping report §0)."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type. t3.medium (2 vCPU/4 GiB) recommended: room for Next.js + FastAPI + Mongo + headless Chromium colocated. Drop to t3.small only if PDF finalize can stay degraded."
  type        = string
  default     = "t3.medium"
}

variable "allowed_cidr_blocks" {
  description = "SUPERSEDED by the CloudFront origin lock (security.tf's aws_ec2_managed_prefix_list.cloudfront_origin_facing) — no longer used by any ingress rule. Kept declared only so an existing terraform.tfvars that still sets it doesn't hard-error on plan. Originally: CIDR blocks allowed to reach the edge proxy port, defaulting fully open (0.0.0.0/0) because the app's own sign-in was judged the real access gate — that judgment is exactly what the post-compromise hardening in README \"Edge: CloudFront + AWS WAF\" revisited."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "edge_port" {
  description = "HTTP port the edge reverse proxy (Caddy) listens on. Since the CloudFront origin lock (security.tf, edge_cloudfront.tf), this is reachable ONLY from CloudFront's origin-facing prefix list, never the public internet directly — CloudFront terminates the public TLS connection and forwards to this port over plain HTTP."
  type        = number
  default     = 80
}

variable "edge_https_port" {
  description = "No longer opened on the security group (Caddy no longer serves public TLS — see README \"TLS / origin-protocol approach\"). Still consumed by edge_cloudfront.tf's custom_origin_config.https_port, a field the AWS provider's CloudFront origin schema requires even though origin_protocol_policy=\"http-only\" means it's never actually connected to."
  type        = number
  default     = 443
}

variable "edge_domain" {
  description = "Public DNS name end users/reviewers hit — the FULL hostname of ONE environment. Prod is the apex \"example.com\" (this stack's default); a future environment (e.g. \"beta.example.com\") is a separate instance of this same stack with its own edge_domain, its own CloudFront distribution/cert, and its own records in the SAME shared account zone. dns.tf's data \"aws_route53_zone\" \"app\" (looked up fixed on the root example.com zone, owned by the separate vpo-aws-account-baseline project — never this domain var) automatically writes this domain's ALIAS + ACM DNS-validation + origin A records — no manual DNS step. See README \"Edge: CloudFront + AWS WAF\". The EIP sits behind a separate, origin-facing hostname (local.cloudfront_origin_domain, \"origin.<this>\")."
  type        = string
  default     = "example.com"
}

variable "acme_email" {
  description = "UNUSED since the CloudFront edge lock — Caddy no longer performs public ACME issuance at all (CloudFront + ACM terminates public TLS instead; see README \"TLS / origin-protocol approach\"). Kept declared only so an existing terraform.tfvars that still sets it doesn't hard-error on plan."
  type        = string
  default     = ""
}

variable "auth_allowed_email_domain" {
  description = "Email domain Google sign-in is restricted to (web/auth.ts AUTH_ALLOWED_EMAIL_DOMAIN, docs/auth.md). Not a secret — just which Workspace domain is allowed. The actual GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET creds are populated out-of-band in SSM (see secrets.tf), not managed here."
  type        = string
  default     = "example.com"
}

variable "ssm_prefix" {
  description = "SSM Parameter Store path prefix. MUST match agents/app/secrets (SECRETS_AWS_SSM_PREFIX, default \"/newsroom/\") and web/lib/secrets — the app's secrets shim reads f\"{prefix}{NAME}\" verbatim, so changing this without also setting SECRETS_AWS_SSM_PREFIX on both containers will break secret resolution."
  type        = string
  default     = "/newsroom/"

  validation {
    condition     = can(regex("^/.*/$", var.ssm_prefix))
    error_message = "ssm_prefix must start and end with \"/\", e.g. \"/newsroom/\"."
  }
}

variable "root_volume_size" {
  description = "Root EBS volume size (GB) — OS + Docker images/layers, not Mongo data (that's the separate persistent volume below)."
  type        = number
  default     = 30
}

variable "mongo_volume_size" {
  description = "Size (GB) of the separate, persistent EBS volume backing on-instance Mongo data."
  type        = number
  default     = 20
}

variable "web_image_tag" {
  description = "Tag of the web/ image already pushed to the Terraform-managed ECR repo (see README — build/push must happen before the instance can boot successfully)."
  type        = string
  default     = "latest"
}

variable "agents_image_tag" {
  description = "Tag of the agents/ image already pushed to the Terraform-managed ECR repo."
  type        = string
  default     = "latest"
}

# --- Real-secret placeholders. Terraform creates the SSM parameter with this placeholder value on
# first apply, then (via `lifecycle { ignore_changes = [value] }` on the parameter resource itself)
# never touches it again — so the captain can safely overwrite it via `aws ssm put-parameter
# --overwrite` without a later `tofu apply` reverting it back to the placeholder. -------------

variable "anthropic_api_key_placeholder" {
  description = "Placeholder only. The captain populates the real Anthropic key directly in SSM after apply — never pass a real value here or on the CLI (it would land in shell history and .tfstate any earlier than necessary)."
  type        = string
  default     = "REPLACE_ME_VIA_SSM"
  sensitive   = true
}

variable "brain_repo_url_placeholder" {
  description = "Git clone URL for HendoCode/masthead (agents/app/secrets shim: BRAIN_REPO_URL). Blank by default — the agents container then behaves exactly like local dev with no brain configured (brain-dependent screens stay empty/503). Populate in SSM the same way as the Anthropic key to enable it."
  type        = string
  default     = ""
  sensitive   = true
}

variable "brain_deploy_key_placeholder" {
  description = "SSH deploy-key PRIVATE key (ed25519, repo-scoped read-write — least-privilege machine-push credential) for authenticated clone/pull/push against brain_repo_url_placeholder (agents/app/secrets shim: BRAIN_DEPLOY_KEY) — the instance has no ambient SSH credential. Populate in SSM alongside BRAIN_REPO_URL; see README 'Brain push credential' for generate/install/store steps."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_oauth_client_id_placeholder" {
  description = "Google OAuth 2.0 client id for the Drive/Docs grant (agents/app/secrets shim: GOOGLE_OAUTH_CLIENT_ID) — the server-side incremental-OAuth credential the Drive connector and the finalize/review Google Docs export both read (see agents/app/connectors/README.md). Blank by default — the parameter then simply isn't created and those features stay degraded/503, same graceful degradation as brain_repo_url_placeholder above. Populate in SSM the same way as the Anthropic key to enable it — never here."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_oauth_client_secret_placeholder" {
  description = "Google OAuth 2.0 client secret paired with google_oauth_client_id_placeholder (agents/app/secrets shim: GOOGLE_OAUTH_CLIENT_SECRET). Same blank-by-default, populate-in-SSM-only convention."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_oauth_refresh_token_placeholder" {
  description = "Offline refresh token from the one-time OAuth consent, scoped to both drive.readonly and drive.file (agents/app/secrets shim: GOOGLE_OAUTH_REFRESH_TOKEN) — see agents/app/connectors/README.md for the consent flow. Same blank-by-default, populate-in-SSM-only convention. A rotated token is written the same way (put-parameter --overwrite) and takes effect on the next secrets-cache TTL with no redeploy."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key_placeholder" {
  description = "OpenAI API key for the gpt-5.6-terra model (agents/app/secrets shim: OPENAI_API_KEY) — used when LLM_BACKEND=openai. Blank by default; the parameter isn't created (same optional/blank convention as brain_repo_url_placeholder above) and the openai backend stays degraded. Populate in SSM the same way as the Anthropic key to enable."
  type        = string
  default     = ""
  sensitive   = true
}

variable "slack_bot_token_placeholder" {
  description = "Slack bot token for the Slack connector (agents/app/secrets shim: SLACK_BOT_TOKEN) — scopes: channels:history, channels:read, groups:history. Blank by default; the parameter isn't created and the Slack connector raises a ConnectorError when used without a token. Populate in SSM the same way as the Anthropic key to enable."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_shared_drive_id" {
  description = "Id of the pre-existing Google Shared Drive that per-piece Drive folders (agents/app/drive/README.md) are created under — GOOGLE_SHARED_DRIVE_ID on the agents container. A plain resource identifier, not a secret (same treatment as published_assets_bucket above) — the Shared Drive itself and the Google account behind the OAuth grant above being a member of it are provisioned out-of-band, never by this Terraform. Blank degrades exactly like an unset PUBLISHED_ASSETS_BUCKET: Docs land loose at the Drive root, no folder pointers are ever written onto a Piece."
  type        = string
  default     = "0AORnWG-55S4rUk9PVA"
}

# --- LLM backend (agents/app/config.py) — plain configuration, NOT secrets ----------------
# "bedrock" (default), "openai", "openrouter", "anthropic". "openrouter" is the OpenAI-compatible
# path pointed at OpenRouter: OPENAI_API_KEY resolves through the SSM secrets shim exactly like
# the other provider keys, OPENAI_BASE_URL is optional (blank → the https://openrouter.ai/api/v1
# default applies for this backend), OPENROUTER_DEFAULT_MODEL_ID is the step-tier model slug.
variable "llm_backend" {
  description = "LLM_BACKEND on the agents container (agents/app/config.py). bedrock | openai | openrouter | anthropic. "
  type        = string
  default     = "bedrock"
}

variable "openai_base_url" {
  description = "OPENAI_BASE_URL on the agents container — explicit endpoint override for the openai/openrouter backends. Blank: openai → the openai SDK default, openrouter → https://openrouter.ai/api/v1. Not a secret."
  type        = string
  default     = ""
}

variable "openrouter_default_model_id" {
  description = "OPENROUTER_DEFAULT_MODEL_ID on the agents container — the model slug the step-tier map routes to when llm_backend=openrouter. Keep in lockstep with the pricing entry in agents/app/llm/pricing.py or the cost readout shows 0.0. Not a secret."
  type        = string
  default     = "z-ai/glm-5"
}

# --- CloudFront + WAF edge (edge_cloudfront.tf, waf.tf) — see README "Edge: CloudFront + AWS WAF" ---

variable "waf_rate_limit_per_5min" {
  description = "Per-IP request ceiling for the WAF rate-based rule (waf.tf) over its ~5-minute rolling evaluation window, before that IP starts getting blocked. 2000 is the hardening-brief default — tune down if scanning/brute-force traffic is still getting through under it, or up if real reviewer traffic is legitimately bursty enough to trip it."
  type        = number
  default     = 2000
}

variable "cloudfront_price_class" {
  description = "CloudFront price class (cost/edge-location-coverage trade-off). PriceClass_100 (US/Canada/Europe only) is cheapest and sufficient for a POC with no global audience; widen to PriceClass_All only if reviewers outside those regions report slow load times."
  type        = string
  default     = "PriceClass_100"
}
