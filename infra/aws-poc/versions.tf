terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state in S3, with native OpenTofu 1.10+ locking via conditional writes
  # (use_lockfile — no DynamoDB table needed at this OpenTofu version; see
  # infra/aws-poc-state-backend/README.md for how the bucket itself was bootstrapped, deliberately
  # as its own separately-applied stack to avoid a chicken-and-egg dependency on itself).
  # `encrypt = true` requests SSE on write; the bucket also has default SSE-AES256 configured
  # server-side (belt and suspenders) since this state holds generated secret values in plaintext
  # (Terraform's own limitation) — the bucket blocks all public access and requires TLS in
  # transit. See README — "State".
  backend "s3" {
    bucket       = "cmw-aws-poc-tofu-state-<AWS_ACCOUNT_ID>"
    key          = "aws-poc/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
