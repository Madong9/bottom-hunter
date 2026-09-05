"""Native compositor blur capability and protocol tests."""

from __future__ import annotations

from dataclasses import is_dataclass

from bottom_hunter.ui_demo.pages.desktop_blur import (
    BLUR_OPT_OUT,
    GNOME_BLUR_EXTENSION,
    GNOME_MUTTER_HINT,
    KWIN_BLUR_REGION,
    DesktopBlurCapability,
    DesktopBlurResult,
    apply_desktop_blur,
    detect_desktop_blur,
)


class RecordingWriter:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.failure = failure

    def set_text(self, window_id: int, name: str, value: str) -> None:
        if self.failure is not None:
            raise self.failure
        self.calls.append(("text", window_id, name, value))

    def set_empty_cardinal(self, window_id: int, name: str) -> None:
        if self.failure is not None:
            raise self.failure
        self.calls.append(("cardinal", window_id, name))


def test_desktop_blur_results_are_frozen_transport_values() -> None:
    for dto_type in (DesktopBlurCapability, DesktopBlurResult):
        assert is_dataclass(dto_type)
        assert dto_type.__dataclass_params__.frozen is True


def test_gnome_x11_detects_enabled_provider() -> None:
    capability = detect_desktop_blur(
        {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "x11"},
        enabled_extensions=[GNOME_BLUR_EXTENSION],
        extension_installed=True,
    )
    assert capability.backend == "gnome-x11"
    assert capability.compositor_ready is True


def test_gnome_request_uses_per_window_mutter_hint() -> None:
    writer = RecordingWriter()
    result = apply_desktop_blur(
        4242,
        {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "x11"},
        writer=writer,
        enabled_extensions=[GNOME_BLUR_EXTENSION],
        extension_installed=True,
        sigma=1200,
        brightness=1.4,
    )
    assert result.active is True
    assert writer.calls == [
        ("text", 4242, GNOME_MUTTER_HINT, "blur-provider=sigma:999,brightness:1.00")
    ]


def test_gnome_installs_hint_even_when_shell_reload_is_pending() -> None:
    writer = RecordingWriter()
    result = apply_desktop_blur(
        9,
        {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "x11"},
        writer=writer,
        enabled_extensions=[],
        extension_installed=True,
    )
    assert result.requested is True
    assert result.active is False
    assert writer.calls[0][2] == GNOME_MUTTER_HINT


def test_kwin_x11_requests_full_window_blur_region() -> None:
    writer = RecordingWriter()
    result = apply_desktop_blur(
        77,
        {"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11"},
        writer=writer,
    )
    assert result.active is True
    assert writer.calls == [("cardinal", 77, KWIN_BLUR_REGION)]


def test_opt_out_and_unsupported_sessions_do_not_touch_window() -> None:
    writer = RecordingWriter()
    result = apply_desktop_blur(
        77,
        {
            "XDG_CURRENT_DESKTOP": "GNOME",
            "XDG_SESSION_TYPE": "x11",
            BLUR_OPT_OUT: "0",
        },
        writer=writer,
    )
    assert result.backend == "disabled"
    assert result.requested is False
    assert writer.calls == []

    wayland = apply_desktop_blur(
        77,
        {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"},
        writer=writer,
    )
    assert wayland.backend == "gnome-wayland"
    assert wayland.requested is False
    assert writer.calls == []


def test_native_property_failure_becomes_safe_result() -> None:
    writer = RecordingWriter(failure=RuntimeError("display unavailable"))
    result = apply_desktop_blur(
        12,
        {"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11"},
        writer=writer,
    )
    assert result.active is False
    assert "display unavailable" in result.detail


def test_invalid_window_never_calls_native_writer() -> None:
    writer = RecordingWriter()
    result = apply_desktop_blur(
        0,
        {"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11"},
        writer=writer,
    )
    assert result.requested is False
    assert writer.calls == []
