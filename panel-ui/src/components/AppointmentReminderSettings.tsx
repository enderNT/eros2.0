import { useState } from "react";

import { minuteLabel } from "../format";
import type { ToggleableMinuteSetting } from "../types";
import { BehaviourSwitch } from "./BehaviourSwitch";
import { Hint } from "./Hint";

/** Shortcuts for testing and for the values actually used day to day. */
const PRESETS: ReadonlyArray<[number, string]> = [
  [1, "1 min"],
  [2, "2 min"],
  [30, "30 min"],
  [60, "1 h"],
  [120, "2 h"],
  [720, "12 h"],
  [1440, "24 h"],
  [2880, "48 h"],
  [4320, "72 h"],
];

interface Props {
  setting: ToggleableMinuteSetting;
  onSave: (minutes: number) => Promise<boolean>;
  onToggle: (enabled: boolean) => Promise<boolean>;
}

export function AppointmentReminderSettings({ setting, onSave, onToggle }: Props) {
  const [draft, setDraft] = useState(String(setting.minutes));
  const minutes = Number(draft);
  const valid = Number.isInteger(minutes) && minutes >= setting.min && minutes <= setting.max;
  const changed = valid && minutes !== setting.minutes;

  async function save() {
    if (!(await onSave(minutes))) setDraft(String(setting.minutes));
  }

  return (
    <div className="form-action booking-followup-control">
      <label htmlFor="appointment-reminder-minutes">
        <strong>Recordatorio de cita</strong>
        <Hint text="Envía un recordatorio fijo antes de cada cita confirmada. Es un ajuste global. Al guardarlo, las citas futuras que todavía no reciben recordatorio se recalculan con este nuevo lapso." />
      </label>
      <BehaviourSwitch
        id="appointment-reminder-enabled"
        enabled={setting.enabled}
        what="ningún recordatorio"
        onToggle={onToggle}
      />
      <p className="subtle">
        Enviar{" "}
        <output id="appointment-reminder-value">
          {valid ? minuteLabel(minutes) : minuteLabel(setting.minutes)}
        </output>{" "}
        antes de la cita.
      </p>
      <label className="reminder-minutes" htmlFor="appointment-reminder-minutes">
        Minutos antes de la cita
        <input
          id="appointment-reminder-minutes"
          name="minutes"
          type="number"
          min={setting.min}
          max={setting.max}
          step={1}
          value={draft}
          disabled={!setting.enabled}
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>
      <div className="reminder-presets" aria-label="Tiempos sugeridos">
        {PRESETS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className="secondary"
            disabled={!setting.enabled}
            onClick={() => setDraft(String(value))}
          >
            {label}
          </button>
        ))}
      </div>
      {changed && setting.enabled && (
        <button className="global-save" type="button" onClick={() => void save()}>
          Guardar cambio global
        </button>
      )}
      <p className="subtle">
        Escribe cualquier valor entre 1 minuto y 7 días; los botones son accesos directos para
        pruebas y valores habituales.
      </p>
    </div>
  );
}
