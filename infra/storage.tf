# Private bucket for the raw HTML: s3://{bucket}/{developer}/{YYYY-MM-DD}/{sha256}.html.

resource "aws_s3_bucket" "raw_html" {
  # A prefix and a random suffix: unique without putting the account ID in the code.
  bucket_prefix = "sobreplano-raw-html-"
}

resource "aws_s3_bucket_public_access_block" "raw_html" {
  bucket                  = aws_s3_bucket.raw_html.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "raw_html" {
  bucket = aws_s3_bucket.raw_html.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_html" {
  bucket = aws_s3_bucket.raw_html.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw_html" {
  bucket = aws_s3_bucket.raw_html.id

  rule {
    id     = "glacier-ir-after-90-days"
    status = "Enabled"
    filter {}

    # Raw HTML is only read again to re-extract, and it grows every day.
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "raw_html_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.raw_html.arn,
      "${aws_s3_bucket.raw_html.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "raw_html" {
  bucket = aws_s3_bucket.raw_html.id
  policy = data.aws_iam_policy_document.raw_html_tls_only.json

  # S3 rejects a bucket policy until the public access block is in place.
  depends_on = [aws_s3_bucket_public_access_block.raw_html]
}
