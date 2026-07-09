# app/services/mod_service/__init__.py
"""Re-export ModService so legacy imports keep working.

``from app.services.mod_service import ModService`` continues to resolve
after the file became a package; this is the contract that ADR 0001 mandates
be preserved during the move-only refactor.
"""
from app.services.mod_service.service import ModService

__all__ = ["ModService"]
