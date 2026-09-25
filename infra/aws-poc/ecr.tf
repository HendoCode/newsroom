# Two small ECR repos — one per image. Images are built and pushed manually before the full
# `tofu apply` (see README — "Apply sequence"); the instance's user-data only ever pulls, so no
# Git/GitHub credential is ever needed on the box.

resource "aws_ecr_repository" "web" {
  name                 = "cmw-poc-web"
  image_tag_mutability = "MUTABLE"
  # So a plain `tofu destroy` never fails on "repository not empty" — matches the POC's
  # "easy to tear down" bar. The repos themselves cost ~$0.10-0.20/mo if ever left behind.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_ecr_repository" "agents" {
  name                 = "cmw-poc-agents"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }
}
