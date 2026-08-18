import { useEffect, useState } from "react";

import { useApi } from "../ApiProvider";
import { timestamp } from "../format";
import type { TraceRow } from "../types";

export function Traces() {
  const { call } = useApi();
  const [traces, setTraces] = useState<TraceRow[] | null>(null);

  useEffect(() => {
    call<{ traces: TraceRow[] }>("/traces")
      .then((payload) => setTraces(payload.traces))
      .catch(() => setTraces([]));
  }, [call]);

  return (
    <>
      <header>
        <h1>Trazas LLM</h1>
      </header>
      <nav className="nav">
        <a href="/admin">← Conversaciones</a>
      </nav>
      <table id="trace-list">
        <thead>
          <tr>
            <th>Modelo</th>
            <th>Tokens in/out</th>
            <th>Tiempo</th>
          </tr>
        </thead>
        <tbody>
          {traces === null && (
            <tr>
              <td colSpan={3} className="loading">
                Cargando…
              </td>
            </tr>
          )}
          {traces?.length === 0 && (
            <tr>
              <td colSpan={3}>Todavía no hay turnos registrados.</td>
            </tr>
          )}
          {traces?.map((row, index) => (
            <tr key={index}>
              <td>{row.model}</td>
              <td>
                {row.tokens_in}/{row.tokens_out} ms {row.latency_ms}
              </td>
              <td>
                <small>{timestamp(row.created_at)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
