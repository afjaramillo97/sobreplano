# Inputs. Secrets are never variables: Terraform only knows the SSM parameter names.

variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-1"
}

variable "alert_email" {
  description = "Email for the error alarm and the budget. Set TF_VAR_alert_email in .env; not committed."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "scrape_schedules" {
  description = "Developer slug -> EventBridge Scheduler expression, in America/Bogota time."
  type        = map(string)
  # 15 minutes apart: a run takes under 2, so they never overlap and the alarm's time
  # tells which developer failed.
  default = {
    "londono-gomez"        = "cron(0 6 * * ? *)"
    "constructora-capital" = "cron(15 6 * * ? *)"
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for the account, in USD."
  type        = number
  default     = 5
}

variable "ssm_database_url_name" {
  description = "SSM SecureString with the transaction-pooler DATABASE_URL (created by scripts/sync-ssm-secrets.sh)."
  type        = string
  default     = "/sobreplano/prod/database_url"
}

variable "ssm_openai_api_key_name" {
  description = "SSM SecureString with OPENAI_API_KEY (created by scripts/sync-ssm-secrets.sh)."
  type        = string
  default     = "/sobreplano/prod/openai_api_key"
}

variable "github_repository_subject" {
  description = "Repository as it appears in the GitHub OIDC sub claim (owner@owner_id/repo@repo_id); only its main branch may deploy."
  type        = string
  default     = "afjaramillo97@128142098/sobreplano@1431332064"
}
