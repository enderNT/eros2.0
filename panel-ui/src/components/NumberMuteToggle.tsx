import { Hint } from "./Hint";

interface Props {
  phoneNumberId: string;
  muted: boolean;
  onToggle: (muted: boolean) => Promise<void>;
}

export function NumberMuteToggle({ phoneNumberId, muted, onToggle }: Props) {
  return (
    <div className="form-action">
      <label>
        <strong>Número</strong>: {phoneNumberId.slice(0, 8)}
        <Hint text="Apaga el bot para TODOS los contactos de este número de WhatsApp — no sólo para una persona. Útil si hay que frenar el número entero mientras se revisa algo." />
      </label>
      {muted && <p className="muted">El bot no responde a nadie en este número.</p>}
      <button type="button" onClick={() => void onToggle(!muted)}>
        {muted ? "Desmutar número" : "Mutar número"}
      </button>
    </div>
  );
}
