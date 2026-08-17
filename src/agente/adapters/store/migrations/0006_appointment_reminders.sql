-- Reminders share the durable outbox with booking-link follow-ups, but carry
-- the Calendly event URI so a cancellation can suppress exactly its reminder.
ALTER TABLE outbox ADD COLUMN kind TEXT NOT NULL DEFAULT 'booking_followup'
    CHECK (kind IN ('booking_followup', 'appointment_reminder'));
ALTER TABLE outbox ADD COLUMN appointment_event_id TEXT;

CREATE UNIQUE INDEX idx_outbox_appointment_event
    ON outbox (appointment_event_id)
    WHERE appointment_event_id IS NOT NULL;

ALTER TABLE app_setting ADD COLUMN appointment_reminder_minutes INTEGER NOT NULL DEFAULT 1440
    CHECK (appointment_reminder_minutes BETWEEN 1 AND 10080);
