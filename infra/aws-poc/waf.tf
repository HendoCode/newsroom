# AWS WAF v2 web ACL for the CloudFront distribution in edge_cloudfront.tf.
#
# Why this exists: the POC instance was compromised via a direct hit on the origin — the security
# group was open to 0.0.0.0/0 on 80/443 with only the app's Google OAuth gate in front, no WAF, no
# rate limiting. See firstmate/data/cmw-architecture/security/vpo-app-hardening-options.md (Option
# 2, "recommended if staying AWS-native"). This web ACL + edge_cloudfront.tf's origin lock in
# security.tf together are the fix: generic exploit/scanner traffic is filtered at the edge before
# it ever reaches the app's own auth gate, and the origin itself is no longer reachable except
# through this edge.
#
# scope = CLOUDFRONT web ACLs MUST be created via the us-east-1 API endpoint regardless of
# var.region — hence provider = aws.us_east_1 (declared in edge_cloudfront.tf, alongside the ACM
# certificate, which has the identical us-east-1-for-CloudFront requirement).
resource "aws_wafv2_web_acl" "cloudfront" {
  provider = aws.us_east_1

  name        = "cmw-poc-cloudfront"
  description = "cmw AWS POC edge WAF: AWS managed rule groups + a per-IP rate limit, scoped to the CloudFront distribution fronting the app."
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # Generic exploit-attempt coverage (SQLi, XSS, known bad request patterns, protocol violations).
  # This is the class of traffic that walked straight through the app's OAuth gate during the
  # compromise this edge is meant to prevent a repeat of.
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "cmw-poc-common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "cmw-poc-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # Blocks requests from IPs on AWS's own reputation list (known scanners/bots/malware C2) —
  # cheap, high-signal, no app-specific tuning needed.
  rule {
    name     = "AWSManagedRulesAmazonIpReputationList"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "cmw-poc-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # Blunt scanning/brute-force per source IP — the pattern that preceded the original compromise.
  # AWS WAF's rate-based rule uses a fixed 5-minute rolling evaluation window by default (no
  # evaluation_window_sec override here — that argument needs a newer aws provider than this
  # stack's `~> 5.0` pin guarantees), which matches the "2000 req / 5 min per IP" ask directly.
  rule {
    name     = "RateLimitPerIp"
    priority = 4

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit_per_5min
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "cmw-poc-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "cmw-poc-web-acl"
    sampled_requests_enabled   = true
  }

  tags = {
    Name = "cmw-poc"
  }
}
