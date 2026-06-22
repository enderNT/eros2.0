# Chequeo de crisis prioritario

Antes del Supervisor se evalúa un chequeo de crisis prioritario. Si detecta señales de riesgo (ideación suicida, autolesión, crisis aguda), el bot responde con recursos de crisis predefinidos (definidos por los psicólogos de la clínica) y dispara Handoff inmediato — nunca maneja una crisis conversacionalmente ni la trata como FAQ o charla.

Va antes del ruteo porque sobre-escribe cualquier intención: el riesgo importa más que lo que el usuario aparenta pedir. Es un guardrail de seguridad, no un agente.

## Consecuencias

- La respuesta de crisis es predefinida y segura (recursos de emergencia + un humano), no improvisación del LLM.
- Los recursos/protocolo concretos (líneas de emergencia, mensaje aprobado) los define la clínica; el diseño deja el hueco.
- Es el segundo gate del flujo, justo después de `bot_activo` y antes de ensamblar contexto para el ruteo normal.
