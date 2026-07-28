# Production Deployment Checklist

## Required configuration

- Runtime: `APP_ENV=production`, `AUTH_REQUIRED=true`, `SECRET_KEY` or `SESSION_SECRET` with at least 32 non-default characters, `TRUST_PROXY_HEADERS=true`, and `DEMO_MODE_ENABLED=false`.
- PostgreSQL: `DATABASE_URL`; Render runs `python scripts/migrate.py --database-url "$DATABASE_URL" --fresh-local` as the pre-deploy command. The flag initializes only a database with no `organizations` table; existing databases receive only unapplied versioned migrations. Startup does not run migrations.
- Redis: `REDIS_URL` for distributed deduplication, scheduler state, leases, and safe multi-instance coordination.
- Session/security: set `AUTH_REQUIRED=true`, a strong persistent secret/session configuration at the deployment layer, HTTPS, secure cookie handling, and the desired session TTL.
- GitHub: `GITHUB_INTEGRATION_ENABLED`, `GITHUB_WEBHOOK_SECRET`, token/installation credentials through the existing secret provider, repository allowlist, and webhook URL.
- AWS: credentials through the runtime identity or secret provider, `AWS_REGION`/`AWS_ALLOWED_REGIONS`, and required read-only permissions.
- Jira: `JIRA_BASE_URL`, account identity, and API token through the external secret provider; never put tokens in normal tables or logs.
- CORS: set `CORS_ALLOWED_ORIGINS` to an explicit comma-separated allowlist. Empty means same-origin only.
- Request limits: review `MAX_REQUEST_BODY_BYTES` and reverse-proxy limits.
- Rate limits: review `EXPENSIVE_RATE_LIMIT_ATTEMPTS` and `EXPENSIVE_RATE_LIMIT_WINDOW_SECONDS`; Redis is required for production enforcement.

## Operations

- Configure backups and test PostgreSQL restore before launch. Back up Redis only when its deployment requires persistence; workflow truth belongs in PostgreSQL.
- Expose `/live` for process liveness and `/ready` for dependency/configuration readiness.
- Render uses `/live` for its health check because `/ready` currently reports dependency state in JSON while retaining HTTP 200; use `/ready` from an external deployment monitor until it returns a non-2xx status on failure.
- Monitor structured workflow, webhook, scheduler, integration, approval, remediation, and outcome events using their correlation IDs.
- Keep bounded external timeouts/retries enabled and review partial-failure warnings.
- Keep `GITHUB_CREATE_REAL_PR=false` unless real PR creation has been explicitly approved and separately monitored.
- Render currently provisions no scheduler worker because the repository has no safe long-running scheduler entry point. Keep `CLOUD_HUNT_SCHEDULE_ENABLED=false` until one is added; do not create one Cron Job per tenant.
- Verify webhook signatures, CSRF protection, rate limits, secret redaction, HTTPS, and error responses in the deployed proxy.
- Review Activity Log and Technical Audit access for each role before the live demo.

## Migration notes

`db/migrations/001_baseline.sql` represents the current `db/schema.sql` baseline. On an existing database, stamp or review the baseline before applying `002_activity_and_scheduler_hardening.sql`. The migration runner does not provide automatic rollback; take a backup and use a forward corrective migration.

Production must use `AUTO_CREATE_SCHEMA=false`. Local/demo startup may continue using `AUTO_CREATE_SCHEMA=true` and `db/schema.sql`.
