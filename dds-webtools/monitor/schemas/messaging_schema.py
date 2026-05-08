# -----------------------------------------------------------------------------
# Arquivo : schemas/messaging_schema.py
# Objetivo: Definir os modelos Pydantic para a comunicação de mensagens.
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field

class MessageCreate(BaseModel):
    threadId: str = Field(..., description="ID da conversa")
    subject: str = Field(..., description="Assunto da conversa")
    content: str = Field(..., description="Conteúdo da mensagem")
    toEquipe: Optional[str] = Field(None, description="Equipe de destino")
    toSetor: Optional[str] = Field(None, description="Setor de destino")
    fromEquipe: Optional[str] = Field(None, description="Equipe/Setor de origem")

class ThreadMarkRead(BaseModel):
    threadId: str

class ThreadConclude(BaseModel):
    threadId: str
