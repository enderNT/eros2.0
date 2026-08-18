export interface MuteState {
  muted_at: string;
  muted_until: string | null;
}

export interface Appointment {
  slot_utc: string;
  status: string;
}

export interface Contact {
  conversation_id: string;
  name: string | null;
  phone: string | null;
  masked_phone: string | null;
  last_activity_at: string | null;
  status: string | null;
  conversation_count: number;
  mute: MuteState | null;
  appointment: Appointment | null;
}

export interface MinuteSetting {
  minutes: number;
  min: number;
  max: number;
}

export interface PanelState {
  phone_number_id: string;
  error: string | null;
  global_muted: boolean;
  number_muted: boolean;
  booking_followup: MinuteSetting;
  appointment_reminder: MinuteSetting;
  contacts: Contact[];
}

export interface TraceRow {
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  created_at: string;
}

/** What `send_now` reports back for a single contact's pending reminder. */
export type ReminderResult = "sent" | "muted" | "failed" | "missing" | "already_sent";
