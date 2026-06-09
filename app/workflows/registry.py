"""Registry for available workflow definitions."""

from typing import Callable, Dict

registry: Dict[str, Callable] = {}


def register(name: str, factory: Callable) -> None:
    registry[name] = factory


def get(name: str):
    return registry.get(name)


# Register built-in workflows
try:
    from app.workflows.pdf_bill_workflow import create_pdf_bill_workflow
    register("pdf_bill", create_pdf_bill_workflow)
except Exception:
    # avoid import-time errors during testing if files not present
    pass
