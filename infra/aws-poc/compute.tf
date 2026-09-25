# Pin the AZ explicitly from the chosen subnet (rather than reading it back off aws_instance.app)
# so the persistent Mongo volume has no dependency cycle with the instance it attaches to.
data "aws_subnet" "selected" {
  id = data.aws_subnets.default.ids[0]
}

locals {
  app_dir          = "/opt/cmw-poc"
  mongo_mount_path = "/mnt/cmw-poc-mongo-data"
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnet.selected.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # No key_name: SSH is intentionally not provisioned anywhere (SSM Session Manager only, via the
  # AmazonSSMManagedInstanceCore attachment in iam.tf).
  associate_public_ip_address = true

  # http_put_response_hop_limit MUST be >=2: the app containers (not just the host) need to reach
  # the instance metadata service for their ambient AWS credentials (SECRETS_BACKEND=aws), and a
  # container adds one hop beyond the host itself. The IMDSv2-only default (http_tokens=required)
  # is a security hardening independent of that.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    encrypted   = true
  }

  user_data = templatefile("${path.module}/templates/user-data.sh.tpl", {
    aws_region                = var.region
    ssm_prefix                = var.ssm_prefix
    ecr_registry              = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
    web_image                 = "${aws_ecr_repository.web.repository_url}:${var.web_image_tag}"
    agents_image              = "${aws_ecr_repository.agents.repository_url}:${var.agents_image_tag}"
    edge_port                 = var.edge_port
    origin_verify_header_name = local.origin_verify_header_name
    mongo_volume_id           = aws_ebs_volume.mongo_data.id
    mongo_mount_path          = local.mongo_mount_path
    app_dir                   = local.app_dir
    docker_compose_content = templatefile("${path.module}/templates/docker-compose.prod.yml.tpl", {
      web_image                   = "${aws_ecr_repository.web.repository_url}:${var.web_image_tag}"
      agents_image                = "${aws_ecr_repository.agents.repository_url}:${var.agents_image_tag}"
      ssm_prefix                  = var.ssm_prefix
      aws_region                  = var.region
      edge_port                   = var.edge_port
      mongo_mount_path            = local.mongo_mount_path
      auth_allowed_email_domain   = var.auth_allowed_email_domain
      published_assets_bucket     = aws_s3_bucket.published_assets.bucket
      google_shared_drive_id      = var.google_shared_drive_id
      llm_backend                 = var.llm_backend
      openai_base_url             = var.openai_base_url
      openrouter_default_model_id = var.openrouter_default_model_id
      # Pins NextAuth's OAuth callback base URL to the real edge domain (same value outputs.tf's
      # app_url derives) instead of letting it infer the host from the request — on this bare
      # Next.js standalone server that inference can silently resolve to the container's own bind
      # address, producing a redirect_uri Google refuses at the token-exchange step even though
      # the sign-in button itself appears to work (observed while diagnosing exactly this failure).
      auth_url = "https://${var.edge_domain}"
    })
  })

  tags = {
    Name = "cmw-poc"
  }

  # user_data_replace_on_change = true forces replacement (not in-place attribute update) when
  # user_data changes. Without it, a var like edge_domain (which feeds AUTH_URL) can be recorded
  # as "applied" in state while the live instance still boots with the old value — exactly the
  # silent drift that took the site down. The root volume is disposable; Mongo lives on the
  # separate EBS volume with its own prevent_destroy.
  user_data_replace_on_change = true

  depends_on = [
    aws_iam_role_policy.read_params,
    aws_iam_role_policy_attachment.ssm_core,
    aws_iam_role_policy_attachment.ecr_read,
  ]
}

# Separate, persistent volume for on-instance Mongo data — deliberately NOT the root volume, so it
# outlives instance replacement (AMI change, taint/replace, etc.). `prevent_destroy` means a plain
# `tofu destroy` refuses to touch it; see README "Teardown" for the two supported paths (wipe vs.
# keep the data volume around).
resource "aws_ebs_volume" "mongo_data" {
  availability_zone = data.aws_subnet.selected.availability_zone
  size              = var.mongo_volume_size
  type              = "gp3"
  encrypted         = true

  tags = {
    Name = "cmw-poc-mongo-data"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "mongo_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.mongo_data.id
  instance_id = aws_instance.app.id
  # Nitro instances (t3.medium included) rename this to an /dev/nvme*n1 device inside the guest —
  # user-data resolves the real path via the stable /dev/disk/by-id/...-<volume-id> symlink
  # instead of assuming /dev/sdf (see templates/user-data.sh.tpl).
}
