provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "newsroom"
      Environment = "aws-poc"
      ManagedBy   = "opentofu"
      Purpose     = "tofu-state-backend-bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}
