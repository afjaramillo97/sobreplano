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

variable "scrape_schedule" {
  description = "EventBridge Scheduler expression for the scrape, in America/Bogota time."
  type        = string
  default     = "cron(0 6 * * ? *)" # every day at 06:00
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

variable "github_repository" {
  description = "owner/repo allowed to deploy through OIDC, from its main branch only."
  type        = string
  default     = "afjaramillo97/sobreplano"
}
