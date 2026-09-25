provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "content-machine-webapp"
      Environment = "aws-poc"
      ManagedBy   = "opentofu"
    }
  }
}
