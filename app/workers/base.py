"""Base worker class for all RIP workers."""

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.core.logger import get_logger
from app.schemas.messages import WorkerRequest, WorkerResponse

logger = get_logger(__name__)


class BaseWorker(ABC):
    """Abstract base class for all RIP workers."""

    def __init__(self, worker_id: str, name: str):
        """
        Initialize worker.

        Args:
            worker_id: Unique worker identifier
            name: Human-readable worker name
        """
        self.worker_id = worker_id
        self.name = name
        self.version = "0.1.0"
        self.status = "active"

    async def execute(self, request: WorkerRequest) -> WorkerResponse:
        """
        Execute worker action.

        Args:
            request: Worker request

        Returns:
            Worker response
        """
        start_time = time.time()

        try:
            # Validate request
            if not await self.validate(request):
                return WorkerResponse(
                    success=False,
                    error="Invalid request",
                    worker_id=self.worker_id,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Process request
            logger.info(
                f"Worker {self.name} processing request",
                extra={"worker_id": self.worker_id, "action": request.action},
            )

            data = await self.process(request)

            execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Worker {self.name} completed",
                extra={
                    "worker_id": self.worker_id,
                    "execution_time_ms": execution_time_ms,
                },
            )

            return WorkerResponse(
                success=True,
                data=data,
                worker_id=self.worker_id,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            logger.error(
                f"Worker {self.name} error: {str(e)}",
                extra={"worker_id": self.worker_id},
                exc_info=True,
            )

            return WorkerResponse(
                success=False,
                error=str(e),
                worker_id=self.worker_id,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    @abstractmethod
    async def process(self, request: WorkerRequest) -> dict[str, Any]:
        """
        Process worker request. Must be implemented by subclasses.

        Args:
            request: Worker request

        Returns:
            Processing result data
        """
        pass

    @abstractmethod
    async def validate(self, request: WorkerRequest) -> bool:
        """
        Validate worker request. Must be implemented by subclasses.

        Args:
            request: Worker request

        Returns:
            True if valid, False otherwise
        """
        pass

    async def health_check(self) -> dict[str, Any]:
        """
        Check worker health.

        Returns:
            Health status
        """
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "status": self.status,
            "version": self.version,
            "timestamp": time.time(),
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(id={self.worker_id}, name={self.name})"
