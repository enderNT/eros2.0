"""El registro de cada caso, rellenado solo.

El documento de casos pedía dejar constancia después de cada ejecución. Escribir
eso a mano es donde se pierde la disciplina, así que lo escribe el arnés: la
transcripción literal, el estado final de la base, cada criterio con su
resultado y cada métrica con su puntuación y el razonamiento del juez.

La pieza clave es `esperado`. Cada criterio declara qué debería pasar **según el
código de hoy**, no según lo que sería deseable. Así el informe distingue solo
las tres cosas que el protocolo pide no mezclar:

* coincide y `esperado=True`  -> funciona
* coincide y `esperado=False` -> **hueco confirmado**: no falla, es que no existe
* no coincide                 -> **desviación**: o es un bug nuevo, o alguien
  arregló el hueco y hay que actualizar el caso
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .world import RUNS_DIR, Snapshot, World


@dataclass(slots=True)
class Criterio:
    numero: int | str
    texto: str
    resultado: bool | None
    esperado: bool | None = None
    nota: str = ""

    @property
    def veredicto(self) -> str:
        if self.resultado is None:
            return "N/A"
        return "SÍ" if self.resultado else "NO"

    @property
    def clase(self) -> str:
        if self.resultado is None or self.esperado is None:
            return "informativo"
        if self.resultado == self.esperado:
            return "ok" if self.esperado else "hueco confirmado"
        return "DESVIACIÓN"


@dataclass(slots=True)
class Medida:
    nombre: str
    score: float | None
    umbral: float
    aprobado: bool
    razon: str


@dataclass(slots=True)
class Report:
    caso: str
    titulo: str
    criterios: list[Criterio] = field(default_factory=list)
    medidas: list[Medida] = field(default_factory=list)
    ajustes: dict[str, Any] = field(default_factory=dict)
    bloqueado: str = ""

    def criterio(
        self,
        numero: int | str,
        texto: str,
        resultado: bool | None,
        *,
        esperado: bool | None = None,
        nota: str = "",
    ) -> bool | None:
        self.criterios.append(Criterio(numero, texto, resultado, esperado, nota))
        return resultado

    def medir(self, metric: Any, test_case: Any) -> Medida:
        """Ejecuta una métrica de deepeval y guarda su veredicto con el porqué."""
        metric.measure(test_case)
        medida = Medida(
            nombre=getattr(metric, "__name__", None) or metric.__class__.__name__,
            score=metric.score,
            umbral=metric.threshold,
            aprobado=bool(metric.is_successful()),
            razon=str(metric.reason or "").strip(),
        )
        self.medidas.append(medida)
        return medida

    # ------------------------------------------------------------ salida

    @property
    def estado(self) -> str:
        if self.bloqueado:
            return "BLOQUEADO"
        desviaciones = [c for c in self.criterios if c.clase == "DESVIACIÓN"]
        fallos = [m for m in self.medidas if not m.aprobado]
        if desviaciones:
            return "FALLA"
        if fallos:
            return "PARCIAL"
        return "OK"

    def write(self, world: World, snapshot: Snapshot | None = None) -> Path:
        estado = snapshot or world.state()
        destino = RUNS_DIR / world.name / "reporte.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(self._render(world, estado), encoding="utf-8")
        return destino

    def _render(self, world: World, estado: Snapshot) -> str:
        # El modo del calendario no es un ajuste más: dos informes del mismo caso
        # en modos distintos no son comparables, y sin esto no se nota.
        declarados = {"calendario": world.modo_calendario} | self.ajustes
        ajustes = ", ".join(f"{k} = {v}" for k, v in declarados.items())
        partes = [
            f"# Registro — {self.caso}: {self.titulo}",
            "",
            "- **Ejecutado por:** arnés deepeval (`evals/`)",
            f"- **Fecha:** {datetime.now(UTC).isoformat(timespec='seconds')}",
            f"- **Ajustes usados:** {ajustes}",
            f"- **Estado:** {self.estado}",
            "",
            "## Criterios",
            "",
            "| # | Criterio | Resultado | Esperado | Lectura | Nota |",
            "|---|---|---|---|---|---|",
        ]
        for c in self.criterios:
            esperado = "—" if c.esperado is None else ("SÍ" if c.esperado else "NO")
            partes.append(
                f"| {c.numero} | {c.texto} | {c.veredicto} | {esperado} | {c.clase} |"
                f" {c.nota or ''} |"
            )
        if self.medidas:
            partes += ["", "## Métricas del juez (deepeval)", ""]
            for m in self.medidas:
                marca = "PASA" if m.aprobado else "FALLA"
                score = "—" if m.score is None else f"{m.score:.2f}"
                partes += [
                    f"### {m.nombre} — {marca} ({score} / umbral {m.umbral})",
                    "",
                    m.razon or "(el juez no dio razón)",
                    "",
                ]
        partes += ["", "## Transcripción literal", "", "```", world.transcript(), "```", ""]
        partes += ["## Estado final", "", _estado(estado), ""]
        if self.bloqueado:
            partes += ["## Bloqueo", "", self.bloqueado, ""]
        partes += [
            "## Hallazgos",
            "",
            *(
                _hallazgo(c)
                for c in self.criterios
                if c.clase in {"DESVIACIÓN", "hueco confirmado"}
            ),
            "",
        ]
        return "\n".join(partes) + "\n"


def _hallazgo(c: Criterio) -> str:
    etiqueta = "**BUG / revisar**" if c.clase == "DESVIACIÓN" else "**hueco**"
    return f"- {etiqueta} — criterio {c.numero}: {c.texto} → {c.veredicto}. {c.nota}".rstrip()


def _estado(estado: Snapshot) -> str:
    lineas = ["```", f"citas: {len(estado.appointments)} ({len(estado.scheduled)} vigentes)"]
    for cita in estado.appointments:
        lineas.append(f"  {cita.slot_utc.isoformat()}  {cita.status}  {cita.event_uri}")
    lineas.append(f"outbox: {len(estado.outbox)}")
    for row in estado.outbox:
        marca = f"enviado {row.sent_at.isoformat()}" if row.sent else "PENDIENTE"
        lineas.append(f"  {row.kind}  vence {row.due_at.isoformat()}  {marca}")
    lineas.append(f"mute: {'SÍ' if estado.muted else 'no'}  ({estado.mute_reason or '-'})")
    lineas.append(f"perfil: {estado.profile}")
    lineas.append("```")
    return "\n".join(lineas)


def cerrar(reporte: Report, world: World) -> Path:
    """Escribe el registro y falla el caso si hay desviación o métrica reprobada.

    Un hueco confirmado **no** falla: el caso documenta lo que hoy no existe, y
    hacerlo fallar cada noche sólo enseñaría a ignorar el rojo. Lo que falla es
    que la realidad se aparte de lo documentado — que es cuando alguien tiene que
    mirar: o se rompió algo, o alguien tapó el hueco y hay que actualizar el caso.
    """
    destino = reporte.write(world)
    desviaciones = [c for c in reporte.criterios if c.clase == "DESVIACIÓN"]
    reprobadas = [m for m in reporte.medidas if not m.aprobado]
    if not desviaciones and not reprobadas:
        return destino
    lineas = [f"{reporte.caso} — registro en {destino}"]
    for c in desviaciones:
        lineas.append(
            f"  desviación criterio {c.numero}: {c.texto} -> {c.veredicto}"
            f" (esperado {'SÍ' if c.esperado else 'NO'}). {c.nota}"
        )
    for m in reprobadas:
        score = "—" if m.score is None else f"{m.score:.2f}"
        lineas.append(f"  métrica '{m.nombre}' reprobada ({score} < {m.umbral}): {m.razon}")
    raise AssertionError("\n".join(lineas))
