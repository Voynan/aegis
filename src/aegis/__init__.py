"""Aegis: streaming envelope encryption for files at rest."""

# Recognised by type checkers, and spares importing `typing` at runtime.
TYPE_CHECKING = False
if TYPE_CHECKING:
    __version__: str
else:

    def __getattr__(name: str) -> str:
        """Resolve ``__version__`` on first access, so ``import aegis`` stays cheap.

        Hidden from type checkers, which would otherwise accept any name as a ``str``.

        Raises:
            AttributeError: for any other name.
        """
        if name == "__version__":
            import importlib.metadata  # deferred on purpose: stack.md § 3.3

            return importlib.metadata.version("aegis-voynan")
        raise AttributeError(f"module 'aegis' has no attribute {name!r}")
