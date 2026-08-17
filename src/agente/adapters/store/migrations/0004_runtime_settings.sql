CREATE TABLE app_setting (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    booking_followup_minutes INTEGER NOT NULL CHECK (booking_followup_minutes BETWEEN 1 AND 90),
    updated_at TEXT NOT NULL
);
