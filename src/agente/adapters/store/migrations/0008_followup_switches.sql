-- Poder apagarlos, no sólo retrasarlos.
--
-- El plazo ya era configurable, pero no había forma de decir "esto no lo
-- queremos". La clínica que no quiere perseguir silencios sólo podía subir el
-- slider al máximo, que no es apagarlo: es esperar más.
--
-- Dos interruptores, no uno, por la misma razón que hay dos plazos: son dos
-- decisiones distintas. Retomar a quien se calló es marketing suave; recordar
-- una cita que ya existe es un servicio. Una clínica puede querer lo segundo y
-- no lo primero.
--
-- Encendidos por defecto: es el comportamiento que ya tenían las instalaciones
-- existentes, y una migración no es el lugar para cambiarle la conducta a nadie.
ALTER TABLE app_setting ADD COLUMN interest_followup_enabled INTEGER NOT NULL DEFAULT 1
    CHECK (interest_followup_enabled IN (0, 1));

ALTER TABLE app_setting ADD COLUMN appointment_reminder_enabled INTEGER NOT NULL DEFAULT 1
    CHECK (appointment_reminder_enabled IN (0, 1));
