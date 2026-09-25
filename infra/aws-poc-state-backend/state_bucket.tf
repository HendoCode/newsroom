# The remote backend for infra/aws-poc's OpenTofu state. Locking uses OpenTofu 1.10+'s native S3
# conditional-write locking (`use_lockfile = true`, set in infra/aws-poc/versions.tf's backend
# block) instead of a separate DynamoDB table — the pinned OpenTofu version (see `tofu version` /
# infra/aws-poc/.terraform.lock.hcl) is well past the 1.10 introduction, so no DynamoDB table is
# created here.

resource "aws_s3_bucket" "tofu_state" {
  bucket = "cmw-aws-poc-tofu-state-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tofu_state" {
  bucket = aws_s3_bucket.tofu_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "tofu_state" {
  bucket = aws_s3_bucket.tofu_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tofu_state" {
  bucket = aws_s3_bucket.tofu_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# infra/aws-poc's state holds every secret value in plaintext (see infra/aws-poc/versions.tf) — deny
# any request made without TLS so it can never be read or written over an unencrypted connection.
resource "aws_s3_bucket_policy" "tofu_state_require_tls" {
  bucket = aws_s3_bucket.tofu_state.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.tofu_state.arn,
          "${aws_s3_bucket.tofu_state.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}
