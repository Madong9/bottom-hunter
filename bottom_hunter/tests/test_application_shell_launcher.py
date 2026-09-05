"""Small product-launcher acceptance checks."""

from __future__ import annotations


def test_rain_effect_support_follows_selected_rhi(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages.application_shell_launcher import rain_effect_supported

    monkeypatch.setenv("QSG_RHI_BACKEND", "opengl")
    assert rain_effect_supported() is True
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    assert rain_effect_supported() is False
    monkeypatch.setenv("QSG_RHI_BACKEND", "null")
    assert rain_effect_supported() is False


def test_product_window_has_user_facing_title() -> None:
    from inspect import getsource

    from bottom_hunter.ui_demo.pages.application_shell_launcher import WINDOW_TITLE, main

    assert WINDOW_TITLE == "Bottom Hunter · 板块超跌反弹狩猎系统"
    assert not WINDOW_TITLE.endswith(".py")
    source = getsource(main)
    assert "view.setTitle(WINDOW_TITLE)" in source
    assert 'os.environ.setdefault("QSG_RHI_BACKEND", "opengl")' in source
    assert "QQuickWindow.setDefaultAlphaBuffer(True)" in source
    assert 'QGuiApplication.setApplicationName("Bottom Hunter")' in source
    assert 'QGuiApplication.setDesktopFileName("bottom-hunter")' in source
    assert "surface_format.setAlphaBufferSize(8)" in source
    assert "view.setColor(QColor(0, 0, 0, 0))" in source
    assert "apply_desktop_blur(int(view.winId()))" in source
