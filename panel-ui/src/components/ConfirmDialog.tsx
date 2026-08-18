import { useEffect, useRef } from "react";

interface Props {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * The single "¿Guardar cambio global?" modal. It closes before the change is
 * applied, unconditionally: a modal that stays open on a click looks frozen
 * and hides whatever went wrong behind it.
 */
export function ConfirmDialog({ open, onCancel, onConfirm }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog className="confirm-dialog" ref={ref} onCancel={onCancel}>
      <form method="dialog">
        <h2>¿Guardar cambio global?</h2>
        <p>Este cambio afectará el comportamiento del bot para todos los contactos.</p>
        <div className="dialog-actions">
          <button type="button" value="cancel" className="secondary" onClick={onCancel}>
            Cancelar
          </button>
          <button type="button" onClick={onConfirm}>
            Guardar
          </button>
        </div>
      </form>
    </dialog>
  );
}
