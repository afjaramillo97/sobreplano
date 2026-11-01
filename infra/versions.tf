# Terraform and AWS provider versions, the S3 state backend and shared locals.

terraform {
  required_version = ">= 1.10" # use_lockfile needs 1.10+

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    # The bucket name contains the account ID, so it is not written in this public repo:
    # terraform -chdir=infra init -backend-config="bucket=$TF_STATE_BUCKET" (see docs/deploy.md).
    key          = "sobreplano/prod/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "sobreplano"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name       = "sobreplano-scraper"
  account_id = data.aws_caller_identity.current.account_id
}
