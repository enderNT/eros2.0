import { useCallback, useEffect, useState } from "react";

import { ApiProvider, useApi } from "./ApiProvider";
import { Login } from "./components/Login";
import { Panel } from "./components/Panel";
import { Traces } from "./components/Traces";

export function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const signOut = useCallback(() => setAuthed(false), []);

  return (
    <ApiProvider onUnauthorized={signOut}>
      <div className="page">
        <Routed authed={authed} setAuthed={setAuthed} />
      </div>
    </ApiProvider>
  );
}

function Routed({
  authed,
  setAuthed,
}: {
  authed: boolean | null;
  setAuthed: (authed: boolean) => void;
}) {
  const { call } = useApi();

  useEffect(() => {
    call<{ authed: boolean }>("/session")
      .then((payload) => setAuthed(payload.authed))
      .catch(() => setAuthed(false));
  }, [call, setAuthed]);

  if (authed === null) return <p className="loading">Cargando…</p>;
  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;
  // Two screens, two URLs, no router: the panel is one page plus a trace list.
  return window.location.pathname.startsWith("/admin/traces") ? <Traces /> : <Panel />;
}
