# app/viewmodels/mod_list_vm/__init__.py
"""Re-export ModListViewModel so legacy imports keep working.

`from app.viewmodels.mod_list_vm import ModListViewModel` continues to resolve
after the file became a package; this is the contract that ADR 0001 mandates
be preserved during the move-only refactor.
"""
from app.viewmodels.mod_list_vm.viewmodel import ModListViewModel

__all__ = ["ModListViewModel"]