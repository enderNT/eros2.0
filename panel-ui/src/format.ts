/** "90 min" / "2 horas" / "3 días" — the server used to render this label. */
export function minuteLabel(minutes: number): string {
  if (minutes >= 1440 && minutes % 1440 === 0) {
    const days = minutes / 1440;
    return `${days} día${days === 1 ? "" : "s"}`;
  }
  if (minutes >= 60 && minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hora${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} min`;
}

/** Timestamps arrive as UTC ISO strings and are shown in the operator's zone. */
export function timestamp(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
