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
    additive: bool = True  # False for rates/averages (ctr, position) that must not be summed
    description: str = ""


@dataclass
class FieldRegistry:
    specs: list[FieldSpec] = field(default_factory=list)
    description: str = ""  # what analyses this report shape answers

    def names(self) -> list[str]:
        return [s.name for s in self.specs]

    def dimensions(self) -> list[FieldSpec]:
        return [s for s in self.specs if s.dimension]

    def metrics(self) -> list[FieldSpec]:
        return [s for s in self.specs if not s.dimension]

    def native_to_unified(self) -> dict[str, str]:
        return {s.native: s.name for s in self.specs}

    def to_dict(self) -> list[dict]:
        return [{"name": s.name, "native": s.native, "dimension": s.dimension,
                 "description": s.description} for s in self.specs]


def group_by_identity(targets: list[str], options: dict) -> dict[str, list[str]]:
    """Group targets (property ids / site urls / account ids) by which Google
    login owns them. options.identities maps target -> identity name; anything
    unmapped belongs to the 'default' identity (the original single login)."""
    mapping = options.get("identities") or {}
    groups: dict[str, list[str]] = {}
    for t in targets:
        groups.setdefault(str(mapping.get(t, "default")), []).append(t)
    return groups


def resolve_targets(options: dict, plural_key: str, singular_key: str) -> list[str]:
    """Connector options may name one target (property_id: "123") or many
    (property_ids: ["123", "456"]). Returns the list either way."""
    targets = options.get(plural_key) or []
    if isinstance(targets, str):
        targets = [targets]
    targets = [str(t) for t in targets]
    single = options.get(singular_key)
    if single is not None:
        single = str(single)
        if single not in targets:
            targets.append(single)
    if not targets:
        raise KeyError(
            f"connector options need {singular_key!r} or {plural_key!r}")
    return targets


class BaseConnector(ABC):
    id: ClassVar[str]
    fields: ClassVar[FieldRegistry]
    # optional named report shapes beyond 'core'; each syncs into its own
    # (source, report) slice so different granularities never mix
    reports: ClassVar[dict[str, FieldRegistry]] = {}

    def __init__(self, settings: ConnectorSettings, secrets_dir: str | Path):
        self.settings = settings
        self.secrets_dir = Path(secrets_dir)

    @classmethod
    def get_reports(cls) -> dict[str, FieldRegistry]:
        """All report shapes, 'core' first. Connectors that predate
        multi-report support just expose their fields as 'core'."""
        return {"core": cls.fields, **cls.reports}

    def enabled_reports(self) -> list[str]:
        """Reports to sync — all by default, restrictable via options.reports."""
        available = self.get_reports()
        wanted = self.settings.options.get("reports")
        if not wanted:
            return list(available)
        unknown = [r for r in wanted if r not in available]
        if unknown:
            raise KeyError(f"{self.id} has no reports {unknown!r} "
                           f"(available: {list(available)})")
        return list(wanted)

    @abstractmethod
    def authenticate(self) -> None:
        """Load/refresh credentials. Raises AuthError with a fix hint."""

    @abstractmethod
    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        """Yield dicts keyed by unified field names (registry names) plus
        account_id/account_name. The normalizer handles the rest."""

    def extract_report(self, report: str, date_from: date,
                       date_to: date) -> Iterable[dict]:
        """Extract one named report shape. Default handles 'core' only."""
        if report == "core":
            return self.extract(date_from, date_to)
        raise KeyError(f"{self.id} has no report {report!r}")
