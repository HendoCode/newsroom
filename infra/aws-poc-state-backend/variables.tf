variable "region" {
  description = "AWS region for the state bucket. Must match the region infra/aws-poc's backend \"s3\" block declares (the S3 backend requires an explicit region, independent of provider config)."
  type        = string
  default     = "us-east-1"
}
