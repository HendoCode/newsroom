terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Local state, deliberately. This tiny stack creates the S3 bucket that infra/aws-poc's OWN
  # state now lives in (see infra/aws-poc/versions.tf's backend "s3" block) — storing this
  # bootstrap stack's state in that same bucket would be a chicken-and-egg trap. One bucket,
  # rarely touched after creation; local state (never committed — see .gitignore) is the right
  # tool here, same reasoning infra/aws-poc itself used before it grew a remote backend.
}
