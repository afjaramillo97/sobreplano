# The scraper Lambda (container image, arm64), its least-privilege role and its log group.

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scraper" {
  name               = local.name
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "scraper" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.scraper.arn}:*"]
  }

  statement {
    sid       = "WriteRawHtml"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw_html.arn}/*"]
  }

  # SecureStrings use the AWS managed key aws/ssm, whose key policy already lets SSM
  # decrypt for principals of this account: no kms:Decrypt needed here.
  statement {
    sid     = "ReadSecrets"
    actions = ["ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${var.region}:${local.account_id}:parameter${var.ssm_database_url_name}",
      "arn:aws:ssm:${var.region}:${local.account_id}:parameter${var.ssm_openai_api_key_name}",
    ]
  }
}

resource "aws_iam_role_policy" "scraper" {
  name   = local.name
  role   = aws_iam_role.scraper.id
  policy = data.aws_iam_policy_document.scraper.json
}

resource "aws_lambda_function" "scraper" {
  function_name = local.name
  role          = aws_iam_role.scraper.arn
  package_type  = "Image"
  # First apply only: the image is pushed by hand with this tag (docs/deploy.md); after
  # that GitHub Actions deploys each commit, hence ignore_changes below.
  image_uri     = "${aws_ecr_repository.scraper.repository_url}:bootstrap"
  architectures = ["arm64"]
  # New accounts are capped at 512 MB; the run mostly waits on the network and the LLM.
  memory_size = 512
  timeout     = 600
  # No reserved concurrency: the account limit is 5 and AWS keeps 10 unreserved. The
  # database lock allows one run per developer per day (SPEC 05).

  environment {
    variables = {
      RAW_STORE          = "s3://${aws_s3_bucket.raw_html.bucket}"
      SSM_DATABASE_URL   = var.ssm_database_url_name
      SSM_OPENAI_API_KEY = var.ssm_openai_api_key_name
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.scraper.name
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [
    aws_iam_role_policy.scraper,
    aws_ecr_repository_policy.scraper,
  ]
}

resource "aws_lambda_function_event_invoke_config" "scraper" {
  function_name = aws_lambda_function.scraper.function_name
  # The scheduler invokes asynchronously, so a failed run is retried by Lambda, not by the
  # scheduler. 2 is the default, written down: retries are safe (SPEC 05).
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600
}
