# CloudFront + ACM: the AWS-native edge in front of the app, replacing "Caddy on the open
# internet" as the public-facing TLS terminator. See README "Edge: CloudFront + AWS WAF" for the
# full design (DNS/ACM automation via dns.tf, TLS/origin-protocol decision, apply sequence) and
# firstmate/data/cmw-architecture/security/vpo-app-hardening-options.md for why this exists.
#
# ACM certificates used by a CloudFront distribution's viewer_certificate MUST be requested in
# us-east-1, regardless of var.region (an AWS-wide CloudFront requirement, not a choice made here)
# — same reasoning as the WAF web ACL's scope=CLOUDFRONT requirement in waf.tf. var.region already
# defaults to "us-east-1" for this whole stack, but that default is override-able, so this alias
# pins both resources to the one region CloudFront actually requires rather than silently
# inheriting whatever var.region happens to be.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "content-machine-webapp"
      Environment = "aws-poc"
      ManagedBy   = "opentofu"
    }
  }
}

locals {
  # CloudFront must reach the origin by a hostname DIFFERENT from the public-facing edge_domain —
  # otherwise "edge_domain resolves to CloudFront, and CloudFront's origin is edge_domain" is a DNS
  # loop. This is the origin-facing name; its DNS A record (dns.tf's aws_route53_record.origin)
  # points at the same EIP the instance has always used.
  cloudfront_origin_domain = "origin.${var.edge_domain}"

  # The shared secret CloudFront injects as a custom origin header and Caddy checks for on every
  # request (templates/user-data.sh.tpl's generated Caddyfile) — the second half of the origin
  # lock, needed because the CloudFront-origin-facing prefix list (security.tf) is shared across
  # every CloudFront distribution on AWS, not just this one. Defined once here so the exact header
  # name can never drift between this file and the Caddyfile it's threaded into.
  origin_verify_header_name = "X-Origin-Verify"
}

# DNS-validated fully in Terraform: example.com's zone is in-account (dns.tf's data source), so
# aws_route53_record.cert_validation writes the CNAME(s) ACM asks for automatically — no manual
# DNS step. aws_acm_certificate_validation still blocks until ACM actually reports the cert issued,
# which in practice means it waits for that record to propagate; that's expected, not a hang.
resource "aws_acm_certificate" "cloudfront" {
  provider = aws.us_east_1

  domain_name       = var.edge_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "cloudfront" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.cloudfront.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# Forwards every viewer header (incl. Host — see README for why that matters given AUTH_URL is
# already pinned), cookie, and query string to the origin unmodified, with caching fully disabled.
# Both are AWS managed policies, looked up by name rather than hardcoding their (stable but
# easy-to-mistype) ids.
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "app" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "cmw-poc: WAF + ACM-TLS edge in front of the origin instance (see infra/aws-poc/README.md)"
  price_class     = var.cloudfront_price_class
  aliases         = [var.edge_domain]
  web_acl_id      = aws_wafv2_web_acl.cloudfront.arn

  origin {
    domain_name = local.cloudfront_origin_domain
    origin_id   = "cmw-poc-app"

    # http-only, not match-viewer/https-only: this is the "CloudFront -> origin over plain HTTP"
    # decision (README "TLS / origin-protocol approach") — Caddy no longer needs (or has) a public
    # TLS cert once the SG stops accepting inbound traffic from anywhere but CloudFront. https_port
    # is still a required schema field even though origin_protocol_policy never uses it.
    custom_origin_config {
      http_port              = var.edge_port
      https_port             = var.edge_https_port
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = local.origin_verify_header_name
      value = random_password.origin_verify_secret.result
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "cmw-poc-app"

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # This is a dynamic, authenticated app (Google OAuth sign-in, session cookies) — never a static
    # site. Caching must stay off and every viewer header/cookie/query string must reach the origin
    # unmodified, or auth cookies and the OAuth redirect round-trip silently break.
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.cloudfront.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name = "cmw-poc"
  }
}
