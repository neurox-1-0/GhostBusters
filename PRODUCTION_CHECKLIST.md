# Production Deployment Checklist

## Required configuration

- PostgreSQL: `DATABASE_URL`; use the repository schema as a baseline and apply future changes through versioned migrations. Startup must not run destructive migrations.
- Redis: `REDIS_URL` for distributed deduplication, scheduler locks, and safe multi-instance coordination.
- Session/security: set `AUTH_REQUIRED=true`, a strong persistent secret/session configuration at the deployment layer, HTTPS, secure cookie handling, and the desired session TTL.
- GitHub: `GITHUB_INTEGRATION_ENABLED`, `GITHUB_WEBHOOK_SECRET`, token/installation credentials through the existing secret provider, repository allowlist, and webhook URL.
- AWS: credentials through the runtime identity or secret provider, `AWS_REGION`/`AWS_ALLOWED_REGIONS`, and required read-only permissions.
- Jira: `JIRA_BASE_URL`, account identity, and API token through the external secret provider; never put tokens in normal tables or logs.
- CORS: set `CORS_ALLOWED_ORIGINS` to an explicit comma-separated allowlist. Empty means same-origin only.
- Request limits: review `MAX_REQUEST_BODY_BYTES` and reverse-proxy limits.

## Operations

- Configure backups and test PostgreSQL restore before launch. Back up Redis only when its deployment requires persistence; workflow truth belongs in PostgreSQL.
- Expose `/live` for process liveness and `/ready` for dependency/configuration readiness.
- Monitor structured workflow, webhook, scheduler, integration, approval, remediation, and outcome events using their correlation IDs.
- Keep bounded external timeouts/retries enabled and review partial-failure warnings.
- Verify webhook signatures, CSRF protection, rate limits, secret redaction, HTTPS, and error responses in the deployed proxy.
- Review Activity Log and Technical Audit access for each role before the live demo.
