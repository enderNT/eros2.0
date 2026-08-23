interface Props {
  id: string;
  enabled: boolean;
  /** Qué se apaga, en palabras del panel: "el seguimiento", "los recordatorios". */
  what: string;
  onToggle: (enabled: boolean) => Promise<boolean>;
}

/**
 * Encender o apagar del todo una conducta automática.
 *
 * Aparte del slider a propósito. Subir el plazo al máximo no es apagar: es
 * esperar más, y hasta ahora era lo único que podía hacer una clínica que
 * simplemente no quiere que el bot escriba por su cuenta.
 *
 * Apagado no se esconden los controles de plazo, se deshabilitan: quien vuelva
 * mañana tiene que poder ver con qué lapso quedó configurado antes de encender.
 */
export function BehaviourSwitch({ id, enabled, what, onToggle }: Props) {
  return (
    <div className="behaviour-switch">
      <label htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={enabled}
          onChange={(event) => void onToggle(event.target.checked)}
        />{" "}
        Activado
      </label>
      {!enabled && (
        <p className="subtle">
          Apagado: no se enviará {what} a nadie, y lo que quedaba en cola se descartó.
        </p>
      )}
    </div>
  );
}
