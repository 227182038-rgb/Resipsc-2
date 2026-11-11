"""
V3 Worker Interface Contract
Defines the interface between the FastAPI service and background workers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from dataclasses import dataclass

@dataclass
class InferenceJob:
    job_id: str
    batch_id: str
    file_path: str
    config: Dict[str, Any]

@dataclass
class InferenceResult:
    job_id: str
    status: str  # 'success', 'failed', 'partial'
    psc_fraction: float
    n_cells: int
    psc_count: int
    uncertainty_metrics: Dict[str, float]
    report_path: str

class BaseWorker(ABC):
    """Abstract base class for V3 inference workers."""
    
    @abstractmethod
    def process(self, job: InferenceJob) -> InferenceResult:
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass
