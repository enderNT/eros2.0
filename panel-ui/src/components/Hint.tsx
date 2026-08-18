/**
 * Tap-friendly inline help. `<details>` works on a phone without hover, which
 * a tooltip does not — the panel's real moment of use is the psychologist on
 * their phone, so every hint must open with a thumb.
 */
export function Hint({ text }: { text: string }) {
  return (
    <details className="hint">
      <summary title="Qué es esto" aria-label="Qué es esto">
        i
      </summary>
      <p>{text}</p>
    </details>
  );
}
