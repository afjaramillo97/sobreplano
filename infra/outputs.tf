# Names the deploy needs: the image repository, the function and the GitHub role.

output "raw_html_bucket" {
  description = "Bucket with the raw HTML."
  value       = aws_s3_bucket.raw_html.bucket
}

output "ecr_repository_url" {
  description = "Where to push the scraper image."
  value       = aws_ecr_repository.scraper.repository_url
}

output "lambda_function_name" {
  description = "The scraper function."
  value       = aws_lambda_function.scraper.function_name
}

output "schedule_name" {
  description = "The EventBridge Scheduler schedule."
  value       = aws_scheduler_schedule.scraper_daily.name
}

output "github_deploy_role_arn" {
  description = "Role for .github/workflows/deploy-scraper.yml (repository variable, not a secret)."
  value       = aws_iam_role.github_deploy.arn
}

output "alerts_topic_arn" {
  description = "SNS topic of the error alarm."
  value       = aws_sns_topic.alerts.arn
}
