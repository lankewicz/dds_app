package com.chicoeletro.dds.components

enum class FooterStatusKind {
    NORMAL,
    WARNING,
    SUCCESS
}

data class FooterStatus(
    val text: String,
    val kind: FooterStatusKind = FooterStatusKind.NORMAL
)