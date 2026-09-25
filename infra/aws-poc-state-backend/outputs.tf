output "bucket" {
  description = "S3 bucket name to reference from infra/aws-poc's backend \"s3\" block."
  value       = aws_s3_bucket.tofu_state.bucket
}

output "region" {
  description = "Region the bucket was created in — must match infra/aws-poc's backend \"s3\" block."
  value       = var.region
}
