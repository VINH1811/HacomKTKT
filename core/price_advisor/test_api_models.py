from __future__ import annotations

from pydantic import BaseModel


class PriceAdvisorExcelTestResult(BaseModel):
    job_id: str
    state: str
    message: str
    result: dict | None = None

