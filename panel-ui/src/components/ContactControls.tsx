import { useState } from "react";

import { timestamp } from "../format";
import type { Contact, ReminderResult } from "../types";
import { Hint } from "./Hint";

interface Props {
  contact: Contact;
  onMute: (muted: boolean, expiresIn: number | null) => Promise<void>;
  onReset: () => Promise<number>;
  onSendReminder: () => Promise<ReminderResult>;
}

const REMINDER_MESSAGE: Record<ReminderResult, { text: string; tone: "subtle" | "error" }> = {
  sent: { text: "Recordatorio enviado.", tone: "subtle" },
  muted: {
    text: "No se envió: el bot está silenciado para este contacto.",
    tone: "error",
  },
  failed: { text: "No se pudo enviar. Revisa la conexión de WhatsApp.", tone: "error" },
  missing: { text: "No hay un recordatorio pendiente para enviar.", tone: "subtle" },
  already_sent: { text: "No hay un recordatorio pendiente para enviar.", tone: "subtle" },
};

export function ContactControls({ contact, onMute, onReset, onSendReminder }: Props) {
  const [expiresIn, setExpiresIn] = useState("");
  const [purged, setPurged] = useState<number | null>(null);
  const [reminder, setReminder] = useState<ReminderResult | null>(null);

  async function sendReminder() {
    if (!window.confirm("Se enviará ahora el recordatorio pendiente a esta persona. ¿Continuar?")) {
      return;
    }
    setReminder(await onSendReminder());
  }

  async function reset() {
    const warning =
      "Se borra todo el historial de este contacto y el bot vuelve a responderle desde cero." +
      " No se puede deshacer. ¿Continuar?";
    if (!window.confirm(warning)) return;
    setPurged(await onReset());
    setReminder(null);
  }

  return (
    <div className="contact-controls">
      <div className="form-action">
        <label>
          <strong>Bot para contacto</strong>
          {contact.mute?.muted_until && ` — hasta ${timestamp(contact.mute.muted_until)}`}
          <Hint text="Silencia al bot sólo para esta persona. No vuelve solo: sigue callado hasta que lo actives aquí, aunque el paciente escriba de nuevo mañana. El bot también se silencia solo cuando escala a una persona o detecta una situación de riesgo." />
        </label>
        {contact.mute && <p className="muted">Silenciado. Esta persona sólo habla con humanos.</p>}
        {contact.mute ? (
          <button type="button" onClick={() => void onMute(false, null)}>
            Activar bot
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void onMute(true, expiresIn ? Number(expiresIn) : null)}
            >
              Silenciar bot
            </button>
            <select
              aria-label="Vencimiento del silencio"
              value={expiresIn}
              onChange={(event) => setExpiresIn(event.target.value)}
            >
              <option value="">Sin vencimiento</option>
              <option value="3600">1 hora</option>
              <option value="86400">1 día</option>
            </select>
          </>
        )}
      </div>

      {contact.appointment && (
        <div className="form-action appointment-reminder-trigger">
          <strong>Recordatorio de cita</strong>
          <p className="subtle">
            Hay una cita confirmada. Puedes enviar ahora el recordatorio pendiente sólo a esta
            persona.
          </p>
          {reminder && (
            <p className={REMINDER_MESSAGE[reminder].tone}>{REMINDER_MESSAGE[reminder].text}</p>
          )}
          {reminder !== "sent" && (
            <button type="button" onClick={() => void sendReminder()}>
              Enviar recordatorio ahora
            </button>
          )}
        </div>
      )}

      <div className="form-action">
        <label>
          <strong>Borrar historial</strong>
          <Hint text="Borra todo lo que guardamos de esta persona: mensajes, resumen, perfil, citas registradas y enlaces de agenda. El bot vuelve a tratarla como si escribiera por primera vez. También reactiva el bot si estaba silenciado. No se puede deshacer, y no cancela nada en Calendly ni borra la conversación en Kapso." />
        </label>
        {purged !== null && (
          <p className="subtle">
            {purged ? `Listo: ${purged} registros borrados.` : "No había nada guardado."}
          </p>
        )}
        <button type="button" className="danger" onClick={() => void reset()}>
          Borrar historial
        </button>
      </div>
    </div>
  );
}
