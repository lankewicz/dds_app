# Finalidade: schemas usados nas respostas das importações.
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportBatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_filename: str
    total_rows: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    error_count: int
    status: str = "completed"
    progress: int = 100
    imported_at: datetime


class ImportErrorItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    field_name: str | None
    raw_value: str | None
    message: str
