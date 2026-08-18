import { useState } from "react";

import { Hint } from "./Hint";

interface Props {
  muted: boolean;
  /** Resolves false when the operator backed out of the confirmation. */
  onSave: (muted: boolean) => Promise<boolean>;
}

export function GlobalKillSwitch({ muted, onSave }: Props) {
  const [draft, setDraft] = useState(muted);
  const changed = draft !== muted;

  async function save() {
    if (!(await onSave(draft))) setDraft(muted);
  }

  return (
    <div className="form-action">
      <label htmlFor="global-muted">
        <strong>Interruptor global</strong>
        <Hint text="Apaga el bot por completo: ningún número, ningún contacto recibe respuesta. Es el «parar todo ahora»; los mensajes siguen llegando a la bandeja de Kapso para que los conteste una persona." />
      </label>
      <label className="toggle-row" htmlFor="global-muted">
        <input
          id="global-muted"
          name="muted"
          type="checkbox"
          checked={draft}
          onChange={(event) => setDraft(event.target.checked)}
        />
        <span>{muted ? "El bot está apagado para todos." : "El bot está activo para todos."}</span>
      </label>
      {changed && (
        <button className="global-save" type="button" onClick={() => void save()}>
          Guardar cambio global
        </button>
      )}
    </div>
  );
}
