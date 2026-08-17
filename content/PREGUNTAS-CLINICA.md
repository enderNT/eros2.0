# Preguntas para la clínica

Cada hueco `<<pendiente>>` de `wiki.md` es una pregunta de esta lista. **Nadie las
contesta por la clínica**: si el asistente inventa una política de cancelación o un
requisito de facturación, el paciente actúa sobre eso y el error sale caro.

La respuesta se copia tal cual al lugar indicado. Si algo no aplica, decirlo también
—"no facturamos" es una respuesta válida y útil; el silencio no.

---

## 1. Cancelación y reagendamiento
→ `wiki.md`, sección **Políticas de citas**

- ¿Con cuánta anticipación se puede cancelar sin costo?
- ¿Se cobra algo por cancelar tarde o por no presentarse? ¿Cuánto?
- ¿Por qué medio se cancela: WhatsApp, teléfono, el enlace de Calendly?
- ¿Cuántas veces se puede reagendar la misma cita?

## 2. Confidencialidad
→ `wiki.md`, sección **Políticas de citas**

- ¿Qué se le dice a un paciente que pregunta si lo que cuenta es confidencial?
- ¿Hay límites que convenga mencionar (riesgo para la vida, menores de edad, orden
  judicial)?
- En el caso de menores: ¿qué se le informa al padre, madre o tutor?

## 3. Qué llevar a la primera cita
→ `wiki.md`, sección **Políticas de citas**

- ¿Documentos, identificación, estudios previos, informes escolares?
- ¿Hay que llenar algo antes de llegar?
- ¿Puede o debe entrar acompañante?

## 4. Equipo profesional
→ `wiki.md`, sección **Equipo profesional**

Sólo lo que la clínica autorice como **información pública**. Por cada persona: nombre,
formación, número de cédula profesional y áreas que atiende.

- ¿Puede el asistente decir qué profesional atendería un caso, o eso se define internamente?

## 5. Canal de atención prioritaria
→ `wiki.md`, sección **Urgencias y situaciones de crisis**

- Cuando el asistente detecta riesgo y escala, ¿a quién le llega y por qué medio?
- ¿Hay un teléfono de atención prioritaria de la clínica? ¿En qué horario?
- Fuera de horario, ¿a dónde se dirige a la persona?

## 6. Facturación y seguros
→ `wiki.md`, sección **Facturación y seguros**

- ¿Se emiten facturas? ¿Qué datos hay que dar y en qué momento?
- ¿Se trabaja con aseguradoras? ¿Cuáles?
- ¿Se entregan recibos o informes para reembolso?

## 7. Dirección exacta de la sede
→ variable de entorno `CALENDLY_LOCATION_VALUE`

Es lo que se manda en el WhatsApp de confirmación cuando alguien agenda. Calle, número,
colonia y referencias. Mientras esté vacía, la confirmación simplemente no menciona
dirección —preferible a inventarla.

## 8. Mensaje de crisis
→ variable de entorno `CRISIS_MESSAGE`

**El más importante de la lista.** Se envía textual, sin que el modelo lo reformule, y
después el asistente se calla hasta que una persona lo reactive.

Tiene que traer:

- Qué hacer **ahora** (a qué número llamar, a dónde acudir).
- Los teléfonos, **verificados uno por uno** por la clínica. No se publican de memoria.
- El canal propio de la clínica, si existe, y su horario.

Borrador para que la clínica corrija —**no usar sin aprobación ni sin verificar cada
número**:

> Lo que me cuentas es importante y merece atención de una persona ahora mismo. Si estás en
> peligro inmediato, llama al 911 o acude al servicio de urgencias más cercano. También
> puedes llamar a la Línea de la Vida, 800 911 2000, disponible las 24 horas. Ya avisé al
> equipo de la clínica para que te contacten.

Decisiones que la clínica tiene que tomar sobre ese texto:

- ¿Esos son los números que quiere dar, o prefiere otros?
- La última frase promete un contacto humano. ¿Se puede cumplir, y en cuánto tiempo?
- ¿Quiere que el mensaje cambie fuera del horario de atención?
