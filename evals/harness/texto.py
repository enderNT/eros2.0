"""Comprobaciones de texto tolerantes con la forma, estrictas con el dato.

Un caso no debe fallar porque el bot escribió "$2,000" en vez de "2000 pesos",
ni pasar porque escribió un número parecido. Estas funciones normalizan acentos,
espacios y separadores de millar, y nada más.
"""

from __future__ import annotations

import re
import unicodedata


def normaliza(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto.lower())
    plano = "".join(char for char in plano if not unicodedata.combining(char))
    plano = plano.replace(" ", " ")
    # 1,000 y 1 000 se comparan como 1000; el punto decimal se respeta.
    plano = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", plano)
    return re.sub(r"\s+", " ", plano)


def dice(texto: str, *variantes: str) -> bool:
    """¿Aparece alguna de las variantes en el texto?"""
    plano = normaliza(texto)
    return any(normaliza(variante) in plano for variante in variantes)


def dice_todo(texto: str, *variantes: str) -> bool:
    plano = normaliza(texto)
    return all(normaliza(variante) in plano for variante in variantes)


def respuestas(world) -> str:
    """Todo lo que el bot dijo, concatenado, para comprobaciones de conjunto."""
    return "\n".join(
        respuesta for intercambio in world.exchanges for respuesta in intercambio.replies
    )
