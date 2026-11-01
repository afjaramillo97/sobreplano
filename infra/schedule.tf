# EventBridge Scheduler: invokes the scraper on var.scrape_schedule, Bogotá time.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.scraper.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${local.name}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "scraper_daily" {
  name                         = "${local.name}-daily"
  schedule_expression          = var.scrape_schedule
  schedule_expression_timezone = "America/Bogota" # no daylight saving time

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.scraper.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ developer = "londono-gomez", limit = null })

    # Covers failures to deliver the invocation (throttling, service errors); a run that
    # fails inside the function is retried by aws_lambda_function_event_invoke_config.
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}
