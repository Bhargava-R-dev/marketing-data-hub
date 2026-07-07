from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import ClassVar, Iterable

from hub.core.config import ConnectorSettings


class AuthError(Exception):
    """Authentication problem with an actionable hint."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


@dataclass(frozen=True)
class FieldSpec:
    name: str            # unified name (core column or extras key)
    native: str          # native API field name
    dimension: bool = False
    description: str = ""


@dataclass
class FieldRegistry:
    specs: list[FieldSpec] = field(default_factory=list)

    def names(self) -> list[str]:
        return [s.name for s in self.specs]

    def native_to_unified(self) -> dict[str, str]:
        return {s.native: s.name for s in self.specs}

    def to_dict(self) -> list[dict]:
        return [{"name": s.name, "native": s.native, "dimension": s.dimension,
                 "description": s.description} for s in self.specs]


def resolve_targets(options: dict, plural_key: str, singular_key: str) -> list[str]:
    """Connector options may name one target (property_id: "123") or many
    (property_ids: ["123", "456"]). Returns the list either way."""
    targets = options.get(plural_key) or []
    if isinstance(targets, str):
        targets = [targets]
    single = options.get(singular_key)
    if single and single not in targets:
        targets = [*targets, single]
    if not targets:
        raise KeyError(
            f"connector options need {singular_key!r} or {plural_key!r}")
    return [str(t) for t in targets]


class BaseConnector(ABC):
    id: ClassVar[str]
    fields: ClassVar[FieldRegistry]

    def __init__(self, settings: ConnectorSettings, secrets_dir: str | Path):
        self.settings = settings
        self.secrets_dir = Path(secrets_dir)

    @abstractmethod
    def authenticate(self) -> None:
        """Load/refresh credentials. Raises AuthError with a fix hint."""

    @abstractmethod
    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        """Yield dicts keyed by unified field names (registry names) plus
        account_id/account_name. The normalizer handles the rest."""
