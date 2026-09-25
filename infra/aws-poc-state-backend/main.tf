provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "content-machine-webapp"
      Environment = "aws-poc"
      ManagedBy   = "opentofu"
      Purpose     = "tofu-state-backend-bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}
