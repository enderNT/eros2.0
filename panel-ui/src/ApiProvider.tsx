import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import { ApiError, request } from "./api";

interface Api {
  call: <T>(path: string, body?: unknown) => Promise<T>;
}

const Context = createContext<Api | null>(null);

/**
 * Wraps every request so a failure is visible. A save that dies silently is
 * what made this panel feel broken: the UI just sat there. Any failed request
 * now says so on screen, no DevTools needed.
 */
export function ApiProvider({
  children,
  onUnauthorized,
}: {
  children: ReactNode;
  onUnauthorized: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const call = useCallback(
    async <T,>(path: string, body?: unknown): Promise<T> => {
      setError(null);
      try {
        return await request<T>(path, body);
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 401) {
          onUnauthorized();
        } else {
          setError(failure instanceof Error ? failure.message : String(failure));
        }
        throw failure;
      }
    },
    [onUnauthorized],
  );

  return (
    <Context.Provider value={{ call }}>
      <p id="save-error" className="save-error" role="alert" hidden={error === null}>
        {error}
      </p>
      {children}
    </Context.Provider>
  );
}

export function useApi(): Api {
  const api = useContext(Context);
  if (api === null) throw new Error("useApi outside ApiProvider");
  return api;
}
