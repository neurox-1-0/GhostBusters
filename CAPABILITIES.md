# Capability Summary

## Real capabilities

- Authenticated, organization-scoped workflows with granular permissions.
- Append-only decisions, Activity Log, Technical Audit, approvals, scheduling, and outcome verification.
- Read-only AWS, GitHub, and Jira collection when the corresponding integration is configured and validated.
- GitHub webhook signature verification when `GITHUB_WEBHOOK_SECRET` is configured.

## Fixture-backed capabilities

- Competition demo scenarios, fixture Cloud Hunt inventory, and deterministic fallback evidence.
- Demo remediation results when real GitHub remediation is disabled.

## Unsupported or intentionally disabled

- Terraform apply, automatic merge, branch deletion, rollback, Jira mutation, and automatic approval.
- Slack, Teams, and email notifications unless a supported channel is configured.
- Unrestricted cron schedules and silent fallback from real integrations to fixtures.

Human approval remains required before remediation actions, and missing or conflicting evidence reduces confidence or escalates safely.
