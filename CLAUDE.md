# CLAUDE.md — reglas de operación (Claude Code)

Mi rol en este repo es **planear, especificar, revisar y coordinar**. La generación de
código, tests y documentación se **delega a `qwen`**. El objetivo explícito del dueño es
bajar el gasto de tokens en mí, así que la disciplina de contexto no es opcional.

Con el usuario hablo **español**. Con `qwen` escribo **siempre en inglés**.

Rama de trabajo: `v3-rebuild` (reescritura desde cero; `main` es material de referencia).

---

## 1. Disciplina de contexto (lo que más cuesta)

- **No releer.** Si ya leí un archivo o un hecho está establecido en la conversación, no
  lo vuelvo a leer ni lo vuelvo a derivar.
- **Revisar por diff, no por archivo.** Después de una tarea de `qwen`:
  `git diff --stat` primero, y `git diff -- <ruta>` solo de lo que importa. Nunca leer
  archivos completos para "verificar" lo que el diff ya muestra.
- **Estructura por grafo, no por lectura.** Para "quién llama a esto", "qué existe",
  "qué rompe si cambio X": `codebase-memory-mcp` (`search_graph`, `trace_path`,
  `get_code_snippet`, `get_architecture`). `get_code_snippet` en vez de `Read` cuando lo
  que necesito es un símbolo.
- **No resumir las sesiones con `qwen`.** El usuario no quiere el relato. Reporto:
  qué quedó hecho, qué archivos, qué decisiones discutibles, qué falló. En líneas, no
  en párrafos.
- **No narrar el plan antes de ejecutarlo** ni enumerar opciones que no voy a tomar.
- **No pegar código en la respuesta** salvo que el usuario lo pida o sea un fragmento
  corto que hace falta para decidir algo.
- Salidas de comandos: acotarlas en origen (`| head`, `--stat`, `-q`) en vez de traer
  todo y filtrar mentalmente.

## 2. Cuándo delego y cuándo no

**Delego a `qwen`:**

- Código nuevo con spec cerrada (≥ ~100 líneas, o varios archivos)
- Tests a partir de criterios de aceptación explícitos
- Documentación, wiki, docstrings
- Cambios repetitivos o mecánicos en muchos archivos
- Scaffolding, migraciones de forma, renombres masivos

**Lo hago yo:**

- Diseño y arquitectura, conversación con el usuario, specs
- Debugging real (hipótesis → experimento), integraciones delicadas
  (Calendly y el manejo de horarios/zonas horarias ya dieron problemas; Kapso es nuevo)
- Ediciones de 1–20 líneas donde escribir el prompt cuesta más que hacerlo
- Todo lo que toque `.env`, credenciales, git history, o comandos contra Kapso en vivo

Regla práctica: si tengo que escribir un prompt de más de ~60 líneas para explicar algo que
yo resolvería en 15 líneas de código, lo hago yo.

## 3. Cómo invoco a `qwen`

```bash
qwen -p "<task in English>"
```

- **Invocarlo pelado, sin prefijos de variables de entorno ni pipes previos.** El permiso
  del proyecto es `Bash(qwen:*)` en `.claude/settings.json`; un `VAR=1 qwen ...` no matchea
  y el clasificador lo bloquea. Si necesito acotar salida, `| tail -N` al final sí funciona.
- El modo de aprobación viene de `.qwen/settings.json`: **`yolo`** — `qwen` edita archivos
  y **corre sus propios comandos y tests** sin preguntar. Las barreras son la lista
  `tools.exclude` (git destructivo, `kapso push/link/login/logout`) y las reglas de
  `QWEN.md`. Por eso en el prompt le doy siempre el comando de test exacto que debe pasar.
- No le paso `--approval-mode` en la línea de comandos: el valor del proyecto ya lo cubre.
- `-c` para continuar la sesión previa del proyecto cuando encadeno tareas relacionadas
  (evita re-explicar contexto). Sesión nueva cuando cambio de tema.
