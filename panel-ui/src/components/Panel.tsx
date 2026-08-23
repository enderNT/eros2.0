import { useCallback, useEffect, useState } from "react";

import { useApi } from "../ApiProvider";
import type {
  Appointment,
  Contact,
  FollowupResult,
  MuteState,
  PanelState,
  ReminderResult,
} from "../types";
import { useConfirm } from "../useConfirm";
import { AppointmentReminderSettings } from "./AppointmentReminderSettings";
import { BookingFollowupControl } from "./BookingFollowupControl";
import { InterestFollowupControl } from "./InterestFollowupControl";
import { ConfirmDialog } from "./ConfirmDialog";
import { ContactList } from "./ContactList";
import { GlobalKillSwitch } from "./GlobalKillSwitch";
import { NumberMuteToggle } from "./NumberMuteToggle";

export function Panel() {
  const { call } = useApi();
  const { ask, dialogProps } = useConfirm();
  const [state, setState] = useState<PanelState | null>(null);

  useEffect(() => {
    call<PanelState>("/state")
      .then(setState)
      .catch(() => undefined);
  }, [call]);

  const patchContact = useCallback((phone: string, patch: Partial<Contact>) => {
    setState((current) =>
      current === null
        ? current
        : {
            ...current,
            contacts: current.contacts.map((contact) =>
              contact.phone === phone ? { ...contact, ...patch } : contact,
            ),
          },
    );
  }, []);

  /** Global switches are confirmed first, then saved; false means "not saved". */
  const saveGlobal = useCallback(
    async (path: string, body: object, patch: Partial<PanelState>): Promise<boolean> => {
      if (!(await ask())) return false;
      try {
        await call(path, body);
      } catch {
        return false;
      }
      setState((current) => (current === null ? current : { ...current, ...patch }));
      return true;
    },
    [ask, call],
  );

  if (state === null) return <p className="loading">Cargando…</p>;

  const contactKey = (contact: Contact) => ({
    phone_number_id: state.phone_number_id,
    contact_phone: contact.phone,
  });

  return (
    <>
      <header>
        <h1>Conversaciones</h1>
      </header>
      {state.error && <p className="error">{state.error}</p>}

      <div id="kill-switch">
        <GlobalKillSwitch
          muted={state.global_muted}
          onSave={(muted) => saveGlobal("/global", { muted }, { global_muted: muted })}
        />
      </div>

      <div id="booking-followup">
        <BookingFollowupControl
          setting={state.booking_followup}
          onSave={(minutes) =>
            saveGlobal(
              "/booking-followup",
              { minutes },
              { booking_followup: { ...state.booking_followup, minutes } },
            )
          }
        />
      </div>

      <div id="interest-followup">
        <InterestFollowupControl
          setting={state.interest_followup}
          onSave={(minutes) =>
            saveGlobal(
              "/interest-followup",
              { minutes },
              { interest_followup: { ...state.interest_followup, minutes } },
            )
          }
          onToggle={(enabled) =>
            saveGlobal(
              "/interest-followup-enabled",
              { enabled },
              { interest_followup: { ...state.interest_followup, enabled } },
            )
          }
        />
      </div>

      <div id="appointment-reminder-settings">
        <AppointmentReminderSettings
          setting={state.appointment_reminder}
          onSave={(minutes) =>
            saveGlobal(
              "/appointment-reminder-settings",
              { minutes },
              { appointment_reminder: { ...state.appointment_reminder, minutes } },
            )
          }
          onToggle={(enabled) =>
            saveGlobal(
              "/appointment-reminder-enabled",
              { enabled },
              { appointment_reminder: { ...state.appointment_reminder, enabled } },
            )
          }
        />
      </div>

      <div id="number-switch">
        <NumberMuteToggle
          phoneNumberId={state.phone_number_id}
          muted={state.number_muted}
          onToggle={async (muted) => {
            await call("/number-mute", { phone_number_id: state.phone_number_id, muted });
            setState((current) => (current === null ? current : { ...current, number_muted: muted }));
          }}
        />
      </div>

      <ContactList
        contacts={state.contacts}
        reminderEnabled={state.appointment_reminder.enabled}
        followupEnabled={state.interest_followup.enabled}
        onMute={async (contact, muted, expiresIn) => {
          const payload = await call<{ mute: MuteState | null }>("/mute", {
            ...contactKey(contact),
            muted,
            expires_in: expiresIn,
          });
          patchContact(contact.phone!, { mute: payload.mute });
        }}
        onReset={async (contact) => {
          const payload = await call<{
            purged: number;
            mute: MuteState | null;
            appointment: Appointment | null;
          }>("/reset", contactKey(contact));
          patchContact(contact.phone!, {
            mute: payload.mute,
            appointment: payload.appointment,
          });
          return payload.purged;
        }}
        onSendReminder={async (contact) => {
          const payload = await call<{
            result: ReminderResult;
            appointment: Appointment | null;
          }>("/appointment-reminder", contactKey(contact));
          patchContact(contact.phone!, { appointment: payload.appointment });
          return payload.result;
        }}
        onSendInterestFollowup={async (contact) => {
          const payload = await call<{ result: FollowupResult }>(
            "/interest-followup-send",
            contactKey(contact),
          );
          return payload.result;
        }}
      />

      <nav className="nav">
        <a href="/admin/traces">Trazas LLM →</a>
      </nav>
      <ConfirmDialog {...dialogProps} />
    </>
  );
}
