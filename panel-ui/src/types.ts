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

/**
 * Un aviso automático: cuánto se espera, y si se manda siquiera.
 *
 * Son dos, y son los dos que el bot manda por iniciativa propia: el seguimiento
 * tras el silencio y el recordatorio previo a la cita. Cada uno con su plazo y
 * su interruptor, porque una clínica puede querer uno sin el otro.
 */
export interface MinuteSetting {
  minutes: number;
  min: number;
  max: number;
  enabled: boolean;
}

export interface PanelState {
  phone_number_id: string;
  error: string | null;
  global_muted: boolean;
  number_muted: boolean;
  interest_followup: MinuteSetting;
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
