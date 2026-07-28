-- Backfill canonical tenant rows from the durable authentication snapshot.
-- Idempotent and intentionally non-destructive: existing organizations win.
INSERT INTO organizations (id, name, slug, status, timezone, created_at, updated_at)
SELECT (item->>'id')::uuid,
       item->>'name',
       item->>'slug',
       COALESCE(item->>'status', 'active'),
       COALESCE(item->>'timezone', 'UTC'),
       (item->>'created_at')::timestamptz,
       (item->>'updated_at')::timestamptz
FROM auth_state AS state
CROSS JOIN LATERAL jsonb_array_elements(state.payload->'organizations') AS item
WHERE state.id = 1
  AND item ? 'id'
  AND item ? 'name'
  AND item ? 'slug'
ON CONFLICT (id) DO NOTHING;
