-- Enterrar el agendamiento por enlace, que ya no existe.
--
-- El bot mandaba un enlace de Calendly con un token opaco dentro, y todo lo que
-- venía detrás —la tabla `booking_token`, la columna `outbox.booking_token`, el
-- seguimiento que preguntaba "¿pudiste agendar tu cita?" y su ajuste— servía
-- para una sola cosa: averiguar de quién era una reserva hecha en una página
-- que no controlábamos.
--
-- Desde que `agendar_cita` reserva por la Scheduling API, la reserva la hacemos
-- nosotros y sabemos de quién es. Nadie emitía ya un token: el seguimiento de
-- reserva llevaba tiempo siendo código inalcanzable, encendido en el panel y
-- sin forma de dispararse. Se va entero en vez de quedarse como adorno.
--
-- Quedan dos avisos automáticos, y son los dos que el panel enseña: el
-- recordatorio previo a la cita y el seguimiento tras el silencio.

-- Las filas de seguimiento de reserva que pudieran quedar de antes: no tienen
-- a quién avisar de qué, porque el enlace del que colgaban ya no se manda.
DELETE FROM outbox WHERE kind = 'booking_followup';

-- SQLite no sabe alterar un CHECK ni soltar una columna citada por uno, así que
-- la tabla se reconstruye. Se conservan filas, ids e índices de lo que sigue vivo.
ALTER TABLE outbox RENAME TO outbox_old;

CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    sent_at TEXT,
    kapso_message_id TEXT,
    slot_utc TEXT,
    kind TEXT NOT NULL
        CHECK (kind IN ('appointment_reminder', 'interest_followup')),
    appointment_event_id TEXT
);

INSERT INTO outbox (id, phone_number_id, contact_phone, text, due_at, sent_at,
                    kapso_message_id, slot_utc, kind, appointment_event_id)
    SELECT id, phone_number_id, contact_phone, text, due_at, sent_at,
           kapso_message_id, slot_utc, kind, appointment_event_id
    FROM outbox_old;

DROP TABLE outbox_old;

CREATE INDEX idx_outbox_due ON outbox (due_at) WHERE sent_at IS NULL;

CREATE UNIQUE INDEX idx_outbox_appointment_event
    ON outbox (appointment_event_id)
    WHERE appointment_event_id IS NOT NULL;

CREATE UNIQUE INDEX idx_outbox_interest_followup
    ON outbox (phone_number_id, contact_phone)
    WHERE kind = 'interest_followup' AND sent_at IS NULL;

-- El ajuste del plazo del seguimiento de reserva se va con él. `app_setting`
-- también se reconstruye: su CHECK citaba la columna, así que no se puede soltar.
ALTER TABLE app_setting RENAME TO app_setting_old;

CREATE TABLE app_setting (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    interest_followup_minutes INTEGER NOT NULL DEFAULT 60
        CHECK (interest_followup_minutes BETWEEN 1 AND 90),
    interest_followup_enabled INTEGER NOT NULL DEFAULT 1
        CHECK (interest_followup_enabled IN (0, 1)),
    appointment_reminder_minutes INTEGER NOT NULL DEFAULT 1440
        CHECK (appointment_reminder_minutes BETWEEN 1 AND 10080),
    appointment_reminder_enabled INTEGER NOT NULL DEFAULT 1
        CHECK (appointment_reminder_enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

INSERT INTO app_setting (id, interest_followup_minutes, interest_followup_enabled,
                         appointment_reminder_minutes, appointment_reminder_enabled, updated_at)
    SELECT id, interest_followup_minutes, interest_followup_enabled,
           appointment_reminder_minutes, appointment_reminder_enabled, updated_at
    FROM app_setting_old;

DROP TABLE app_setting_old;

DROP TABLE booking_token;
