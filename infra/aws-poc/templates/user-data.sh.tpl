#!/bin/bash
# Rendered by compute.tf (aws_instance.app.user_data) — runs once on first boot (Amazon Linux
# 2023 / cloud-init). Logs to /var/log/cmw-poc-user-data.log; tail that over an SSM session if
# something looks wrong (see README "Sharp edges" for the two known first-boot failure modes:
# image-not-pushed-yet, and IAM propagation delay).
set -euo pipefail
exec > >(tee -a /var/log/cmw-poc-user-data.log) 2>&1
echo "cmw-poc: user-data starting $(date -u +%FT%TZ)"

REGION="${aws_region}"
SSM_PREFIX="${ssm_prefix}"
ECR_REGISTRY="${ecr_registry}"
WEB_IMAGE="${web_image}"
AGENTS_IMAGE="${agents_image}"
EDGE_PORT="${edge_port}"
ORIGIN_VERIFY_HEADER_NAME="${origin_verify_header_name}"
MONGO_VOLUME_ID="${mongo_volume_id}"
MONGO_MOUNT_PATH="${mongo_mount_path}"
APP_DIR="${app_dir}"
COMPOSE_PLUGIN_VERSION="v2.29.7"

# --- Packages: Docker + the Compose v2 CLI plugin (AL2023's own repos don't ship the plugin) ----
dnf update -y
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user || true

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL \
  "https://github.com/docker/compose/releases/download/$COMPOSE_PLUGIN_VERSION/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# --- Mount the persistent Mongo data volume ------------------------------------------------------
# Nitro-based instance types (t3.medium included) do NOT honor the `/dev/sdf` device name given at
# attach time — the kernel exposes it as an NVMe device instead (typically /dev/nvme1n1, but the
# exact number isn't guaranteed). The one stable handle is the /dev/disk/by-id symlink keyed on the
# EBS volume ID itself, which AWS's NVMe driver always creates. Resolve that instead of guessing.
MONGO_VOLUME_ID_NO_DASH=$(echo "$MONGO_VOLUME_ID" | tr -d '-')
DEVICE=""
for _ in $(seq 1 30); do
  CANDIDATE="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_$MONGO_VOLUME_ID_NO_DASH"
  if [ -e "$CANDIDATE" ]; then
    DEVICE=$(readlink -f "$CANDIDATE")
    break
  fi
  sleep 2
done
if [ -z "$DEVICE" ]; then
  echo "cmw-poc: FATAL - mongo EBS volume $MONGO_VOLUME_ID never appeared as a block device" >&2
  exit 1
fi
echo "cmw-poc: mongo data volume resolved to $DEVICE"

if ! blkid "$DEVICE" >/dev/null 2>&1; then
  echo "cmw-poc: no filesystem on $DEVICE yet - formatting as xfs (first boot only)"
  mkfs -t xfs "$DEVICE"
fi

mkdir -p "$MONGO_MOUNT_PATH"
mount "$DEVICE" "$MONGO_MOUNT_PATH"
VOL_UUID=$(blkid -s UUID -o value "$DEVICE")
if ! grep -q "$VOL_UUID" /etc/fstab; then
  echo "UUID=$VOL_UUID $MONGO_MOUNT_PATH xfs defaults,nofail 0 2" >>/etc/fstab
fi

mkdir -p "$MONGO_MOUNT_PATH/db"
chown -R 999:999 "$MONGO_MOUNT_PATH/db" # mongo:7's image runs as uid 999

