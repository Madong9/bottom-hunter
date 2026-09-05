"""Native compositor blur requests for the transparent QML product window.

This module deliberately does not capture the screen.  It only publishes a
window-manager hint; the desktop compositor owns the pixels behind the window
and performs the blur without exposing those pixels to Bottom Hunter.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

GNOME_BLUR_EXTENSION = "blur-my-shell@aunetx"
GNOME_MUTTER_HINT = "_MUTTER_HINTS"
KWIN_BLUR_REGION = "_KDE_NET_WM_BLUR_BEHIND_REGION"
BLUR_OPT_OUT = "BOTTOM_HUNTER_DESKTOP_BLUR"


class WindowPropertyWriter(Protocol):
    """Small seam around native window properties, replaceable in tests."""

    def set_text(self, window_id: int, name: str, value: str) -> None: ...

    def set_empty_cardinal(self, window_id: int, name: str) -> None: ...


@dataclass(frozen=True)
class DesktopBlurCapability:
    desktop: str
    session_type: str
    backend: str
    compositor_ready: bool
    detail: str


@dataclass(frozen=True)
class DesktopBlurResult:
    backend: str
    requested: bool
    compositor_ready: bool
    detail: str

    @property
    def active(self) -> bool:
        """Whether the native request was installed and a provider is ready."""
        return self.requested and self.compositor_ready


def _extension_is_installed(extension: str = GNOME_BLUR_EXTENSION) -> bool:
    local = Path.home() / ".local/share/gnome-shell/extensions" / extension
    system = Path("/usr/share/gnome-shell/extensions") / extension
    return local.is_dir() or system.is_dir()


def _enabled_gnome_extensions() -> frozenset[str]:
    executable = shutil.which("gnome-extensions")
    if executable is None:
        return frozenset()
    try:
        result = subprocess.run(
            [executable, "list", "--enabled"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if result.returncode != 0:
        return frozenset()
    return frozenset(line.strip() for line in result.stdout.splitlines() if line.strip())


def detect_desktop_blur(
    environ: Mapping[str, str] | None = None,
    *,
    enabled_extensions: Sequence[str] | None = None,
    extension_installed: bool | None = None,
) -> DesktopBlurCapability:
    """Describe the compositor path without mutating desktop or window state."""
    env = os.environ if environ is None else environ
    desktop = env.get("XDG_CURRENT_DESKTOP", "").strip()
    session_type = env.get("XDG_SESSION_TYPE", "").strip().casefold()
    desktop_key = desktop.casefold()

    if env.get(BLUR_OPT_OUT, "1").strip().casefold() in {"0", "false", "no", "off"}:
        return DesktopBlurCapability(
            desktop, session_type, "disabled", False, "已通过环境变量关闭桌面合成器模糊。"
        )

    if session_type == "x11" and ("gnome" in desktop_key or "ubuntu" in desktop_key):
        enabled = (
            frozenset(enabled_extensions)
            if enabled_extensions is not None
            else _enabled_gnome_extensions()
        )
        installed = _extension_is_installed() if extension_installed is None else extension_installed
        if GNOME_BLUR_EXTENSION in enabled:
            detail = "GNOME 动态背景模糊已就绪。"
            ready = True
        elif installed:
            detail = "Blur My Shell 已安装但未在当前 GNOME Shell 会话启用。"
            ready = False
        else:
            detail = "缺少 Blur My Shell；运行 python setup_desktop_blur.py 后重载 GNOME Shell。"
            ready = False
        return DesktopBlurCapability(desktop, session_type, "gnome-x11", ready, detail)

    if session_type == "x11" and any(name in desktop_key for name in ("kde", "plasma")):
        return DesktopBlurCapability(
            desktop,
            session_type,
            "kwin-x11",
            True,
            "已向 KWin 请求整窗口 blur-behind；桌面特效中需启用“模糊”。",
        )

    if session_type == "wayland" and any(name in desktop_key for name in ("kde", "plasma")):
        return DesktopBlurCapability(
            desktop,
            session_type,
            "kwin-wayland",
            False,
            "KWin Wayland 需要 org_kde_kwin_blur 协议，当前 PySide6 未暴露该协议。",
        )

    if session_type == "wayland" and ("gnome" in desktop_key or "ubuntu" in desktop_key):
        return DesktopBlurCapability(
            desktop,
            session_type,
            "gnome-wayland",
            False,
            "当前 GNOME/PySide6 组合无可用的客户端背景模糊协议；请使用 X11 会话。",
        )

    return DesktopBlurCapability(
        desktop,
        session_type,
        "unsupported",
        False,
        "未识别到受支持的 GNOME/X11 或 KWin/X11 合成器。",
    )


class X11PropertyWriter:
    """Publish compositor hints with Xlib, without invoking shell commands."""

    PROP_MODE_REPLACE = 0

    def __init__(self) -> None:
        library_name = ctypes.util.find_library("X11")
        if library_name is None:
            raise RuntimeError("系统缺少 libX11，无法设置合成器模糊属性。")
        self._x11 = ctypes.CDLL(library_name)
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._x11.XCloseDisplay.restype = ctypes.c_int
        self._x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self._x11.XInternAtom.restype = ctypes.c_ulong
        self._x11.XChangeProperty.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
        ]
        self._x11.XChangeProperty.restype = ctypes.c_int
        self._x11.XFlush.argtypes = [ctypes.c_void_p]
        self._x11.XFlush.restype = ctypes.c_int

    def _change_property(
        self,
        window_id: int,
        name: str,
        type_name: str,
        value: bytes,
        format_bits: int,
        item_count: int,
    ) -> None:
        display = self._x11.XOpenDisplay(None)
        if not display:
            raise RuntimeError("无法连接 X11 DISPLAY。")
        try:
            prop_atom = self._x11.XInternAtom(display, name.encode("ascii"), 0)
            type_atom = self._x11.XInternAtom(display, type_name.encode("ascii"), 0)
            buffer = (ctypes.c_ubyte * max(1, len(value)))()
            if value:
                ctypes.memmove(buffer, value, len(value))
            self._x11.XChangeProperty(
                display,
                ctypes.c_ulong(window_id),
                prop_atom,
                type_atom,
                format_bits,
                self.PROP_MODE_REPLACE,
                buffer,
                item_count,
            )
            self._x11.XFlush(display)
        finally:
            self._x11.XCloseDisplay(display)

    def set_text(self, window_id: int, name: str, value: str) -> None:
        encoded = value.encode("utf-8")
        self._change_property(window_id, name, "UTF8_STRING", encoded, 8, len(encoded))

    def set_empty_cardinal(self, window_id: int, name: str) -> None:
        # KWindowSystem uses an empty CARDINAL property to mean the full client
        # region.  It is different from deleting the property.
        self._change_property(window_id, name, "CARDINAL", b"", 32, 0)


def apply_desktop_blur(
    window_id: int,
    environ: Mapping[str, str] | None = None,
    *,
    writer: WindowPropertyWriter | None = None,
    enabled_extensions: Sequence[str] | None = None,
    extension_installed: bool | None = None,
    sigma: int = 52,
    brightness: float = 0.96,
) -> DesktopBlurResult:
    """Ask the active compositor to blur pixels behind ``window_id``."""
    capability = detect_desktop_blur(
        environ,
        enabled_extensions=enabled_extensions,
        extension_installed=extension_installed,
    )
    if window_id <= 0:
        return DesktopBlurResult(capability.backend, False, False, "原生窗口尚未创建。")
    if capability.backend == "disabled":
        return DesktopBlurResult(capability.backend, False, False, capability.detail)

    property_writer = writer
    try:
        if capability.backend == "gnome-x11":
            property_writer = property_writer or X11PropertyWriter()
            safe_sigma = max(1, min(int(sigma), 999))
            safe_brightness = max(0.0, min(float(brightness), 1.0))
            property_writer.set_text(
                window_id,
                GNOME_MUTTER_HINT,
                f"blur-provider=sigma:{safe_sigma},brightness:{safe_brightness:.2f}",
            )
            return DesktopBlurResult(
                capability.backend,
                True,
                capability.compositor_ready,
                capability.detail,
            )
        if capability.backend == "kwin-x11":
            property_writer = property_writer or X11PropertyWriter()
            property_writer.set_empty_cardinal(window_id, KWIN_BLUR_REGION)
            return DesktopBlurResult(capability.backend, True, True, capability.detail)
    except (OSError, RuntimeError) as exc:
        return DesktopBlurResult(capability.backend, False, False, f"设置合成器模糊失败：{exc}")

    return DesktopBlurResult(capability.backend, False, False, capability.detail)


def main() -> int:
    capability = detect_desktop_blur()
    state = "就绪" if capability.compositor_ready else "未就绪"
    print(f"桌面模糊：{state}")
    print(f"后端：{capability.backend}")
    print(f"会话：{capability.desktop or '未知'} / {capability.session_type or '未知'}")
    print(capability.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
