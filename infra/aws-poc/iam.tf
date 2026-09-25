# Instance role: SSM Session Manager for shell access (no SSH key, no port 22 anywhere) + scoped
# read of exactly this POC's own SSM parameter prefix + pull-only ECR access for the two images
# user-data fetches at boot.

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name_prefix        = "cmw-poc-"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ssm:GetParameter on exactly the paths this deploy owns (Anthropic key, NEXTAUTH secret, brain
# push credential, Google OAuth grant, Mongo creds) — nothing broader.
# Shared by two call sites: user-data (fetches the non-shim secrets directly at boot — see
# templates/user-data.sh.tpl) and the `agents` container itself (SECRETS_BACKEND=aws resolves
# ANTHROPIC_API_KEY/MONGO_URL/BRAIN_REPO_URL/BRAIN_DEPLOY_KEY/GOOGLE_OAUTH_CLIENT_ID/
# GOOGLE_OAUTH_CLIENT_SECRET/GOOGLE_OAUTH_REFRESH_TOKEN live, per-request, over IMDS-forwarded
# credentials). This wildcard already covers any new name under the prefix — adding
# GOOGLE_OAUTH_* above needed no policy change, just this comment update.
data "aws_iam_policy_document" "read_params" {
  statement {
    sid       = "ReadCmwPocSsmParameters"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}*"]
  }

  statement {
    sid       = "DecryptSsmSecureStrings"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]
  }
}

resource "aws_iam_role_policy" "read_params" {
  name   = "cmw-poc-read-ssm-params"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.read_params.json
}

resource "aws_iam_instance_profile" "instance" {
  name_prefix = "cmw-poc-"
  role        = aws_iam_role.instance.name
}

# s3:PutObject on exactly the published-assets bucket (publish_bucket.tf) — the ONLY write path
# `app.publish.storage.S3PublishStorage` needs; ambient IAM role credentials via IMDS
# (metadata_options.http_put_response_hop_limit = 2 in compute.tf already covers the container
# hop), same credential story SECRETS_BACKEND=aws already relies on for SSM. No s3:GetObject/
# ListBucket here — reads are public by bucket policy (publish_bucket.tf), never via this role.
data "aws_iam_policy_document" "publish_bucket_write" {
  statement {
    sid       = "WritePublishedAssets"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.published_assets.arn}/*"]
  }
}

resource "aws_iam_role_policy" "publish_bucket_write" {
  name   = "cmw-poc-write-published-assets"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.publish_bucket_write.json
}

# bedrock:InvokeModel + InvokeModelWithResponseStream on the three GLM foundation-model ARNs in
# us-east-1. Required because BedrockGLMProvider (the live default since PR 108) uses ambient
# instance IAM with no API key; the prior policy had zero bedrock:* grants. The implementing
# worker's proof used the captain's personal creds, not the instance role, so the gap was not
# caught. Only foundation-model ARNs are needed (the code passes bare modelId "zai.glm-5" etc
# to Converse; inference-profile / cross-region routing form would use a different ARN shape
# arn:...:inference-profile/... and would require a separate permission — not used here).
# Include all three models so a future tier decision (GLM4.7 etc) needs no second apply.
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid = "InvokeBedrockGLMModels"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:us-east-1::foundation-model/zai.glm-5",
      "arn:aws:bedrock:us-east-1::foundation-model/zai.glm-4.7",
      "arn:aws:bedrock:us-east-1::foundation-model/zai.glm-4.7-flash",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock_invoke" {
  name   = "cmw-poc-bedrock-invoke-glm"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

# cloudwatch:PutMetricData scoped to the CMW/Bedrock namespace only (via condition, not global
# grant). Used by BedrockGLMProvider to emit InferenceCostUSD per call (dimensioned by Step+Model)
# for the non-technical cost dashboard. Emission is best-effort, offloaded to executor, and
# swallowed on failure so telemetry never impacts inference. Controllable via settings flag.
data "aws_iam_policy_document" "cloudwatch_put_metrics" {
  statement {
    sid       = "PutCmwBedrockMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["CMW/Bedrock"]
    }
  }
}

resource "aws_iam_role_policy" "cloudwatch_put_metrics" {
  name   = "cmw-poc-cloudwatch-put-bedrock-metrics"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.cloudwatch_put_metrics.json
}
