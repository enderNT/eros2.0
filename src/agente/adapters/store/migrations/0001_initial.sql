-- v3 initial schema (SPEC §10). Times are UTC ISO-8601 strings.
-- Applied by agente.adapters.store.db.migrate inside a single transaction;
-- do not add BEGIN/COMMIT here.

CREATE TABLE contact (
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    display_name TEXT,
    timezone TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (phone_number_id, contact_phone)
);

CREATE TABLE profile (
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    name TEXT,
    email TEXT,
    kind TEXT NOT NULL DEFAULT 'prospect' CHECK (kind IN ('patient', 'prospect')),
    timezone TEXT,
    appointment_count INTEGER NOT NULL DEFAULT 0,
    last_appointment_utc TEXT,
    next_appointment_utc TEXT,
    handoff_state TEXT NOT NULL DEFAULT 'bot',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (phone_number_id, contact_phone),
    FOREIGN KEY (phone_number_id, contact_phone)
        REFERENCES contact (phone_number_id, contact_phone)
);

-- kapso_message_id is unique across the table: that is the dedupe of §4 step 2.
CREATE TABLE message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    kapso_message_id TEXT NOT NULL UNIQUE,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_by_us INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (phone_number_id, contact_phone)
        REFERENCES contact (phone_number_id, contact_phone)
);

-- Window reads: last messages of one contact in time order.
CREATE INDEX idx_message_window
    ON message (phone_number_id, contact_phone, created_at, id);

CREATE TABLE summary (
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    text TEXT NOT NULL,
    watermark_message_id INTEGER NOT NULL REFERENCES message (id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (phone_number_id, contact_phone)
);

-- The three mute levels. Row present means muted; muted_until NULL means
-- indefinitely, and the mute expires at exactly that instant.
CREATE TABLE mute (
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    muted_at TEXT NOT NULL,
    muted_until TEXT,
    PRIMARY KEY (phone_number_id, contact_phone)
);

CREATE TABLE number_mute (
    phone_number_id TEXT PRIMARY KEY,
    muted_at TEXT NOT NULL,
    muted_until TEXT
);

CREATE TABLE global_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    muted_at TEXT NOT NULL,
    muted_until TEXT
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    phone_number_id TEXT,
    contact_phone TEXT,
    reason TEXT NOT NULL,
    urgent INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE appointment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    calendly_event_id TEXT NOT NULL UNIQUE,
    slot_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (phone_number_id, contact_phone)
        REFERENCES contact (phone_number_id, contact_phone)
);

CREATE INDEX idx_appointment_contact
    ON appointment (phone_number_id, contact_phone);

CREATE TABLE llm_trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL,
    stop_reason TEXT,
    tools_called TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_llm_trace_turn ON llm_trace (turn_id);

-- Seam for reminders (§13); empty in v3. Due rows are the unsent ones.
CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    sent_at TEXT,
    kapso_message_id TEXT
);

CREATE INDEX idx_outbox_due ON outbox (due_at) WHERE sent_at IS NULL;
