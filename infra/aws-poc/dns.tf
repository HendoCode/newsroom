# DNS placeholder for the legacy AWS POC infra.
#
# The live Content Machine DNS posture is Cloudflare-managed OpenTofu in the separate
# `dns-infra` project (`hendocode.com`). This stack previously looked up a Route53 zone
# for ACM validation; the zone ID below is replaced with a clearly-fake placeholder.
# Only this app's own record sets were written into the looked-up zone.
#
# See the `dns-infra` project for the real-world design: Cloudflare zone + GitHub Pages
# apex records, with `tofu plan` gating and no secrets in code.
data "aws_route53_zone" "app" {
  zone_id = "<ROUTE53_ZONE_ID>" # placeholder; live DNS lives in dns-infra (hendocode.com)
}

# var.edge_domain is the FULL hostname of ONE environment — prod is the apex "example.com" (this
# stack); a future environment (e.g. "beta.example.com") is a separate instance of this same stack
# with its own edge_domain, its own CloudFront distribution/cert, and its own records written into
# this SAME shared zone. So every record/cert below derives its name from var.edge_domain — never
# hardcode "example.com" here — while the zone lookup above stays fixed to the root zone regardless.

# DNS-validates aws_acm_certificate.cloudfront (edge_cloudfront.tf) by writing the validation
# CNAME(s) ACM asks for directly into the account zone — replaces the old out-of-band "create this
# CNAME by hand" step now that DNS is in-account. allow_overwrite tolerates re-running this after a
# cert replacement (create_before_destroy) proposing the same validation record again.
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cloudfront.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  zone_id         = data.aws_route53_zone.app.zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
}

# The public-facing record end users/reviewers resolve — an ALIAS (not a CNAME, so this works even
# at the zone apex) to the CloudFront distribution. Named for var.edge_domain, so a future
# beta.example.com instance of this stack produces the correct subdomain record with no code change.
resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.app.zone_id
  name    = var.edge_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.app.domain_name
    zone_id                = aws_cloudfront_distribution.app.hosted_zone_id
    evaluate_target_health = false
  }
}

# The origin-facing record CloudFront's custom_origin_config actually connects to
# (local.cloudfront_origin_domain, edge_cloudfront.tf) — a plain A record to the instance's own
# public IP, deliberately a DIFFERENT hostname from var.edge_domain to avoid the DNS loop that name
# would otherwise create (see edge_cloudfront.tf's locals comment). No Elastic IP backs this: the
# instance gets a fresh public IPv4 on every launch (associate_public_ip_address in compute.tf),
# and this record is rewritten to match on every `tofu apply` — see README "EIP removed" for what
# that trades away (an apply-less IP change, e.g. a manual stop/start, now leaves this record
# pointing at a dead address until the next apply) and the 300s TTL's role in that.
resource "aws_route53_record" "origin" {
  zone_id = data.aws_route53_zone.app.zone_id
  name    = local.cloudfront_origin_domain
  type    = "A"
  ttl     = 300
  records = [aws_instance.app.public_ip]
}
