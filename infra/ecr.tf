# Container registry for the scraper image; keeps the last 5 images.

resource "aws_ecr_repository" "scraper" {
  name = local.name
  # Tags are git SHAs (plus "bootstrap" for the first image): never overwritten.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "scraper" {
  repository = aws_ecr_repository.scraper.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

data "aws_iam_policy_document" "ecr_lambda_pull" {
  # What Lambda would add on its own when it first uses the repository; declared here so
  # Terraform owns it and the plan stays clean.
  statement {
    sid     = "LambdaECRImageRetrievalPolicy"
    actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "aws:sourceArn"
      values   = ["arn:aws:lambda:${var.region}:${local.account_id}:function:*"]
    }
  }
}

resource "aws_ecr_repository_policy" "scraper" {
  repository = aws_ecr_repository.scraper.name
  policy     = data.aws_iam_policy_document.ecr_lambda_pull.json
}
