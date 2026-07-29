# Capability Summary

## Real integration paths (optional)

- Authenticated, organization-scoped workflows with granular permissions.
- Append-only decisions, Activity Log, Technical Audit, approvals, scheduling, and outcome verification.
- Read-only AWS collection when AWS credentials, regions, and permissions are configured and `inventory_source=real_aws` is selected.
- Read-only GitHub and Jira context collection when server-side credentials, allowlists, and validation succeed.
- GitHub webhook signature verification when `GITHUB_WEBHOOK_SECRET` is configured.

## Fixture-backed or simulated capabilities

- Competition demo scenarios, fixture Cloud Hunt inventory, and deterministic fallback evidence.
- Demo remediation results and Cloud Hunt proposals when real GitHub remediation is disabled.
- Pricing and utilization values from scenario fixtures are not production billing truth.
- Production pricing is intentionally unavailable unless a live or verified-cached pricing provider is configured with complete provenance; mock and fixture pricing are restricted to explicit demo/test mode.

## Unsupported or intentionally disabled

- Terraform apply, automatic merge, branch deletion, rollback, Jira mutation, and automatic approval.
- Slack, Teams, and email notifications unless a supported channel is configured.
- Real remediation PR creation is optional and disabled by default; it requires explicit `GITHUB_CREATE_REAL_PR=true` and human approval.
- Unrestricted cron schedules and silent fallback from real integrations to fixtures.

Human approval remains required before remediation actions, and missing or conflicting evidence reduces confidence or escalates safely.
