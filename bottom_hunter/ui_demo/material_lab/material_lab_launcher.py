"""CrystalGlassMaterialLab launcher — three-layer material study.

Layers (bottom → top):
  1. recognizable environment background (procedural night city)
  2. clear colorless optical glass (subtle blur + weak refraction)
  3. static realistic small rain droplets (screen-space lenses)

Batch mode (default) renders the lab screenshots and exits:
  background_only.png            layer 1 only
  clear_glass_no_rain.png        layers 1+2
  clear_glass_with_static_rain.png layers 1+2+3
  debug_droplets.png             layers 1+2+3 with u_debug=1 diameter proof
  refraction_calibration.png     layers 1+2+3 + calibration patch (refraction proof)
  final_material_rain.png        final polish output (rain)
  debug_droplets_final.png       final polish output (diameter proof)
  refraction_calibration_final.png final polish output (calibration patch)

Usage:
  .venv/bin/python -m bottom_hunter.ui_demo.material_lab.material_lab_launcher
  .venv/bin/python -m bottom_hunter.ui_demo.material_lab.material_lab_launcher --out shots
  .venv/bin/python -m bottom_hunter.ui_demo.material_lab.material_lab_launcher --modes rain,debug,calibration
  .venv/bin/python -m bottom_hunter.ui_demo.material_lab.material_lab_launcher --run
  .venv/bin/python -m bottom_hunter.ui_demo.material_lab.material_lab_launcher --run --debug-droplets

The GPU path needs a display with a working GL context (X11/Wayland).
--software forces the software RHI, where ShaderEffect may not render;
batch mode reports that instead of faking a result.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent

WIDTH = 1440
HEIGHT = 900

MODES = (
    ("background", "background_only.png"),
    ("glass", "clear_glass_no_rain.png"),
    ("rain", "clear_glass_with_static_rain.png"),
    ("debug", "debug_droplets.png"),
    ("calibration", "refraction_calibration.png"),
    ("final_rain", "final_material_rain.png"),
    ("final_debug", "debug_droplets_final.png"),
    ("final_calibration", "refraction_calibration_final.png"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CrystalGlassMaterialLab (3-layer material study)"
    )
    parser.add_argument(
        "--out",
        default=str(LAB_DIR / "shots"),
        help="screenshot output directory (default: <material_lab>/shots)",
    )
    parser.add_argument(
        "--modes",
        default=None,
        help="comma-separated subset of modes to render (default: all). "
        "Keys: " + ",".join(m for m, _ in MODES),
    )
    parser.add_argument(
        "--debug-droplets",
        action="store_true",
        help="interactive: show droplet bounding circles (u_debug=1, diameter proof)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="open an interactive window instead of batch screenshot mode",
    )
    parser.add_argument(
        "--software",
        action="store_true",
        help="force QSG_RHI_BACKEND=software (no-GPU fallback)",
    )
    return parser.parse_args(argv)


def _prepare_env(args: argparse.Namespace) -> None:
    # deterministic DPR: the lab is defined in logical px at DPR 1, and the
    # screenshots must be exactly WIDTH x HEIGHT pixels.
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    if args.software:
        os.environ["QSG_RHI_BACKEND"] = "software"
    else:
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")


def _select_modes(spec: str | None) -> list[tuple[str, str]]:
    """Resolve the --modes comma list (None = all modes) to (mode, file) pairs."""
    if not spec:
        return list(MODES)
    valid = dict(MODES)
    keys = [k.strip() for k in spec.split(",") if k.strip()]
    unknown = [k for k in keys if k not in valid]
    if unknown:
        raise SystemExit(
            f"unknown mode(s): {', '.join(unknown)}; valid: {', '.join(valid)}"
        )
    return [(k, valid[k]) for k in keys]


def _settle(app, ms: float) -> None:
    t0 = time.perf_counter()
    while (time.perf_counter() - t0) * 1000.0 < ms:
        app.processEvents()
        time.sleep(0.005)


def _size_of(v) -> tuple[int, int]:
    w = v.width() if hasattr(v, "width") else v.x()
    h = v.height() if hasattr(v, "height") else v.y()
    return int(w), int(h)


def _frame_delta(a, b) -> float:
    """Mean absolute per-channel difference on a coarse grid (sanity only)."""
    total, n = 0.0, 0
    step = 7
    w, h = min(a.width(), b.width()), min(a.height(), b.height())
    for y in range(0, h, step):
        for x in range(0, w, step):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += abs(ca.redF() - cb.redF()) + abs(ca.greenF() - cb.greenF()) + abs(ca.blueF() - cb.blueF())
            n += 1
    return total / (3.0 * n) if n else 0.0


def _make_view(qml_path: Path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickView

    view = QQuickView(QUrl.fromLocalFile(str(qml_path)))
    view.setColor(QColor("#04070E"))
    view.resize(WIDTH, HEIGHT)
    view.show()
    return view


def run_batch(app, args: argparse.Namespace) -> int:
    view = _make_view(LAB_DIR / "MaterialLab.qml")
    _settle(app, 700)

    root = view.rootObject()
    if root is None:
        print("ERROR: MaterialLab.qml failed to load", file=sys.stderr)
        return 2

    dpr = view.devicePixelRatio()
    tex_w, tex_h = _size_of(root.property("captureTextureSize"))
    print(
        f"[lab] platform={os.environ.get('QT_QPA_PLATFORM', 'auto')} "
        f"rhi={os.environ.get('QSG_RHI_BACKEND', 'auto')} dpr={dpr} "
        f"window={view.width()}x{view.height()} "
        f"ShaderEffectSource.textureSize={tex_w}x{tex_h}"
    )
    if abs(dpr - 1.0) > 1e-3:
        print(
            f"WARNING: devicePixelRatio={dpr} != 1.0 — grabs are {view.width() * dpr:.0f}px wide",
            file=sys.stderr,
        )
    if (tex_w, tex_h) != (WIDTH, HEIGHT):
        print(
            f"WARNING: textureSize {tex_w}x{tex_h} != expected {WIDTH}x{HEIGHT}",
            file=sys.stderr,
        )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    modes = _select_modes(args.modes)
    shots: dict[str, object] = {}
    for mode, filename in modes:
        root.setProperty("mode", mode)
        _settle(app, 500)
        img = view.grabWindow()
        expect = (int(WIDTH * dpr), int(HEIGHT * dpr))
        if (img.width(), img.height()) != expect:
            print(
                f"ERROR: {filename} grab size {img.width()}x{img.height()} != {expect}",
                file=sys.stderr,
            )
            return 3
        path = out / filename
        if not img.save(str(path)):
            print(f"ERROR: failed to save {path}", file=sys.stderr)
            return 3
        shots[mode] = img
        print(f"[lab] saved {path} ({img.width()}x{img.height()})")

    # sanity guard (not a visual assertion): every layer must change the frame,
    # otherwise the ShaderEffect pipeline is inactive (no GPU / software RHI).
    # Pairs are skipped when --modes filtered one side out.
    def _pair_delta(a: str, b: str) -> float | None:
        if a in shots and b in shots:
            return _frame_delta(shots[a], shots[b])
        return None

    deltas = {
        "glass": _pair_delta("background", "glass"),
        "rain": _pair_delta("glass", "rain"),
        "debug": _pair_delta("rain", "debug"),
    }
    fmt = lambda v: f"{v:.4f}" if v is not None else "n/a"
    print(
        f"[lab] frame delta: glass={fmt(deltas['glass'])} "
        f"rain={fmt(deltas['rain'])} debug={fmt(deltas['debug'])}"
    )
    if any(v is not None and v < 0.002 for v in deltas.values()):
        print(
            "WARNING: a layer did not change the frame — ShaderEffect pipeline may be "
            "inactive (no GPU / software backend). Glass/rain layers may be missing.",
            file=sys.stderr,
        )
        return 4

    view.close()
    return 0


def run_interactive(app, args: argparse.Namespace) -> int:
    view = _make_view(LAB_DIR / "MaterialLab.qml")
    _settle(app, 500)
    root = view.rootObject()
    if root is None:
        print("ERROR: MaterialLab.qml failed to load", file=sys.stderr)
        return 2
    root.setProperty("mode", "debug" if args.debug_droplets else "rain")
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _prepare_env(args)

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setApplicationName("CrystalGlassMaterialLab")

    if args.run:
        return run_interactive(app, args)
    return run_batch(app, args)


if __name__ == "__main__":
    raise SystemExit(main())
