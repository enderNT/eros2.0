"""Las suscripciones de webhook de Calendly: listar, borrar y crear.

Existe porque la URL cambia. En local es un túnel que se renumera cada vez que
lo reinicias, y cada URL muerta deja una suscripción reintentando contra la
nada. Hacerlo a mano son tres `curl` con cuatro URIs largas dentro, y el error
típico —mandar el literal `<USER_URI>`, o crear la segunda sin borrar la
primera— sólo se nota días después, cuando una cancelación no llega.

Todo sale de `.env` menos la URL de destino, que es lo único que el entorno no
puede saber: depende de qué túnel levantaste o de qué dominio te dio Coolify.

    python scripts/calendly_webhooks.py listar
    python scripts/calendly_webhooks.py borrar --todos
    python scripts/calendly_webhooks.py borrar <uuid> [<uuid>...]
    python scripts/calendly_webhooks.py crear https://xxxx.ngrok-free.app

`crear` reutiliza `CALENDLY_SIGNING_KEY` del `.env`. Tiene que ser la misma con
la que corre la app: Calendly firma con ella y la app verifica con ella, así que
dos valores distintos dan 401 en cada entrega y ningún otro síntoma.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

API = "https://api.calendly.com"
EVENTS = ["invitee.created", "invitee.canceled"]
RUTA = "/webhook/calendly"
ENV = Path(__file__).resolve().parents[1] / ".env"

ROJO, VERDE, AMARILLO, GRIS, FIN = "\033[31m", "\033[32m", "\033[33m", "\033[90m", "\033[0m"


def _env(nombre: str) -> str:
    """Del entorno si está, del `.env` si no.

    Se lee a mano en vez de con `source`: los valores llevan espacios y comas
    —la dirección de la clínica, el mensaje de crisis— y el shell los parte.
    """
    if valor := os.environ.get(nombre):
        return valor
    if not ENV.exists():
        return ""
    for linea in ENV.read_text(encoding="utf-8").splitlines():
        if linea.startswith(f"{nombre}="):
            return linea.split("=", 1)[1].strip()
    return ""


def _pedir(
    metodo: str, url: str, cuerpo: dict | None = None, params: dict | None = None
) -> tuple[int, dict]:
    """Una llamada a la API. `httpx` y no `urllib` por los certificados: en macOS
    `urllib` no encuentra el almacén del sistema y falla con `CERTIFICATE_VERIFY_FAILED`."""
    try:
        respuesta = httpx.request(
            metodo,
            url,
            json=cuerpo,
            params=params,
            headers={"Authorization": f"Bearer {_token()}"},
            timeout=30,
        )
    except httpx.HTTPError as error:
        print(f"{ROJO}no se pudo hablar con Calendly: {error}{FIN}")
        raise SystemExit(1) from error
    if not respuesta.content:
        return respuesta.status_code, {}
    try:
        return respuesta.status_code, respuesta.json()
    except ValueError:
        return respuesta.status_code, {"raw": respuesta.text}


_TOKEN: str | None = None


def _token() -> str:
    global _TOKEN  # noqa: PLW0603
    if _TOKEN is None:
        _TOKEN = _env("CALENDLY_TOKEN")
        if not _TOKEN:
            print(f"{ROJO}falta CALENDLY_TOKEN (ni en el entorno ni en .env){FIN}")
            raise SystemExit(1)
    return _TOKEN


_IDENTIDAD: tuple[str, str] | None = None


def _identidad() -> tuple[str, str]:
    """`(user_uri, organization_uri)` de la cuenta dueña del token.

    Se piden a la API en vez de guardarlas en `.env` porque son derivables del
    token, y un `.env` con una URI de otra cuenta es un fallo mudo: la llamada
    responde 200 y lista las suscripciones de nadie.
    """
    global _IDENTIDAD  # noqa: PLW0603
    if _IDENTIDAD is None:
        estado, cuerpo = _pedir("GET", f"{API}/users/me")
        if estado != 200:
            print(f"{ROJO}/users/me devolvió {estado}: {json.dumps(cuerpo)[:300]}{FIN}")
            raise SystemExit(1)
        recurso = cuerpo["resource"]
        _IDENTIDAD = (recurso["uri"], recurso["current_organization"])
    return _IDENTIDAD


def _suscripciones() -> list[dict]:
    """Las de los dos ámbitos.

    `scope` es obligatorio y no admite "los dos", así que son dos llamadas. Y
    `user` sólo vale con `scope=user`: mandarlo en la de organización da un 400
    diciendo `is not applicable`, no una lista vacía.
    """
    usuario, organizacion = _identidad()
    encontradas: list[dict] = []
    for ambito in ("user", "organization"):
        params = {"scope": ambito, "organization": organizacion}
        if ambito == "user":
            params["user"] = usuario
        estado, cuerpo = _pedir("GET", f"{API}/webhook_subscriptions", params=params)
        if estado != 200:
            print(f"{AMARILLO}scope={ambito}: {estado} {json.dumps(cuerpo)[:200]}{FIN}")
            continue
        encontradas += cuerpo.get("collection") or []
    return encontradas


def _uuid(suscripcion: dict) -> str:
    return suscripcion["uri"].rsplit("/", 1)[-1]


def cmd_listar(_args: argparse.Namespace) -> int:
    suscripciones = _suscripciones()
    if not suscripciones:
        print("(ninguna suscripción registrada)")
        return 0
    for suscripcion in suscripciones:
        estado = suscripcion.get("state", "?")
        color = VERDE if estado == "active" else AMARILLO
        print(f"{color}{estado}{FIN}  {_uuid(suscripcion)}")
        print(f"  url    {suscripcion.get('callback_url')}")
        print(f"  scope  {suscripcion.get('scope')}")
        print(f"  events {', '.join(suscripcion.get('events') or [])}")
        print(f"  creada {suscripcion.get('created_at')}")
        # `retry_started_at` es la señal de que la URL murió: Calendly lleva
        # desde esa fecha entregando contra un sitio que no contesta.
        if reintentos := suscripcion.get("retry_started_at"):
            print(f"  {AMARILLO}reintentando desde {reintentos} — la URL no responde{FIN}")
        print()
    print(f"{GRIS}{len(suscripciones)} suscripción(es){FIN}")
    return 0


def cmd_borrar(args: argparse.Namespace) -> int:
    if args.todos:
        objetivos = [_uuid(s) for s in _suscripciones()]
        if not objetivos:
            print("(no había ninguna que borrar)")
            return 0
    elif args.uuids:
        objetivos = [u.rsplit("/", 1)[-1] for u in args.uuids]
    else:
        print(f"{ROJO}dime qué borrar: uno o más uuid, o --todos{FIN}")
        return 1
    fallos = 0
    for uuid in objetivos:
        estado, cuerpo = _pedir("DELETE", f"{API}/webhook_subscriptions/{uuid}")
        # 204 es borrada; 404 es que ya no estaba, que para este script es el
        # mismo resultado y no merece un rojo.
        if estado in (204, 404):
            nota = "" if estado == 204 else f" {GRIS}(ya no estaba){FIN}"
            print(f"{VERDE}borrada{FIN}  {uuid}{nota}")
        else:
            fallos += 1
            print(f"{ROJO}error {estado}{FIN}  {uuid}  {json.dumps(cuerpo)[:200]}")
    return 1 if fallos else 0


def cmd_crear(args: argparse.Namespace) -> int:
    base = args.url.rstrip("/")
    if not base.startswith("https://"):
        print(
            f"{ROJO}la URL tiene que ser https:// pública."
            f" Calendly no entrega a http ni a localhost.{FIN}"
        )
        return 1
    destino = base if base.endswith(RUTA) else base + RUTA

    llave = _env("CALENDLY_SIGNING_KEY")
    if not llave:
        print(f"{ROJO}falta CALENDLY_SIGNING_KEY. Genera una con: openssl rand -hex 32{FIN}")
        print(f"{GRIS}y ponla en .env ANTES de crear la suscripción: Calendly firma con ella{FIN}")
        return 1

    if (vivas := _suscripciones()) and not args.forzar:
        print(f"{AMARILLO}ya hay {len(vivas)} suscripción(es):{FIN}")
        for suscripcion in vivas:
            print(f"  {_uuid(suscripcion)}  {suscripcion.get('callback_url')}")
        print(
            f"\n{AMARILLO}Calendly entrega a TODAS las que estén activas.{FIN}"
            "\nBórralas primero (borrar --todos), o repite con --forzar si de verdad"
            " quieres varias."
        )
        return 1

    usuario, organizacion = _identidad()
    estado, cuerpo = _pedir(
        "POST",
        f"{API}/webhook_subscriptions",
        {
            "url": destino,
            "events": EVENTS,
            "organization": organizacion,
            "user": usuario,
            "scope": "user",
            "signing_key": llave,
        },
    )
    if estado not in (200, 201):
        print(f"{ROJO}Calendly rechazó la suscripción ({estado}){FIN}")
        print(json.dumps(cuerpo, indent=2)[:800])
        return 1
    creada = cuerpo.get("resource", {})
    print(f"{VERDE}creada{FIN}  {_uuid(creada)}")
    print(f"  url    {creada.get('callback_url')}")
    print(f"  events {', '.join(creada.get('events') or [])}")
    print(
        f"\n{GRIS}Comprueba que la app rechaza lo que no viene firmado:{FIN}"
        f"\n  curl -s -o /dev/null -w '%{{http_code}}\\n' -X POST {destino} -d '{{}}'"
        f"\n{GRIS}Tiene que decir 401. Si dice otra cosa, la app no está viendo"
        f" la misma CALENDLY_SIGNING_KEY.{FIN}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    verbos = parser.add_subparsers(dest="comando", required=True)

    verbos.add_parser("listar", help="las suscripciones registradas").set_defaults(func=cmd_listar)

    borrar = verbos.add_parser("borrar", help="borrar por uuid, o todas")
    borrar.add_argument("uuids", nargs="*", help="uuid o uri completa")
    borrar.add_argument("--todos", action="store_true", help="borrar todas las que haya")
    borrar.set_defaults(func=cmd_borrar)

    crear = verbos.add_parser("crear", help="registrar una nueva para esta URL")
    crear.add_argument("url", help="https://xxxx.ngrok-free.app (la ruta se añade sola)")
    crear.add_argument("--forzar", action="store_true", help="crear aunque ya haya otras")
    crear.set_defaults(func=cmd_crear)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
