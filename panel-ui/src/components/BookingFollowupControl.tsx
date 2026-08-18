import { useState } from "react";

import type { MinuteSetting } from "../types";
import { Hint } from "./Hint";

/** Slider granularities offered to the operator; UI only, never persisted. */
const SLIDER_STEPS = [1, 2, 3, 5, 6, 9, 10, 15, 18, 30, 45, 90];

interface Props {
  setting: MinuteSetting;
  onSave: (minutes: number) => Promise<boolean>;
}

export function BookingFollowupControl({ setting, onSave }: Props) {
  const [draft, setDraft] = useState(setting.minutes);
  const [step, setStep] = useState(1);
  const changed = draft !== setting.minutes;

  async function save() {
    if (!(await onSave(draft))) setDraft(setting.minutes);
  }

  return (
    <div className="form-action booking-followup-control">
      <label htmlFor="booking-followup-slider">
        <strong>Seguimiento de reserva</strong>
        <Hint text="Si el paciente recibe un enlace de agenda y no responde ni confirma la cita, el bot pregunta una sola vez después de este lapso. El ajuste es global y aplica a los enlaces nuevos." />
      </label>
      <p className="subtle">
        Esperar <output id="booking-followup-value">{draft}</output> min antes de preguntar.
      </p>
      <div className="range-row">
        <div className="range-slider">
          <output className="slider-step-count" id="booking-followup-step-count">
            {setting.max / step} pasos de {step} min
          </output>
          <input
            id="booking-followup-slider"
            name="minutes"
            type="range"
            min={setting.min}
            max={setting.max}
            step={step}
            value={draft}
            onChange={(event) => setDraft(Number(event.target.value))}
          />
          <div className="slider-bounds">
            <span>Ahora</span>
            <span>{setting.max} min</span>
          </div>
        </div>
        <label className="slider-stepper" htmlFor="booking-followup-stepper">
          Paso
          <select
            id="booking-followup-stepper"
            aria-label="Paso del slider en minutos"
            value={step}
            onChange={(event) => setStep(Number(event.target.value))}
          >
            {SLIDER_STEPS.map((value) => (
              <option key={value} value={value}>
                {value} min
              </option>
            ))}
          </select>
        </label>
      </div>
      {changed && (
        <button className="global-save" type="button" onClick={() => void save()}>
          Guardar cambio global
        </button>
      )}
      <p className="subtle">
        El paso sólo cambia cuánto avanza el slider; no cambia el tiempo programado.
      </p>
    </div>
  );
}
