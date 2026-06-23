"""Cliente de Chatwoot (T12/T13 · I.chatwoot).

Enviar mensajes salientes y escribir el atributo de conversación `bot_activo`
(usado por el Handoff, V7).
"""

import logging
from functools import lru_cache
from typing import Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)


class ChatwootClient:
    def __init__(self, base_url: str, token: str, account_id: str, http: Optional[httpx.Client] = None):
        self._account = account_id
        self._http = http or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"api_access_token": token, "Content-Type": "application/json"},
            timeout=15.0,
        )

    def enviar_mensaje(self, conversation_id, texto: str) -> dict:
        r = self._http.post(
            f"/api/v1/accounts/{self._account}/conversations/{conversation_id}/messages",
            json={"content": texto, "message_type": "outgoing"},
        )
        r.raise_for_status()
        return r.json()

    def enviar_plantilla(
        self,
        conversation_id,
        *,
        nombre_plantilla: str,
        idioma: str,
        processed_params: dict,
        fallback: str = "",
    ) -> dict:
        """Envía un mensaje de PLANTILLA de WhatsApp (HSM) por Chatwoot.

        Necesario fuera de la ventana de 24h: WhatsApp solo entrega plantillas
        pre-aprobadas. `processed_params` mapea posición→valor ({"1": "...", ...}).
        """
        r = self._http.post(
            f"/api/v1/accounts/{self._account}/conversations/{conversation_id}/messages",
            json={
                "content": fallback,
                "message_type": "outgoing",
                "template_params": {
                    "name": nombre_plantilla,
                    "language": idioma,
                    "processed_params": processed_params,
                },
            },
        )
        r.raise_for_status()
        return r.json()

    def set_atributo(self, conversation_id, key: str, value) -> dict:
        r = self._http.post(
            f"/api/v1/accounts/{self._account}/conversations/{conversation_id}/custom_attributes",
            json={"custom_attributes": {key: value}},
        )
        r.raise_for_status()
        return r.json()


@lru_cache(maxsize=1)
def get_chatwoot() -> Optional[ChatwootClient]:
    if not (settings.chatwoot_base_url and settings.chatwoot_api_token and settings.chatwoot_account_id):
        return None
    return ChatwootClient(
        settings.chatwoot_base_url, settings.chatwoot_api_token, settings.chatwoot_account_id
    )
