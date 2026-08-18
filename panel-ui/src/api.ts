/** Thrown when the server answered, but refused the change. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Thrown when the request never reached a server at all. */
export class NetworkError extends Error {}

const BASE = "/admin/api";

export async function request<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new NetworkError("No se pudo contactar al servidor. ¿Sigue corriendo el contenedor?");
  }
  if (!response.ok) {
    throw new ApiError(response.status, `El servidor rechazó el cambio (HTTP ${response.status}).`);
  }
  return (await response.json()) as T;
}
