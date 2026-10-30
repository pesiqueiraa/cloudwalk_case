-- Esquema da plataforma. Idempotente: aplicado a cada subida do platform-web.

CREATE TABLE IF NOT EXISTS brands (
    id     text PRIMARY KEY,
    name   text NOT NULL,
    locale text NOT NULL
);

INSERT INTO brands (id, name, locale) VALUES
    ('infinitepay', 'InfinitePay', 'pt-BR'),
    ('jim', 'JIM', 'en-US')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS customers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id    text NOT NULL REFERENCES brands (id),
    external_id text NOT NULL,
    name        text NOT NULL,
    email       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (brand_id, external_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id            text NOT NULL REFERENCES brands (id),
    customer_id         uuid NOT NULL REFERENCES customers (id),
    channel             text NOT NULL,
    external_session_id text NOT NULL,
    status              text NOT NULL DEFAULT 'open',
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (brand_id, channel, external_session_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id    uuid NOT NULL REFERENCES conversations (id),
    trace_id           uuid NOT NULL,
    direction          text NOT NULL CHECK (direction IN ('in', 'out')),
    author             text NOT NULL CHECK (author IN ('customer', 'agent', 'analyst')),
    text               text NOT NULL,
    channel_message_id text,               -- ID da mensagem no canal (idempotência da ingestão)
    source_event_id    uuid UNIQUE,        -- event_id do AgentResult (idempotência do callback)
    created_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (conversation_id, channel_message_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id              bigserial PRIMARY KEY,
    event_id        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    trace_id        uuid NOT NULL,
    conversation_id uuid NOT NULL,
    type            text NOT NULL,
    actor           text NOT NULL,
    payload         jsonb NOT NULL DEFAULT '{}',
    occurred_at     timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS audit_events_trace_idx ON audit_events (trace_id);
CREATE INDEX IF NOT EXISTS audit_events_conversation_idx ON audit_events (conversation_id);

CREATE OR REPLACE FUNCTION audit_events_reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events é append-only: % não é permitido', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_reject_change();

CREATE TABLE IF NOT EXISTS webhook_jobs (
    id              bigserial PRIMARY KEY,
    event_id        uuid NOT NULL UNIQUE,
    trace_id        uuid NOT NULL,
    conversation_id uuid NOT NULL,         -- um job por vez por conversa, para manter a ordem
    payload         jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
    attempts        int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS webhook_jobs_due_idx ON webhook_jobs (next_attempt_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS webhook_jobs_conversation_idx ON webhook_jobs (conversation_id, id) WHERE status = 'pending';
