import { useState, type FormEvent } from "react";

import { ApiError } from "../api";
import { useApi } from "../ApiProvider";

export function Login({ onAuthed }: { onAuthed: () => void }) {
  const { call } = useApi();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await call("/login", { password });
      onAuthed();
    } catch (failure) {
      // A wrong password is the expected answer here, not a broken panel:
      // it belongs next to the field, not in the red banner up top.
      setError(
        failure instanceof ApiError && failure.status === 401
          ? "Contraseña inválida"
          : "No se pudo iniciar sesión.",
      );
    }
  }

  return (
    <div className="page">
      <header>
        <h1>Panel</h1>
      </header>
      <div className="card">
        <form onSubmit={submit}>
          <label htmlFor="password">Contraseña</label>
          <input
            type="password"
            id="password"
            name="password"
            required
            autoFocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="submit">Entrar</button>
          {error && <p className="error">{error}</p>}
        </form>
      </div>
    </div>
  );
}
