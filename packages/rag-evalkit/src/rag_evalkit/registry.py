"""Explicit extension registry; manifests cannot import arbitrary Python paths."""

from importlib.metadata import entry_points

from .contracts import ContractError, UnsupportedCapability


class Registry:
    def __init__(self):
        self._factories = {}

    def register(self, kind, name, factory):
        if kind not in {"store", "model", "harness", "rag", "embedding"} or not isinstance(name, str) or not name or not callable(factory):
            raise ContractError("invalid adapter registration")
        key = kind, name
        if key in self._factories:
            raise ContractError("adapter already registered: " + kind + "/" + name)
        self._factories[key] = factory

    def build(self, kind, config, **context):
        key = kind, config["type"]
        if key not in self._factories:
            raise UnsupportedCapability("unregistered adapter: " + "/".join(key))
        return self._factories[key](config, **context)

    def load_plugins(self, names):
        """Only explicitly named, installed entry points may execute code."""
        available = {}
        for point in entry_points(group="rag_evalkit.plugins"):
            if point.name in available:
                raise ContractError("ambiguous installed plugin: " + point.name)
            available[point.name] = point
        for name in names:
            if name not in available:
                raise UnsupportedCapability("plugin is not installed: " + name)
            available[name].load()(self)

    def describe(self):
        return [{"kind": kind, "name": name} for kind, name in sorted(self._factories)]
