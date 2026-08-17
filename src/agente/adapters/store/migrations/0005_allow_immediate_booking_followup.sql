ALTER TABLE app_setting RENAME TO app_setting_old;

CREATE TABLE app_setting (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    booking_followup_minutes INTEGER NOT NULL CHECK (booking_followup_minutes BETWEEN 0 AND 90),
    updated_at TEXT NOT NULL
);

INSERT INTO app_setting (id, booking_followup_minutes, updated_at)
    SELECT id, booking_followup_minutes, updated_at FROM app_setting_old;

DROP TABLE app_setting_old;