# --- Fetch the handful of secrets user-data itself needs -----------------------------------------
# Everything else (ANTHROPIC_API_KEY, MONGO_URL, BRAIN_REPO_URL, BRAIN_DEPLOY_KEY) is resolved
# live, per-request, by the `agents` container's own secrets shim (SECRETS_BACKEND=aws) — never
# fetched or written to disk here. These are needed here because Mongo and the edge proxy have no
# app code / no secrets-shim integration to do that resolution themselves, and NEXTAUTH_SECRET/
# GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are pre-materialized for `web` instead of resolved live via
# SECRETS_BACKEND=aws (see README "Why web doesn't use SECRETS_BACKEND=aws" — an Edge-runtime
# limitation, not specific to Google). ORIGIN_VERIFY_SECRET is the CloudFront origin-lock secret
# (README "Edge: CloudFront + AWS WAF") — baked literally into the generated Caddyfile below, never
# passed to `agents`/`web`.
get_param() {
  aws ssm get-parameter --name "$SSM_PREFIX$1" --with-decryption --region "$REGION" \
    --query 'Parameter.Value' --output text
}

# Tolerates the parameter being absent entirely (not just blank) — GOOGLE_CLIENT_ID/SECRET are
# populated out-of-band and may not exist yet on a fresh apply; a missing param degrades to the
# same empty string as a blank one, which web/auth.ts treats as "Google not configured".
get_param_optional() {
  aws ssm get-parameter --name "$SSM_PREFIX$1" --with-decryption --region "$REGION" \
    --query 'Parameter.Value' --output text 2>/dev/null || true
}

MONGO_ROOT_USERNAME=$(get_param MONGO_ROOT_USERNAME)
MONGO_ROOT_PASSWORD=$(get_param MONGO_ROOT_PASSWORD)
NEXTAUTH_SECRET_VALUE=$(get_param NEXTAUTH_SECRET)
ORIGIN_VERIFY_SECRET_VALUE=$(get_param ORIGIN_VERIFY_SECRET)
GOOGLE_CLIENT_ID_VALUE=$(get_param_optional GOOGLE_CLIENT_ID)
GOOGLE_CLIENT_SECRET_VALUE=$(get_param_optional GOOGLE_CLIENT_SECRET)

# --- Pull the pre-built images from ECR (no Git/GitHub credential ever touches this box) ---------
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$WEB_IMAGE"
docker pull "$AGENTS_IMAGE"

# --- Assemble the app directory ------------------------------------------------------------------
mkdir -p "$APP_DIR"
chmod 700 "$APP_DIR"

cat >"$APP_DIR/Caddyfile" <<EOF
{
	admin off
	# CloudFront (edge_cloudfront.tf) now terminates the public TLS connection with an ACM cert
	# and forwards here over plain HTTP — Caddy has no domain name to request a Let's Encrypt
	# cert for anymore, and auto_https would otherwise try (and fail, since the SG below no
	# longer accepts inbound traffic from the open internet at all) the moment a future edit
	# gives a site block a hostname instead of a bare port. off, explicitly, as insurance.
	auto_https off
}

# Port-only address (not a domain) — this is the origin CloudFront's custom_origin_config points
# at, never the public-facing hostname directly. The X-Origin-Verify check is the second half of
# the origin lock (security.tf restricts inbound to CloudFront's own prefix list, which is shared
# across every CloudFront customer — this header is what proves a request is really from THIS
# distribution): anything missing it gets a plain 403, never reaching \`web\`.
:$EDGE_PORT {
	@missing_origin_secret not header $ORIGIN_VERIFY_HEADER_NAME $ORIGIN_VERIFY_SECRET_VALUE
	respond @missing_origin_secret 403

	reverse_proxy web:3000
}
EOF

cat >"$APP_DIR/docker-compose.yml" <<'COMPOSE_EOF'
${docker_compose_content}
COMPOSE_EOF

cat >"$APP_DIR/.env" <<EOF
MONGO_ROOT_USERNAME=$MONGO_ROOT_USERNAME
MONGO_ROOT_PASSWORD=$MONGO_ROOT_PASSWORD
NEXTAUTH_SECRET=$NEXTAUTH_SECRET_VALUE
GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID_VALUE
GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET_VALUE
EOF
chmod 600 "$APP_DIR/.env"

# --- Bring the stack up ----------------------------------------------------------------------
cd "$APP_DIR"
docker compose --env-file .env up -d

echo "cmw-poc: user-data complete $(date -u +%FT%TZ)"
