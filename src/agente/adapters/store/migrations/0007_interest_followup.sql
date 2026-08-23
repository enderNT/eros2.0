-- Un seguimiento distinto del de reserva, y a propósito separado de él.
--
-- El de reserva pregunta "¿pudiste agendar tu cita?" a quien ya recibió un
-- horario concreto. Éste es para quien mostró interés y se enfrió **antes** de
-- llegar a agendar: nunca hubo hueco, ni token, ni nada a lo que referirse. Se
-- disparan en momentos distintos y por motivos distintos, así que comparten el
-- outbox pero no la fila, ni el ajuste, ni el botón del panel.

-- SQLite no sabe alterar un CHECK: la tabla se reconstruye entera para admitir
-- el tercer tipo. Se conservan filas, ids e índices.
ALTER TABLE outbox RENAME TO outbox_old;

CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    sent_at TEXT,
    kapso_message_id TEXT,
    booking_token TEXT,
    slot_utc TEXT,
    kind TEXT NOT NULL DEFAULT 'booking_followup'
        CHECK (kind IN ('booking_followup', 'appointment_reminder', 'interest_followup')),
    appointment_event_id TEXT
);

INSERT INTO outbox (id, phone_number_id, contact_phone, text, due_at, sent_at,
                    kapso_message_id, booking_token, slot_utc, kind, appointment_event_id)
    SELECT id, phone_number_id, contact_phone, text, due_at, sent_at,
           kapso_message_id, booking_token, slot_utc, kind, appointment_event_id
    FROM outbox_old;

DROP TABLE outbox_old;

CREATE INDEX idx_outbox_due ON outbox (due_at) WHERE sent_at IS NULL;

CREATE UNIQUE INDEX idx_outbox_booking_token
    ON outbox (booking_token)
    WHERE booking_token IS NOT NULL;

CREATE UNIQUE INDEX idx_outbox_appointment_event
    ON outbox (appointment_event_id)
    WHERE appointment_event_id IS NOT NULL;

-- Un solo seguimiento de interés vivo por contacto: el que se programe después
-- sustituye al anterior, en vez de acumular preguntas al que no contesta.
CREATE UNIQUE INDEX idx_outbox_interest_followup
    ON outbox (phone_number_id, contact_phone)
    WHERE kind = 'interest_followup' AND sent_at IS NULL;

-- Su propio ajuste, con su propio rango. 1 minuto es el mínimo útil para
-- probarlo de punta a punta sin esperar; 90 es el techo que ya usa el de reserva.
ALTER TABLE app_setting ADD COLUMN interest_followup_minutes INTEGER NOT NULL DEFAULT 60
    CHECK (interest_followup_minutes BETWEEN 1 AND 90);
