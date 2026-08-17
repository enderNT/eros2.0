-- Attribution for Calendly bookings (TASKS T9b).
-- The patient books on Calendly's own page, so the only thing that comes back
-- in the webhook is whatever we put in the link. We put an opaque token —
-- never the phone number, which would travel in a URL and end up in Calendly's
-- logs — and resolve it here.

CREATE TABLE booking_token (
    token TEXT PRIMARY KEY,
    phone_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    slot_utc TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_booking_token_contact
    ON booking_token (phone_number_id, contact_phone);
