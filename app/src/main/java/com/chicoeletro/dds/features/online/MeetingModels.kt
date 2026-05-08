package com.chicoeletro.dds.features.online

import com.google.firebase.Timestamp

data class Roles(
    val hostTeams: List<String> = emptyList(),
    val cohostTeams: List<String> = emptyList(),
    val participant: List<String> = emptyList()
)

data class DdsSession(
    val id: String = "",
    val type: String = "online",
    val date: String = "",
    val time: String = "",
    val timezone: String = "America/Sao_Paulo",
    val subject: String = "",
    val status: String = "scheduled",
    val createdByEmail: String = "",
    val channelName: String = "",
    val roles: Roles = Roles()
) {
    // Para simplificar a criação pelo Firestore
    constructor() : this("", "online", "", "", "America/Sao_Paulo", "", "scheduled", "", "", Roles())
}
