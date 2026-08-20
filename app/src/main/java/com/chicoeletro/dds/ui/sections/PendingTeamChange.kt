package com.chicoeletro.dds.ui.sections

import com.chicoeletro.dds.core.WorkSchedule

data class PendingTeamChange(
    val name: String,
    val members: List<String>,
    val schedule: WorkSchedule,
    val teamType: String?,
    val motorista: String?,
    val coringas: List<String>
)
