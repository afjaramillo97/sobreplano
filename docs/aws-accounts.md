# AWS accounts and access

How the AWS side of Sobreplano is organized and how people get access to it. Everything here was set up by hand, once, in the console (October 2026); Terraform (`infra/`, SPEC 05) only manages resources inside the workload account.

This repo is public: account IDs, the access portal URL, the organization ID and email addresses are **not** written here. Ask the owner for them. Terraform reads the account ID at plan time with `data "aws_caller_identity"`.

## Account layout

AWS Organizations with all features enabled.

| Account | Role | What runs there |
| --- | --- | --- |
| Management (payer) | Billing, AWS Organizations, IAM Identity Center | Nothing. No workloads, ever |
| `sobreplano-prod` (member) | Production | Everything in `infra/`: Lambda, ECR, S3, SSM parameters, Scheduler, alarms, Terraform state bucket |

- Region: `us-east-1` for every resource and for IAM Identity Center.
- There is no staging account (SPEC 05, out of scope). A future `sobreplano-dev` account would be a new member account with the same assignments.
- The legacy Free Tier applies: always-free usage is shared across the organization.

## Human access: IAM Identity Center

Organization instance, single Region (`us-east-1`), built-in Identity Center directory.

- MFA is required at **every** sign-in.
- Nobody uses IAM users or long-lived access keys. There are no IAM users in either account.
- The root user of the management account has MFA and no access keys; it is used only for tasks that require root.
- Centralized root access is on (root credentials management): member accounts have no root credentials.

| Group | Permission set | Accounts | Can do |
| --- | --- | --- | --- |
| `sobreplano-admins` | `AdministratorAccess` (8 h session) | Management and `sobreplano-prod` | Everything, including `terraform apply` and billing |
| `sobreplano-developers` | `SobreplanoDeveloper` = `PowerUserAccess` (8 h session) | `sobreplano-prod` only | Run and debug the scraper, read logs, push images. Cannot create or change IAM, so no `terraform apply` of IAM resources, and no access to billing |

Permissions are always assigned to groups, never to individual users.

## Machine access

- GitHub Actions deploys with OIDC: an IAM role in `sobreplano-prod` that trusts only `repo:afjaramillo97/sobreplano:ref:refs/heads/main`. No AWS keys are stored in GitHub (SPEC 05).
- The Lambda reads its secrets from SSM Parameter Store at start-up; the values never enter Terraform state.

## Cost and security guardrails

| Guardrail | Where | Notes |
| --- | --- | --- |
| Budget `account-safety-net`: 1 USD/month, alerts at 100 % actual and forecast | Management account | Covers every account in the organization. No budget actions |
| Free Tier usage alerts and PDF invoice by email | Management account | Billing preferences |
| Project budget of 5 USD and Lambda error alarm | `sobreplano-prod` | Managed by Terraform (SPEC 05) |
| S3 Block Public Access, all four settings | `sobreplano-prod`, account level | Buckets cannot be made public by mistake |
| IAM Access Analyzer, external access | `sobreplano-prod`, `us-east-1` | Free. Review findings after each `terraform apply` |
| IAM user and role access to billing | Management account | Lets admins see billing without root |

Deliberately **not** enabled because they cost money: GuardDuty, Security Hub, AWS Config, Macie, a CloudTrail trail and the unused-access analyzer. CloudTrail event history (90 days) is on by default and free. Check cost before turning any of these on (`CLAUDE.md`, "Budget").

## CLI setup

One-time, on each machine:

```bash
aws configure sso
# SSO session name: sobreplano
# SSO start URL: the access portal URL (ask the owner)
# SSO region: us-east-1
# Account: sobreplano-prod · role: AdministratorAccess or SobreplanoDeveloper
# Default region: us-east-1 · profile name: sobreplano-prod
```

Every working session:

```bash
aws sso login --profile sobreplano-prod
export AWS_PROFILE=sobreplano-prod      # Terraform, Docker/ECR and boto3 pick it up
aws sts get-caller-identity             # must show the sobreplano-prod account
```

Credentials are temporary and expire with the 8 h session; run `aws sso login` again when they do.

## Onboarding a developer

1. Identity Center → Users → add the user with their email and the option to email them password setup instructions.
2. Add them to `sobreplano-developers`. Nothing else in AWS.
3. Add them as a collaborator on the GitHub repo.
4. They accept the invitation, register MFA and follow the CLI setup with the `SobreplanoDeveloper` role.

Offboarding: disable or delete the user in Identity Center (active sessions end when they expire, at most 8 h) and remove them from the GitHub repo.
