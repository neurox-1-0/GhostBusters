CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS organization_memberships (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    approval_permission_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL,
    invited_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    joined_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS invitations (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    approval_permission_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    token_hash TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    invited_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_events (
    id BIGSERIAL PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS organization_memberships_org_idx ON organization_memberships(organization_id);
CREATE INDEX IF NOT EXISTS activity_events_org_idx ON activity_events(organization_id, created_at);

INSERT INTO organizations (id, name, slug, status, timezone, created_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'GhostBusters Development', 'ghostbusters-dev', 'active', 'UTC', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    goal TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL,
    idempotency_key TEXT,
    error TEXT,
    payload JSONB NOT NULL,
    UNIQUE (organization_id, idempotency_key)
);

ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
ALTER TABLE workflow_runs DROP CONSTRAINT IF EXISTS workflow_runs_idempotency_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS workflow_runs_org_idempotency_idx ON workflow_runs(organization_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS workflow_runs_status_idx ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS workflow_runs_created_at_idx ON workflow_runs(created_at);
CREATE INDEX IF NOT EXISTS workflow_runs_org_idx ON workflow_runs(organization_id, created_at);

CREATE TABLE IF NOT EXISTS evidence_records (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    resource_id TEXT NOT NULL,
    source TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    claim TEXT NOT NULL,
    freshness_status TEXT NOT NULL,
    reliability DOUBLE PRECISION NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

ALTER TABLE evidence_records ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
CREATE INDEX IF NOT EXISTS evidence_records_run_idx ON evidence_records(run_id);
CREATE INDEX IF NOT EXISTS evidence_records_resource_idx ON evidence_records(resource_id);
CREATE INDEX IF NOT EXISTS evidence_records_org_idx ON evidence_records(organization_id, run_id);

CREATE TABLE IF NOT EXISTS approvals (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    reviewer TEXT NOT NULL,
    action TEXT NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

ALTER TABLE approvals ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
CREATE INDEX IF NOT EXISTS approvals_run_idx ON approvals(run_id);
CREATE INDEX IF NOT EXISTS approvals_org_idx ON approvals(organization_id, run_id);

CREATE TABLE IF NOT EXISTS waivers (
    id BIGSERIAL PRIMARY KEY,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    resource_id TEXT NOT NULL,
    run_id UUID REFERENCES workflow_runs(id) ON DELETE SET NULL,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    milestone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at IS NOT NULL OR milestone IS NOT NULL)
);

ALTER TABLE waivers ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
CREATE INDEX IF NOT EXISTS waivers_active_resource_idx ON waivers(organization_id, resource_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    sequence_number INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    summary TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, sequence_number)
);

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
CREATE INDEX IF NOT EXISTS audit_log_run_idx ON audit_log(run_id, sequence_number);
CREATE INDEX IF NOT EXISTS audit_log_org_idx ON audit_log(organization_id, run_id);

CREATE TABLE IF NOT EXISTS cloud_hunts (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

ALTER TABLE cloud_hunts ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
CREATE INDEX IF NOT EXISTS cloud_hunts_org_idx ON cloud_hunts(organization_id, created_at);

CREATE TABLE IF NOT EXISTS cloud_review_cases (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id),
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

ALTER TABLE cloud_review_cases ADD COLUMN IF NOT EXISTS organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES organizations(id);
CREATE INDEX IF NOT EXISTS cloud_review_cases_status_idx ON cloud_review_cases ((payload->>'status'));
CREATE INDEX IF NOT EXISTS cloud_review_cases_org_idx ON cloud_review_cases(organization_id, updated_at);
