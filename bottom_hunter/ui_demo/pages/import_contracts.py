"""PHASE 4-D1 — Immutable transport contracts for import preview."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportPreviewItemDTO:
    """One normalized, read-only preview row."""

    symbol: str = "--"
    name: str = "--"
    market: str = "--"
    category: str = "--"
    industry: str = "--"

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "category": self.category,
            "industry": self.industry,
        }


@dataclass(frozen=True)
class FileFingerprintDTO:
    """Fingerprint captured when a preview was produced."""

    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class ImportPreviewDTO:
    """Complete result of reading a selected file without persistence."""

    filename: str = ""
    format: str = ""
    detected_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    preview_items: tuple[ImportPreviewItemDTO, ...] = field(default_factory=tuple)
    file_fingerprint: FileFingerprintDTO | None = None

    def as_dict(self) -> dict[str, Any]:
        fingerprint = self.file_fingerprint
        return {
            "filename": self.filename,
            "format": self.format,
            "detected_count": self.detected_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "warnings": list(self.warnings),
            "preview_items": [item.as_dict() for item in self.preview_items],
            "file_fingerprint": (
                {
                    "size": fingerprint.size,
                    "mtime_ns": fingerprint.mtime_ns,
                    "sha256": fingerprint.sha256,
                }
                if fingerprint is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ImportCommandDTO:
    """Validated intent passed to the command boundary."""

    command_id: str
    preview_id: str
    source: str
    file_path: str
    file_fingerprint: FileFingerprintDTO
    account_alias: str = ""
    resolve_industries: bool = True
    allow_partial: bool = False
    requested_at: str = ""


@dataclass(frozen=True)
class ImportErrorDTO:
    """Safe error information returned to the ViewModel."""

    code: str
    stage: str
    message: str
    retryable: bool = False
    technical_reference: str = ""


@dataclass(frozen=True)
class ImportResultDTO:
    """Transport-only terminal or review result of an import command."""

    command_id: str
    source: str
    filename: str
    status: str
    committed: bool = False
    rollback_performed: bool = False
    imported_count: int = 0
    merged_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0
    unresolved_industry_count: int = 0
    generated_sector_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    error: ImportErrorDTO | None = None
    started_at: str = ""
    finished_at: str = ""


@dataclass(frozen=True)
class ImportMaintenanceCommandDTO:
    """A user-confirmed watchlist maintenance intent."""

    action: str
    source: str = ""
    symbol: str = ""
    name: str = ""
    market: str = ""
    industry: str = ""


@dataclass(frozen=True)
class ImportSourceStatusDTO:
    source: str
    label: str
    count: int = 0
    manual_count: int = 0
    connected: bool = False
    imported_at: str = ""
    import_file: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "label": self.label,
            "count": self.count,
            "manualCount": self.manual_count,
            "connected": self.connected,
            "importedAt": self.imported_at,
            "importFile": self.import_file,
        }


@dataclass(frozen=True)
class ImportMaintenanceResultDTO:
    action: str
    success: bool
    message: str
    total_count: int = 0
    affected_sources: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    source_statuses: tuple[ImportSourceStatusDTO, ...] = field(default_factory=tuple)
