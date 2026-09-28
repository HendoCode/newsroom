provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "newsroom"
      Environment = "aws-poc"
      ManagedBy   = "opentofu"
    }
  }
}
