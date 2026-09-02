"""PHASE 4-D1 — Strictly read-only selected-file preview adapter.

This is the only boundary allowed to call the existing watchlist parser.  It
does not construct the repository and never calls a persistence operation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .import_contracts import FileFingerprintDTO, ImportPreviewDTO, ImportPreviewItemDTO

SUPPORTED_SOURCES = frozenset({"tonghuashun", "binance", "okx"})
PREVIEW_LIMIT = 50
FORMAT_LABELS = {
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".xlsm": "Excel",
    ".csv": "CSV",
    ".json": "JSON",
    ".txt": "TXT",
    ".sel": "SEL",
    ".ini": "INI",
}


class ImportPreviewError(ValueError):
    """The selected file could not produce a safe preview."""


def normalize_import_selection(selection: str | Path) -> Path:
    """Return the local path represented by a QML file selection."""

    value = str(selection).strip()
    if value.startswith("file:"):
        parsed = urlsplit(value)
        value = unquote(parsed.path)
    return Path(value).expanduser().resolve()


def _format_label(path: Path) -> str:
    suffix = path.suffix.casefold()
    return FORMAT_LABELS.get(suffix, suffix.removeprefix(".").upper() or "UNKNOWN")


def _fingerprint(path: Path) -> FileFingerprintDTO:
    stat = path.stat()
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return FileFingerprintDTO(size=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=digest)


def build_import_preview_dto(
    selection: str | Path,
    source: str,
) -> ImportPreviewDTO:
    """Read and normalize a file without changing any application state."""

    normalized_source = source.strip().casefold()
    if normalized_source not in SUPPORTED_SOURCES:
        raise ImportPreviewError(f"不支持的自选来源：{source}")

    path = normalize_import_selection(selection)
    if not path.is_file():
        raise ImportPreviewError(f"文件不存在：{path.name or path}")
    file_format = _format_label(path)
    preview_fingerprint = _fingerprint(path)
    if path.stat().st_size == 0:
        return ImportPreviewDTO(
            filename=path.name,
            format=file_format,
            warnings=("文件为空，没有可预览的记录。",),
            file_fingerprint=preview_fingerprint,
        )

    # Deferred import keeps the DTO module pure. parse_watchlist_file reads
    # and normalizes the selected file; it does not persist application state.
    from bottom_hunter.src.account_watchlist import parse_watchlist_file

    failures: list[str] = []
    try:
        assets = parse_watchlist_file(path, normalized_source, failures_out=failures)
    except (OSError, ValueError) as exc:
        raise ImportPreviewError(str(exc)) from exc
    if _fingerprint(path) != preview_fingerprint:
        raise ImportPreviewError("文件在预览期间发生变化，请重新选择。")

    warnings = list(failures)
    if len(assets) > PREVIEW_LIMIT:
        warnings.append(f"预览仅显示前 {PREVIEW_LIMIT} 项，文件不会被修改。")
    preview_items = tuple(
        ImportPreviewItemDTO(
            symbol=asset.symbol,
            name=asset.name,
            market=asset.market,
            category=asset.category,
            industry=asset.industry,
        )
        for asset in assets[:PREVIEW_LIMIT]
    )
    valid_count = len(assets)
    invalid_count = len(failures)
    return ImportPreviewDTO(
        filename=path.name,
        format=file_format,
        detected_count=valid_count + invalid_count,
        valid_count=valid_count,
        invalid_count=invalid_count,
        warnings=tuple(warnings),
        preview_items=preview_items,
        file_fingerprint=preview_fingerprint,
    )
