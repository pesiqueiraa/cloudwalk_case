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
    created_at          timestamptz NOT NULL DEFAULT now()
    -- Unicidade da sessão: índice parcial conversations_one_open_per_session, mais abaixo
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
    status          text NOT NULL DEFAULT 'pending',  -- CHECK mais abaixo
    attempts        int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS webhook_jobs_due_idx ON webhook_jobs (next_attempt_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS webhook_jobs_conversation_idx ON webhook_jobs (conversation_id, id) WHERE status = 'pending';

-- Semana 2: equipes, filas e regras de roteamento. Filas e regras nunca são apagadas, só desativadas.

CREATE TABLE IF NOT EXISTS teams (
    id   text PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS analysts (
    id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id text NOT NULL REFERENCES teams (id),
    name    text NOT NULL,
    email   text NOT NULL
);

CREATE TABLE IF NOT EXISTS queues (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL UNIQUE,
    brand_id        text NOT NULL REFERENCES brands (id),
    team_id         text NOT NULL REFERENCES teams (id),
    first_responder text NOT NULL CHECK (first_responder IN ('agent', 'human')),
    is_default      boolean NOT NULL DEFAULT false,  -- recebe o que nenhuma regra casou
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS queues_one_default_per_brand ON queues (brand_id) WHERE is_default AND active;

CREATE TABLE IF NOT EXISTS routing_rules (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    position   int NOT NULL,                         -- ordem de avaliação: vale a primeira que casa
    -- Condições: nulo casa qualquer valor
    brand_id   text REFERENCES brands (id),
    channel    text CHECK (channel IN ('chat', 'whatsapp', 'email')),
    category   text CHECK (category IN ('payments', 'hardware', 'card', 'account', 'fraud', 'other')),
    priority   text CHECK (priority IN ('high', 'normal')),
    queue_id   uuid NOT NULL REFERENCES queues (id),
    active     boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Colunas novas em tabelas da semana 1: ADD COLUMN IF NOT EXISTS evita zerar o banco
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS category text,
    ADD COLUMN IF NOT EXISTS priority text;

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS queue_id   uuid REFERENCES queues (id),
    ADD COLUMN IF NOT EXISTS priority   text,
    ADD COLUMN IF NOT EXISTS handled_by text,   -- quem atende primeiro: 'agent' ou 'human', vindo da fila
    ADD COLUMN IF NOT EXISTS routed_at  timestamptz;

CREATE INDEX IF NOT EXISTS conversations_queue_idx ON conversations (queue_id);

-- Semana 3: handoff

ALTER TABLE queues
    ADD COLUMN IF NOT EXISTS escalation_queue_id uuid REFERENCES queues (id);  -- nulo: escala na própria fila

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS escalated_at       timestamptz,
    ADD COLUMN IF NOT EXISTS escalation_reason  text,
    ADD COLUMN IF NOT EXISTS escalation_summary text,
    ADD COLUMN IF NOT EXISTS closed_at          timestamptz;

-- CHECKs trocados por DROP + ADD: o banco de uma semana anterior ganha os valores novos sem down -v
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_status_check;
ALTER TABLE conversations ADD CONSTRAINT conversations_status_check
    CHECK (status IN ('open', 'escalated', 'closed'));

ALTER TABLE webhook_jobs DROP CONSTRAINT IF EXISTS webhook_jobs_status_check;
ALTER TABLE webhook_jobs ADD CONSTRAINT webhook_jobs_status_check
    CHECK (status IN ('pending', 'done', 'failed', 'cancelled'));  -- cancelled: conversa foi para humano

-- Uma conversa não encerrada por sessão. Encerrada, a próxima mensagem do canal abre outra.
-- A ingestão repete este predicado no ON CONFLICT.
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_brand_id_channel_external_session_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS conversations_one_open_per_session
    ON conversations (brand_id, channel, external_session_id) WHERE status <> 'closed';

-- Respostas do agente que chegaram depois do handoff: guardadas para auditoria, nunca entregues
CREATE TABLE IF NOT EXISTS discarded_agent_results (
    event_id        uuid PRIMARY KEY,                -- idempotência: a reentrega não gera outro descarte
    conversation_id uuid NOT NULL REFERENCES conversations (id),
    trace_id        uuid NOT NULL,
    in_reply_to     uuid NOT NULL,
    event_type      text NOT NULL,
    text            text NOT NULL,
    reason          text NOT NULL,
    discarded_at    timestamptz NOT NULL DEFAULT now()
);

-- Semana 3, etapa 2: analista que assumiu o caso
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS assigned_analyst_id uuid REFERENCES analysts (id),
    ADD COLUMN IF NOT EXISTS assigned_at         timestamptz;

CREATE INDEX IF NOT EXISTS conversations_customer_idx ON conversations (customer_id);  -- memória do cliente
