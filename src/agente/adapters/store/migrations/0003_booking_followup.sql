ALTER TABLE outbox ADD COLUMN booking_token TEXT;
ALTER TABLE outbox ADD COLUMN slot_utc TEXT;

CREATE UNIQUE INDEX idx_outbox_booking_token
    ON outbox (booking_token)
    WHERE booking_token IS NOT NULL;
