import { useState } from "react";

import type { ToggleableMinuteSetting } from "../types";
import { BehaviourSwitch } from "./BehaviourSwitch";
import { Hint } from "./Hint";

/** Slider granularities offered to the operator; UI only, never persisted. */
const SLIDER_STEPS = [1, 2, 3, 5, 6, 9, 10, 15, 18, 30, 45, 90];

interface Props {
  setting: ToggleableMinuteSetting;
  onSave: (minutes: number) => Promise<boolean>;
  onToggle: (enabled: boolean) => Promise<boolean>;
}

/**
 * Hermano del control de seguimiento de reserva, y a propósito no el mismo.
 *
 * Aquel espera a quien ya tenía un horario en la mano; éste, a quien preguntó y
 * se enfrió antes de llegar a agendar. Son dos plazos porque son dos decisiones
 * distintas de la clínica: a quien abandonó una reserva se le escribe antes que
 * a quien sólo estaba mirando.
 */
export function InterestFollowupControl({ setting, onSave, onToggle }: Props) {
  const [draft, setDraft] = useState(setting.minutes);
  const [step, setStep] = useState(1);
  const changed = draft !== setting.minutes;

  async function save() {
    if (!(await onSave(draft))) setDraft(setting.minutes);
  }

  return (
    <div className="form-action booking-followup-control">
      <label htmlFor="interest-followup-slider">
        <strong>Seguimiento de interés</strong>
        <Hint text="Para quien preguntó por la clínica y dejó de responder sin llegar a agendar. El bot escribe una sola vez después de este lapso, y no lo hace si la persona contesta antes, si ya tiene cita, o si la conversación pasó a una persona del equipo. El ajuste es global." />
      </label>
      <BehaviourSwitch
        id="interest-followup-enabled"
        enabled={setting.enabled}
        what="ningún seguimiento"
        onToggle={onToggle}
      />
      <p className="subtle">
        Esperar <output id="interest-followup-value">{draft}</output> min antes de escribir.
      </p>
      <div className="range-row">
        <div className="range-slider">
          <output className="slider-step-count" id="interest-followup-step-count">
            {Math.round(setting.max / step)} pasos de {step} min
          </output>
          <input
            id="interest-followup-slider"
            name="minutes"
            type="range"
            min={setting.min}
            max={setting.max}
            step={step}
            value={draft}
            disabled={!setting.enabled}
            onChange={(event) => setDraft(Number(event.target.value))}
          />
          <div className="slider-bounds">
            <span>{setting.min} min</span>
            <span>{setting.max} min</span>
          </div>
        </div>
        <label className="slider-stepper" htmlFor="interest-followup-stepper">
          Paso
          <select
            id="interest-followup-stepper"
            aria-label="Paso del slider de seguimiento de interés en minutos"
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
      {changed && setting.enabled && (
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
