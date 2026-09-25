# Reuse the account's default VPC/subnet rather than provision a purpose-built one — cheapest,
# zero IGW/route-table/NAT to manage, matches the scoping report's §1/§2 recommendation.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Amazon Linux 2023 AMI via the AWS-published SSM public parameter — no brittle name-filter
# guessing, always current at apply time.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# Resolved to the real key ARN (not a hand-built alias ARN) for the kms:Decrypt grant in iam.tf —
# SSM SecureString parameters are encrypted with this AWS-managed key by default.
data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}
