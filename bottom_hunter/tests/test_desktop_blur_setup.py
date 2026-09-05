"""Tests for the explicit GNOME blur-provider setup utility."""

from __future__ import annotations

import json
import zipfile

import pytest
import setup_desktop_blur as setup


def test_metadata_compatibility_requires_expected_uuid_and_shell() -> None:
    metadata = {
        "uuid": setup.EXTENSION_UUID,
        "shell-version": ["42", "43", "44"],
    }
    assert setup.metadata_supports(metadata, "42") is True
    assert setup.metadata_supports(metadata, "45") is False
    assert setup.metadata_supports({**metadata, "uuid": "unexpected"}, "42") is False


def test_archive_validation_rejects_wrong_shell(tmp_path) -> None:
    archive = tmp_path / "extension.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(
            "metadata.json",
            json.dumps({"uuid": setup.EXTENSION_UUID, "shell-version": ["44"]}),
        )
    with pytest.raises(RuntimeError, match="不支持 GNOME Shell 42"):
        setup.validate_archive(archive, "42")


def test_queue_enable_preserves_existing_extensions(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(setup, "command_output", lambda *args: "['one@example']")
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command),
    )
    setup.queue_extension_enable()
    assert calls == [
        [
            "gsettings",
            "set",
            "org.gnome.shell",
            "enabled-extensions",
            "['one@example', 'blur-my-shell@aunetx']",
        ]
    ]


def test_queue_enable_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(
        setup,
        "command_output",
        lambda *args: "@as ['blur-my-shell@aunetx']",
    )
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must not rewrite an unchanged setting"),
    )
    setup.queue_extension_enable()
