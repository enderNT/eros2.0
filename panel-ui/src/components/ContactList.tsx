import { timestamp } from "../format";
import type { Contact, FollowupResult, ReminderResult } from "../types";
import { ContactControls } from "./ContactControls";
import { Hint } from "./Hint";

interface Props {
  contacts: Contact[];
  onMute: (contact: Contact, muted: boolean, expiresIn: number | null) => Promise<void>;
  onReset: (contact: Contact) => Promise<number>;
  onSendReminder: (contact: Contact) => Promise<ReminderResult>;
  onSendInterestFollowup: (contact: Contact) => Promise<FollowupResult>;
}

function StatusBadge({ status }: { status: string | null }) {
  if (status === "active") return <span className="badge badge-active">abierta</span>;
  if (status === "ended") return <span className="badge badge-ended">cerrada</span>;
  return <>{status || "—"}</>;
}

export function ContactList({
  contacts,
  onMute,
  onReset,
  onSendReminder,
  onSendInterestFollowup,
}: Props) {
  return (
    <table id="conv-list">
      <thead>
        <tr>
          <th>
            Contacto
            <Hint text="Una fila por persona. Kapso puede tener varias conversaciones del mismo número; aquí se muestran agrupadas, con la más reciente." />
          </th>
          <th>Última actividad</th>
          <th>
            Estado
            <Hint text="Estado de la conversación en Kapso, no del bot. Kapso cierra una conversación tras 24 h sin mensajes y abre otra con el siguiente mensaje: «cerrada» sólo significa que pasó ese tiempo. El bot responde igual." />
          </th>
        </tr>
      </thead>
      <tbody>
        {contacts.length === 0 && (
          <tr>
            <td colSpan={3}>No hay conversaciones.</td>
          </tr>
        )}
        {contacts.map((contact) => (
          <Row
            key={contact.conversation_id}
            contact={contact}
            onMute={onMute}
            onReset={onReset}
            onSendReminder={onSendReminder}
            onSendInterestFollowup={onSendInterestFollowup}
          />
        ))}
      </tbody>
    </table>
  );
}

function Row({
  contact,
  onMute,
  onReset,
  onSendReminder,
  onSendInterestFollowup,
}: { contact: Contact } & Omit<Props, "contacts">) {
  return (
    <>
      <tr className={contact.phone ? "contact-row" : undefined}>
        <td>
          <strong>{contact.name || "?"}</strong>
          <br />
          <small>{contact.masked_phone}</small>
          {contact.conversation_count > 1 && (
            <>
              <br />
              <small className="subtle">{contact.conversation_count} conversaciones en Kapso</small>
            </>
          )}
        </td>
        <td>
          <small>{timestamp(contact.last_activity_at)}</small>
        </td>
        <td>
          <StatusBadge status={contact.status} />
        </td>
      </tr>
      {contact.phone && (
        <tr className="contact-controls-row">
          <td colSpan={3}>
            <ContactControls
              contact={contact}
              onMute={(muted, expiresIn) => onMute(contact, muted, expiresIn)}
              onReset={() => onReset(contact)}
              onSendReminder={() => onSendReminder(contact)}
              onSendInterestFollowup={() => onSendInterestFollowup(contact)}
            />
          </td>
        </tr>
      )}
    </>
  );
}
