ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS event_id UUID;
CREATE UNIQUE INDEX IF NOT EXISTS activity_events_event_id_idx ON activity_events(event_id) WHERE event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS scheduler_locks (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    schedule_id UUID NOT NULL,
    lease_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, schedule_id)
);

CREATE TABLE IF NOT EXISTS tenant_state (
    kind TEXT NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (kind, organization_id)
);
CREATE INDEX IF NOT EXISTS tenant_state_org_idx ON tenant_state(organization_id, updated_at);

CREATE TABLE IF NOT EXISTS auth_state (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