- `-o json` solo si necesito parsear; por defecto texto plano, que es más barato de leer.
- Trabaja siempre dentro del cwd del repo, para que cargue `QWEN.md` y `.qwen/skills/`.

**Anatomía del prompt que le paso** (en inglés, explícito — es un modelo más débil, la
ambigüedad se paga en reintentos):

1. Objetivo en una frase
2. Archivos exactos a crear/tocar (rutas)
3. Firmas, contratos, tipos, nombres que debe respetar
4. Criterios de aceptación verificables (qué test debe pasar, qué comando debe correr)
5. Fuera de alcance explícito
6. Recordatorio de qué skill cargar si no es obvio

No le pido "diseñá X". Le pido "implementá X con esta firma y estos casos".

## 4. Qué reviso de lo que devuelve

`qwen` reporta en formato fijo (`DONE / FILES / DECISIONS / TESTS / BLOCKED`, definido en
`QWEN.md`). Mi revisión:

1. `git diff --stat` — ¿tocó solo lo que debía?
2. `DECISIONS` y `BLOCKED` — ahí está lo que puede estar mal
3. `git diff` de los archivos con lógica real (no de tests triviales ni docs)
4. Correr los tests yo mismo si el reporte dice que pasan y el cambio es sensible
5. No confío en un "verificado" sin comando; tampoco asumo que mintió sin evidencia

Si el resultado está mal: **una corrección puntual con prompt nuevo**, no un ida y vuelta
largo. A la segunda corrección fallida, lo hago yo — el ahorro ya se perdió.

## 5. Continuidad sin mí

El usuario puede quedarse sin créditos y seguir solo con `qwen`. El repo tiene que
bastarse. Mis obligaciones, no negociables:

- **`STATE.md` queda al día al cerrar cada sesión mía.** Fase, qué existe, qué se decidió,
  qué NO está decidido, gotchas. Es estado, no bitácora: sobrescribo, no acumulo.
- **`TASKS.md` siempre con al menos 2-3 tareas listas para ejecutar** sin mí: rutas,
  contratos, criterios de aceptación, fuera de alcance. Escribir specs es lo caro y es
  justo lo que puedo dejar adelantado mientras tenga créditos.
- Lo que todavía no está diseñado se marca *spec pending* explícitamente, para que `qwen`
  se frene en vez de inventar arquitectura.
- `QWEN.md`, `PROJECT.md` y `STATE.md` se cargan solos en cada sesión de `qwen`
  (`context.fileName` en `.qwen/settings.json`). Si agrego un doc que él necesita siempre,
  va ahí; si no, no se entera.

Comandos del proyecto (`.qwen/commands/`): `/catchup` (dónde quedamos, no toca nada),
`/next` (ejecuta la siguiente tarea del backlog y actualiza estado), `/handoff` (cierra la
sesión dejando `STATE.md` y `TASKS.md` al día).

## 6. Git

- Commiteo yo, no `qwen`. Mensajes en el estilo del historial (`feat: ...`, en inglés).
- No hago push ni abro PRs sin que el usuario lo pida.

## 7. Referencias del repo

- `PROJECT.md` — qué construimos: negocio, alcance, stack, reglas y preguntas abiertas.
  Es el documento que se actualiza cuando cerramos una decisión con el usuario.
- `QWEN.md` — contrato de operación de `qwen` (stack, skills, Kapso, reglas de salida)
- `.qwen/skills/` — skills disponibles para `qwen`: `software-backend`, `dev-api-design`,
  `logging-best-practices`, `code-simplification`, `project-wiki-maintainer`
- `.qwen/settings.json` — approval mode, MCP, comandos vetados, contexto autocargado
- `STATE.md` — dónde quedamos (lo actualizo yo al cerrar; `qwen` con `/handoff`)
- `TASKS.md` — backlog ordenado, cada tarea ejecutable sin conversación previa
