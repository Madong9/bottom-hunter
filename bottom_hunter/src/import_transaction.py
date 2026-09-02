"""Backend-internal transport types for prepared watchlist imports.

These contracts describe an in-memory import plan only.  They deliberately
carry no repository, database, Qt, open file, or persistence implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .account_watchlist import WatchAsset


@dataclass(frozen=True)
class PreparedFileFingerprint:
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class PreparedPathBaseline:
    """Hash captured for one repository dependency or future target."""

    kind: str
    path: str
    existed: bool
    sha256: str = ""


@dataclass(frozen=True)
class ImportConflict:
    code: str
    message: str
    path: str = ""
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True)
class ImportVerificationResult:
    transaction_id: str
    valid: bool
    conflicts: tuple[ImportConflict, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlannedImportArtifact:
    """One candidate payload; writing it belongs to a later phase."""

    kind: str
    target: str
    format: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "format": self.format,
            "payload": deepcopy(dict(self.payload)),
        }


@dataclass(frozen=True)
class PreparedImport:
    """Complete, serializable result of the zero-write preparation phase."""

    transaction_id: str
    source: str
    source_file: str
    prepared_at: str
    fingerprint: PreparedFileFingerprint
    baselines: tuple[PreparedPathBaseline, ...] = field(default_factory=tuple)
    parsed_assets: tuple[WatchAsset, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    imported_count: int = 0
    merged_count: int = 0
    duplicate_count: int = 0
    unresolved_industry_count: int = 0
    generated_sector_count: int = 0
    planned_artifacts: tuple[PlannedImportArtifact, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "source": self.source,
            "source_file": self.source_file,
            "prepared_at": self.prepared_at,
            "fingerprint": asdict(self.fingerprint),
            "baselines": [asdict(baseline) for baseline in self.baselines],
            "parsed_assets": [asset.to_dict() for asset in self.parsed_assets],
            "warnings": list(self.warnings),
            "imported_count": self.imported_count,
            "merged_count": self.merged_count,
            "duplicate_count": self.duplicate_count,
            "unresolved_industry_count": self.unresolved_industry_count,
            "generated_sector_count": self.generated_sector_count,
            "planned_artifacts": [artifact.to_dict() for artifact in self.planned_artifacts],
        }
