# Only the edge (reverse proxy) port is internet-facing, and even that is no longer open to the
# internet — it's restricted to CloudFront (edge_cloudfront.tf). web/agents/mongo publish no host
# ports at all — the edge container reaches `web` over the internal compose network (see
# templates/docker-compose.prod.yml.tpl). No SSH ingress anywhere: shell access is SSM Session
# Manager only (iam.tf), the cleanest of the "none/SSM-only" choices.
#
# Origin lock (post-compromise hardening — see
# firstmate/data/cmw-architecture/security/vpo-app-hardening-options.md and README "Edge:
# CloudFront + AWS WAF"): the instance was previously compromised via a direct hit on this SG when
# it was open to 0.0.0.0/0. It no longer is. Ingress on var.edge_port is restricted to AWS's
# CloudFront-origin-facing managed prefix list — but that list is shared across EVERY CloudFront
# customer's origins, not just this one, so it alone would only prove "some CloudFront
# distribution somewhere," not "our distribution." The secret custom origin header
# (edge_cloudfront.tf's origin.custom_header, checked by the generated Caddyfile in
# templates/user-data.sh.tpl) closes that gap — anything reaching this SG's allowed IP range
# without the header gets a plain 403 from Caddy, never reaching `web`.
#
# var.edge_https_port is NOT opened here at all: CloudFront terminates the public TLS connection
# (ACM cert, edge_cloudfront.tf) and talks to this origin over plain HTTP only (README "TLS /
# origin-protocol approach") — Caddy no longer does public ACME issuance, so it has no cert to
# serve on 443 in the first place.
data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "app" {
  name_prefix = "cmw-poc-"
  description = "cmw AWS POC: edge proxy port only, ingress-wise, restricted to the CloudFront origin-facing prefix list. No SSH (SSM Session Manager only)."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Edge reverse proxy HTTP - CloudFront only (prefix list), plus the secret X-Origin-Verify header Caddy requires (see edge_cloudfront.tf, templates/user-data.sh.tpl)"
    from_port       = var.edge_port
    to_port         = var.edge_port
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id]
  }

  egress {
    description = "All outbound (ECR/SSM/Docker Hub pulls, package installs, SSM agent)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "cmw-poc"
  }

  lifecycle {
    create_before_destroy = true
  }
}
