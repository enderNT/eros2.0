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

/**
 * Un ajuste de plazo que además se puede apagar entero.
 *
 * No todos lo son: el seguimiento de reserva sigue siendo sólo un plazo. Los dos
 * que sí — el seguimiento tras el silencio y el recordatorio previo a la cita —
 * son los que el bot manda por iniciativa propia, y son justo los que una
 * clínica puede querer que no salgan nunca.
 */
export interface ToggleableMinuteSetting extends MinuteSetting {
  enabled: boolean;
}

export interface PanelState {
  phone_number_id: string;
  error: string | null;
  global_muted: boolean;
  number_muted: boolean;
  booking_followup: MinuteSetting;
  interest_followup: ToggleableMinuteSetting;
  appointment_reminder: ToggleableMinuteSetting;
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
export type ReminderResult =
  | "sent"
  | "muted"
  | "failed"
  | "missing"
  | "already_sent"
  /** El interruptor global está apagado, así que el botón por contacto no manda. */
  | "disabled";

/**
 * Lo que devuelve el envío manual del seguimiento de interés.
 *
 * Comparte casi todos los valores con `ReminderResult` y añade `booked`, que
 * aquí sí puede pasar: entre programarlo y mandarlo, la persona pudo agendar —
 * y entonces preguntarle si sigue ahí sobra.
 */
export type FollowupResult = ReminderResult | "booked";
