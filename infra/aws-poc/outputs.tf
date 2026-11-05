output "public_ip" {
  description = "The instance's own public IPv4 (no Elastic IP — see README \"EIP removed\"). This is the ORIGIN-facing address — dns.tf's aws_route53_record.origin A-records \"origin.<edge_domain>\" here automatically, NOT edge_domain itself. Changes on instance replacement; the next `tofu apply` rewrites the DNS record to match."
  value       = aws_instance.app.public_ip
}

output "app_url" {
  description = "URL to share with reviewers. Gated by the app's own sign-in (docs/auth.md) behind CloudFront's WAF + ACM-TLS edge (edge_cloudfront.tf) — edge_domain's DNS ALIAS to the CloudFront distribution is written automatically by dns.tf's aws_route53_record.app."
  value       = "https://${var.edge_domain}"
}

output "cloudfront_distribution_domain_name" {
  description = "CloudFront's own d<random>.cloudfront.net hostname. dns.tf's aws_route53_record.app already ALIASes edge_domain to this automatically — surfaced here for console lookups/debugging only, no manual DNS step needed."
  value       = aws_cloudfront_distribution.app.domain_name
}

output "cloudfront_distribution_id" {
  description = "For `aws cloudfront create-invalidation` / console lookups."
  value       = aws_cloudfront_distribution.app.id
}

output "origin_domain_name" {
  description = "The hostname CloudFront's origin config actually connects to — DELIBERATELY different from edge_domain, to avoid a DNS loop. dns.tf's aws_route53_record.origin A-records this to public_ip automatically."
  value       = local.cloudfront_origin_domain
}

output "acm_validation_records" {
  description = "The DNS validation record(s) ACM asked for edge_domain's CloudFront certificate — dns.tf's aws_route53_record.cert_validation already writes these into the account zone automatically. Surfaced here for visibility/debugging only."
  value = [
    for dvo in aws_acm_certificate.cloudfront.domain_validation_options : {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  ]
}

output "instance_id" {
  description = "For `aws ssm start-session --target <id>` (shell access) and port-forwarding (see README)."
  value       = aws_instance.app.id
}

output "ssm_connect_command" {
  description = "Shell access — no SSH key exists for this instance by design."
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.region}"
}

output "web_ecr_repository_url" {
  description = "Push the web/ image here before the first full apply — see README."
  value       = aws_ecr_repository.web.repository_url
}

output "agents_ecr_repository_url" {
  description = "Push the agents/ image here before the first full apply — see README."
  value       = aws_ecr_repository.agents.repository_url
}

output "mongo_data_volume_id" {
  description = "The persistent EBS volume backing on-instance Mongo data. Survives instance replacement; a plain `tofu destroy` will refuse to delete it (prevent_destroy) — see README Teardown."
  value       = aws_ebs_volume.mongo_data.id
}

output "published_assets_bucket" {
  description = "Durable, generally-public bucket for finalized → published outputs (see app/publish/README.md). A plain `tofu destroy` will refuse to delete it (prevent_destroy) — see README Teardown."
  value       = aws_s3_bucket.published_assets.bucket
}

output "published_assets_base_url" {
  description = "Base URL published object keys resolve under — PUBLISHED_ASSETS_BUCKET/PUBLISHED_ASSETS_REGION on the agents container derive this same shape."
  value       = "https://${aws_s3_bucket.published_assets.bucket}.s3.${var.region}.amazonaws.com"
}
