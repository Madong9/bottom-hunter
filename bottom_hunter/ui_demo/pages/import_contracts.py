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
class ImportPreviewDTO:
    """Complete result of reading a selected file without persistence."""

    filename: str = ""
    format: str = ""
    detected_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    preview_items: tuple[ImportPreviewItemDTO, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "format": self.format,
            "detected_count": self.detected_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "warnings": list(self.warnings),
            "preview_items": [item.as_dict() for item in self.preview_items],
        }


@dataclass(frozen=True)
class FileFingerprintDTO:
    """Fingerprint captured when a preview was produced."""

    size: int
    mtime_ns: int
    sha256: str


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
