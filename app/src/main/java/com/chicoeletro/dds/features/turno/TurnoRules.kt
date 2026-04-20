// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoRules.kt
// Função: Motor de regras de negócio para jornada de trabalho. Valida períodos de descanso 
//         obrigatório (Art. 66/67 CLT) e detecta inconsistências em turnos abertos.
// Tecnologias: Java Time API (LocalDateTime, Duration).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

object TurnoRules {

    fun podeTransitar(from: EstadoTurno, to: EstadoTurno): Boolean = when (from) {
        EstadoTurno.FECHADO ->
            to == EstadoTurno.ABERTO || to == EstadoTurno.DESLOCAMENTO_ESPECIAL

        EstadoTurno.ABERTO ->
            to == EstadoTurno.FECHADO || to == EstadoTurno.INTERVALO

        EstadoTurno.INTERVALO ->
            to == EstadoTurno.ABERTO || to == EstadoTurno.DESLOCAMENTO_ESPECIAL

        EstadoTurno.DESLOCAMENTO_ESPECIAL ->
            to == EstadoTurno.FECHADO || to == EstadoTurno.ABERTO
    }

    fun pedeKm(from: EstadoTurno, to: EstadoTurno): Boolean {
        return (from == EstadoTurno.FECHADO && to == EstadoTurno.ABERTO) ||
                (from == EstadoTurno.FECHADO && to == EstadoTurno.DESLOCAMENTO_ESPECIAL) ||
                (from == EstadoTurno.ABERTO && to == EstadoTurno.FECHADO) ||
                (from == EstadoTurno.INTERVALO && to == EstadoTurno.DESLOCAMENTO_ESPECIAL)
    }

    fun pedeMotivo(to: EstadoTurno): Boolean = (to == EstadoTurno.DESLOCAMENTO_ESPECIAL)

    // NOC/SS opcional: se preenchido, precisa ser "dígitos" com grupos por ponto.
    fun isNocSsValido(value: String): Boolean {
        val v = value.trim()
        if (v.isEmpty()) return true
        return Regex("^\\d+(\\.\\d+)*$").matches(v)
    }
}