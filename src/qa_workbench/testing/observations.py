"""Pure observation boundary shared by project-specific test contracts.

Only built-in detached values and explicitly designated contract dataclasses cross
the boundary. SDK objects, clients and callbacks are never observations.
"""

from dataclasses import dataclass, fields, is_dataclass, replace
from functools import wraps


@dataclass(frozen=True)
class ObservationPolicy:
    """Bind contract namespaces explicitly instead of trusting every dataclass."""

    contract_namespaces: tuple[str, ...] = ("test_support.contracts",)

    def __post_init__(self):
        if not isinstance(self.contract_namespaces, (list, tuple)) or not self.contract_namespaces or any(
            not isinstance(name, str) or not name or not all(part.isidentifier() for part in name.split("."))
            for name in self.contract_namespaces
        ):
            raise ValueError("explicit Python contract namespaces are required")
        object.__setattr__(self, "contract_namespaces", tuple(self.contract_namespaces))

    def snapshot(self, value):
        """Fail closed on live objects and copy every supported container."""
        if type(value) in (str, int, float, bool, type(None)):
            return value
        if type(value) in (list, tuple):
            return type(value)(self.snapshot(item) for item in value)
        if type(value) is dict:
            return {self.snapshot(key): self.snapshot(item) for key, item in value.items()}
        module = type(value).__module__
        if not isinstance(value, type) and is_dataclass(value) and any(
            module == namespace or module.startswith(namespace + ".")
            for namespace in self.contract_namespaces
        ):
            return replace(
                value,
                **{field.name: self.snapshot(getattr(value, field.name)) for field in fields(value)},
            )
        raise TypeError(
            f"action returned a live/unsupported object: {type(value).__module__}.{type(value).__name__}"
        )

    def observed(self, action):
        """Decorate a public action with this project's observation contract."""
        @wraps(action)
        def wrapped(*args, **kwargs):
            return self.snapshot(action(*args, **kwargs))

        return wrapped


_DEFAULT = ObservationPolicy()


def snapshot(value):
    """Copy a value under the conventional test_support.contracts namespace."""
    return _DEFAULT.snapshot(value)


def observed(action):
    """Observe an action under the conventional contract namespace."""
    return _DEFAULT.observed(action)
