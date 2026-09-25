# Durable public storage for a piece's PUBLISHED outputs (finalized → published HITL button —
# see agents/app/publish/README.md and docs/design.md's D13 note). A SEPARATE bucket from
# `cmw-aws-poc-tofu-state-${account_id}` (infra/aws-poc-state-backend/state_bucket.tf) — never
# conflate OpenTofu's own state with application data.
#
# Unconditional, NOT count-conditional on any variable — an explicit captain requirement. This is
# exactly the "SSM rejects blank, so make creation opt-in" count-flip pattern secrets.tf's five
# optional secrets are forced into (see that file's header comment and README's "Apply sequence"
# step 4 warning); a plain resource with `prevent_destroy` is what's wanted instead, so a bare
# `tofu apply` with no `-var` overrides can never propose destroying it.
#
# `prevent_destroy = true` mirrors the existing durable-storage idiom in this stack
# (infra/aws-poc-state-backend/state_bucket.tf's `aws_s3_bucket.tofu_state`,
# compute.tf's `aws_ebs_volume.mongo_data`) — a plain `tofu destroy` refuses to touch it. Unlike
# those two, this bucket is also deliberately GENERALLY PUBLIC by policy (Hendo, v1 — "happy with
# them landing in an s3 bucket... let's treat the published assets... as generally public. We can
# iterate that decision later, and easily"): no signed URLs, no unguessable keys, no per-object
# ACL layer. Tightening this later is cheap; it just can't un-share a URL already circulating —
# see the publish README's "Permanence" note. Object keys are minted app-side
# (`app.publish.service.PublishService`) as `published/<slug>/<release>/branded.{html,pdf}`, one
# NEW immutable key per publish (never overwritten in place), so an already-shared link survives a
# later re-render, re-publish, template-version bump, or Git history rewrite.
resource "aws_s3_bucket" "published_assets" {
  bucket = "cmw-poc-published-assets-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

# Versioning ON so a re-publish that (by app-side bug or otherwise) ever reused a key still can't
# silently destroy the bytes an existing link points at — belt-and-suspenders alongside the
# app-side immutable-key discipline above, matching the state bucket's own versioning rationale.
resource "aws_s3_bucket_versioning" "published_assets" {
  bucket = aws_s3_bucket.published_assets.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Allows per-object ACLs (BucketOwnerPreferred) so publish can grant public-read on specific objects
# and unpublish can flip exactly those to private — reversing the per-object grant without touching
# the bucket-wide policy. The policy still provides the baseline public read; ACL private overrides
# it for unpublished objects.
resource "aws_s3_bucket_ownership_controls" "published_assets" {
  bucket = aws_s3_bucket.published_assets.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# Public READ by policy (below) is the whole point of this bucket, so — unlike the state bucket's
# fully-locked-down block — `block_public_policy`/`restrict_public_buckets` must be OFF for that
# policy to take effect. ACL-based public access stays blocked (irrelevant anyway with
# BucketOwnerEnforced above, but harmless defense-in-depth to leave set).
resource "aws_s3_bucket_public_access_block" "published_assets" {
  bucket = aws_s3_bucket.published_assets.id

  block_public_acls       = false
  ignore_public_acls      = false
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_server_side_encryption_configuration" "published_assets" {
  bucket = aws_s3_bucket.published_assets.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Public GetObject only — deliberately NEVER s3:ListBucket. "Bucket listing off" (Hendo) isn't an
# access-control ask (the objects are public either way); it just stops the bucket becoming a
# browsable index of every piece ever published. A caller who doesn't already have a specific key
# (from the Piece's own recorded `published_html_url`/`published_pdf_url`/`published_doc`, or a
# link a human copy-pasted) has no way to enumerate what else is in here.
resource "aws_s3_bucket_policy" "published_assets_public_read" {
  bucket = aws_s3_bucket.published_assets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowPublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.published_assets.arn}/*"
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.published_assets.arn,
          "${aws_s3_bucket.published_assets.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.published_assets]
}
