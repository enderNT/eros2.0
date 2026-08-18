import { useCallback, useRef, useState } from "react";

/**
 * One shared confirmation gate for the global switches. Returns the dialog's
 * props plus an `ask()` that resolves to the operator's answer.
 */
export function useConfirm() {
  const [open, setOpen] = useState(false);
  const pending = useRef<((answer: boolean) => void) | null>(null);

  const settle = useCallback((answer: boolean) => {
    setOpen(false);
    pending.current?.(answer);
    pending.current = null;
  }, []);

  const ask = useCallback((): Promise<boolean> => {
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      pending.current = resolve;
    });
  }, []);

  return {
    ask,
    dialogProps: {
      open,
      onCancel: () => settle(false),
      onConfirm: () => settle(true),
    },
  };
}
