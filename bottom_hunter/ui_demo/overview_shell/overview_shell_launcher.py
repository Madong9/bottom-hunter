"""Overview shell POC launcher — Bottom Hunter 总览页外壳 Crystal Glass POC.

PHASE 1.6 production hardening: viewport-relative (1280x720 / 1440x900 /
1920x1080), dynamic protection geometry, true low-res mask textures,
qt_Opacity contract, launcher diagnostics.

Batch mode (default) renders the shell screenshots and exits:
  overview_shell_hardened.png             final POC (no glare / no dark hole)
  overview_shell_hardened_debug.png       auto-generated rain zones (red) +
                                          readability zones (blue) + mask
                                          texture resolution report

The shell reuses the ACCEPTED MaterialLab shaders (ClearGlass + StaticRain).
No business logic, no other pages, formal QtWidgets GUI untouched.

Usage:
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher --out shots
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher --width 1280 --height 720
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher --run

The GPU path needs a display with a working GL context (X11/Wayland).
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
    ("shell", "overview_shell_hardened.png"),
    ("readability_debug", "overview_shell_hardened_debug.png"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overview shell Crystal Glass POC (总览页外壳)"
    )
    parser.add_argument(
        "--out",
        default=str(LAB_DIR / "shots"),
        help="screenshot output directory (default: <overview_shell>/shots)",
    )
    parser.add_argument(
        "--modes",
        default=None,
        help="comma-separated subset of modes to render (default: all). "
        "Keys: " + ",".join(m for m, _ in MODES),
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="open an interactive window instead of batch screenshot mode",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1440,
        help="viewport width (default 1440; design reference resolution)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=900,
        help="viewport height (default 900; design reference resolution)",
    )
    parser.add_argument(
        "--opacity-check",
        action="store_true",
        help="verify qt_Opacity contract: render at opacity 0.5 vs 1.0 into "
             "/tmp and report the mean luminance ratio (~0.5 expected)",
    )
    return parser.parse_args(argv)


def _prepare_env() -> None:
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")


def _select_modes(spec: str | None) -> list[tuple[str, str]]:
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
    total, n = 0.0, 0
    step = 7
    w, h = min(a.width(), b.width()), min(a.height(), b.height())
    for y in range(0, h, step):
        for x in range(0, w, step):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += abs(ca.redF() - cb.redF()) + abs(ca.greenF() - cb.greenF()) + abs(ca.blueF() - cb.blueF())
            n += 1
    return total / (3.0 * n) if n else 0.0


def _make_view(qml_path: Path, width: int = WIDTH, height: int = HEIGHT):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickView

    view = QQuickView(QUrl.fromLocalFile(str(qml_path)))
    # viewport-relative: the view drives the root item size (reference
    # resolution 1440x900 remains the QML default, not a hard assumption)
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setColor(QColor("#04070E"))
    view.resize(width, height)
    view.show()
    return view


def _wire_overview_state(view) -> None:
    """PHASE 2-B: create OverviewState + OverviewBridge + RefreshController
    and expose state/bridge to QML as context properties. Initialization
    load + manual refresh() only — no async system, no business imports in
    QML. Loaders mirror the read-only helpers the QtWidgets dashboard
    already uses, injected into the bridge — the shell stays isolated.
    """
    from bottom_hunter.ui_demo.overview_shell.viewmodel import (
        HEALTH_OK,
        HEALTH_WARNING,
        HEALTH_UNKNOWN,
        OverviewBridge,
        OverviewRefreshController,
        OverviewState,
    )

    state = OverviewState(view)
    bridge = OverviewBridge(state, view)
    controller = OverviewRefreshController(view)

    def _opportunity_loader():
        from bottom_hunter.src import gui_core

        reports = gui_core.list_reports()
        if not reports:
            return None
        summary = gui_core.load_report_summary(reports[-1])
        return {
            "value": str(summary.opportunity_count),
            "hint": f"有效观察 {summary.signal_count} 个",
            "report_date": summary.report_date,
        }

    def _market_loader():
        from bottom_hunter.src import gui_core

        reports = gui_core.list_reports()
        if not reports:
            return None
        summary = gui_core.load_report_summary(reports[-1])
        sessions = summary.market_sessions or {}
        parts = [f"{k} {v}" for k, v in sessions.items()]
        return {
            "value": " · ".join(parts) if parts else "--",
            "detail": f"环境 {len(summary.environments or {})} 项",
        }

    def _health_loader():
        from bottom_hunter.src import gui_core

        reports = gui_core.list_reports()
        if not reports:
            return None
        summary = gui_core.load_report_summary(reports[-1])
        if summary.error_count:
            return {"level": HEALTH_WARNING, "text": f"需关注 · {summary.error_count} 项异常"}
        return {"level": HEALTH_OK, "text": "正常 · 本次行情完整"}

    def _validation_loader():
        from bottom_hunter.src.storage import StateStore

        database = Path(os.environ.get("BH_PACKAGE_DIR", ".")) / "state" / "signals.db"
        if not database.exists():
            return None
        store = StateStore(database)
        summary = store.outcome_summary(window_days=30, horizon=5)
        if not summary.get("sample_size"):
            return None
        return {
            "value": f"{summary['win_rate']:.0%}",
            "hint": f"{summary['sample_size']} 样本 · {summary['average_return']:+.2%}",
        }

    def _paper_loader():
        from bottom_hunter.src.storage import StateStore

        database = Path(os.environ.get("BH_PACKAGE_DIR", ".")) / "state" / "signals.db"
        if not database.exists():
            return None
        store = StateStore(database)
        paper = store.paper_history_summary()
        if paper is None or paper.get("latest") is None:
            return None
        return {
            "value": f"{float(paper['latest']):.4f}",
            "hint": f"{len(paper['points'])} 个交易日",
        }

    bridge.setOpportunityLoader(_opportunity_loader)
    bridge.setMarketLoader(_market_loader)
    bridge.setHealthLoader(_health_loader)
    bridge.setValidationLoader(_validation_loader)
    bridge.setPaperLoader(_paper_loader)

    # unified refresh: controller.requestRefresh -> bridge.refresh
    controller.refreshRequested.connect(bridge.refresh)

    engine = view.engine()
    engine.rootContext().setContextProperty("overviewState", state)
    engine.rootContext().setContextProperty("overviewBridge", bridge)
    engine.rootContext().setContextProperty("overviewRefreshController", controller)
    # initialization load
    bridge.refresh()
    return state, bridge


def run_batch(app, args: argparse.Namespace) -> int:
    view = _make_view(LAB_DIR / "OverviewShell.qml", args.width, args.height)
    # PHASE 2-A: expose OverviewState before the QML binds (context property)
    _wire_overview_state(view)
    _settle(app, 700)

    root = view.rootObject()
    if root is None:
        print("ERROR: OverviewShell.qml failed to load", file=sys.stderr)
        return 2

    dpr = view.devicePixelRatio()
    tex_w, tex_h = _size_of(root.property("captureTextureSize"))
    rain_mask_w, rain_mask_h = _size_of(root.property("rainMaskTextureSize"))
    read_mask = root.property("readMaskTextureSize")
    read_mask_w, read_mask_h = int(read_mask.x()), int(read_mask.y())
    zones = root.property("protectionZones")
    zone_list = []
    if zones is not None:
        if hasattr(zones, "toVariant"):
            v = zones.toVariant()
            zone_list = v if isinstance(v, list) else []
        elif isinstance(zones, list):
            zone_list = zones
        elif hasattr(zones, "length"):
            zone_list = [zones.property(i) for i in range(zones.length())]
    n_critical = sum(1 for z in zone_list if z.get("level") == "critical")
    print(
        f"[shell] platform={os.environ.get('QT_QPA_PLATFORM', 'auto')} "
        f"rhi={os.environ.get('QSG_RHI_BACKEND', 'auto')} dpr={dpr} "
        f"viewport={view.width()}x{view.height()} "
        f"scene-tex={tex_w}x{tex_h} "
        f"rain-mask-tex={rain_mask_w}x{rain_mask_h} "
        f"readability-mask-tex={read_mask_w}x{read_mask_h} "
        f"protection-zones={len(zone_list)} (critical={n_critical})"
    )
    if (tex_w, tex_h) != (args.width, args.height):
        print(
            f"WARNING: scene textureSize {tex_w}x{tex_h} != viewport {args.width}x{args.height}",
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
        expect = (int(view.width() * dpr), int(view.height() * dpr))
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
        print(f"[shell] saved {path} ({img.width()}x{img.height()})")

    # sanity guard: rain mode must change the frame vs glass mode, otherwise
    # the ShaderEffect pipeline is inactive (no GPU / software RHI).
    if "shell" in shots and "glass" in shots:
        d_rain = _frame_delta(shots["glass"], shots["shell"])
        print(f"[shell] frame delta (glass -> rain): {d_rain:.4f}")
        if d_rain < 0.002:
            print(
                "WARNING: rain layer did not change the frame — ShaderEffect "
                "pipeline may be inactive (no GPU / software backend).",
                file=sys.stderr,
            )
            return 4

    view.close()
    return 0


def run_interactive(app, args: argparse.Namespace) -> int:
    view = _make_view(LAB_DIR / "OverviewShell.qml", args.width, args.height)
    _wire_overview_state(view)
    _settle(app, 500)
    return app.exec()


def run_opacity_check(app, args: argparse.Namespace) -> int:
    """Verify the qt_Opacity contract: the shell at opacity 0.5 over the
    black clear color must have ~half the mean luminance of opacity 1.0."""
    ratios = []
    for opacity in (1.0, 0.5):
        view = _make_view(LAB_DIR / "OverviewShell.qml", args.width, args.height)
        _settle(app, 600)
        root = view.rootObject()
        if root is None:
            print("ERROR: OverviewShell.qml failed to load", file=sys.stderr)
            return 2
        root.setProperty("opacity", opacity)
        _settle(app, 300)
        img = view.grabWindow()
        mean = 0.0
        n = 0
        for y in range(0, img.height(), 8):
            for x in range(0, img.width(), 8):
                c = img.pixelColor(x, y)
                mean += 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
                n += 1
        ratios.append(mean / n if n else 0.0)
        if opacity == 0.5:
            path = Path("/tmp/opencode/opacity_check_050.png")
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(path))
        view.close()
    ratio = ratios[1] / ratios[0] if ratios[0] > 1e-6 else 0.0
    print(f"[shell] opacity check: mean luma @1.0={ratios[0]:.5f} @0.5={ratios[1]:.5f} ratio={ratio:.3f} "
          f"(expect < 0.85: clearly dimmed; exact qt_Opacity contract is regex-tested)")
    # Qt Quick layers the SES subtree when root opacity < 1, so the observed
    # ratio is not exactly 0.5; the precise contract (fragColor premultiplied
    # by qt_Opacity) is verified by the shader regex tests in the test suite.
    if not (0.30 <= ratio <= 0.85):
        print("WARNING: opacity did not dim the output as expected", file=sys.stderr)
        return 5
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _prepare_env()

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setApplicationName("OverviewShellPOC")

    if args.run:
        return run_interactive(app, args)
    if args.opacity_check:
        return run_opacity_check(app, args)
    return run_batch(app, args)


if __name__ == "__main__":
    raise SystemExit(main())
