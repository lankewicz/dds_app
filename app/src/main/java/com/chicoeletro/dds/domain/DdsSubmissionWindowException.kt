// Módulo: app/src/main/java/com/chicoeletro/dds/domain/DdsSubmissionWindowException.kt
// Função: Exceção personalizada para sinalizar tentativas de submissão fora da janela de tempo 
//         permitida (regras de negócio de envio).
// Tecnologias: Kotlin Custom Exception.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.domain

class DdsSubmissionWindowException(
    message: String
) : IllegalStateException(message)