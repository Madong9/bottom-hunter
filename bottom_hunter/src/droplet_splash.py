"""Liquid-glass droplet splash: 3D canvas + brand text + progress bar.

Shown at startup while the main window warms up; fades out automatically.
The 3D part (DropletGLWidget) is real OpenGL — glass droplets shaded by
a MatCap texture with Fresnel rim lighting.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .droplet_scene import DropletGLWidget


class DropletSplash(QWidget):
    """Frameless translucent splash; call :meth:`finish` to fade out."""

    def __init__(self, app_style: str = "", parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(880, 560)

        self.setStyleSheet(
            """
            QLabel[role="splashTitle"] {
                font-size: 34px; font-weight: 800; color: #f2f6f9;
                letter-spacing: 1px;
            }
            QLabel[role="splashTag"] {
                font-size: 11pt; color: #7b8290;
            }
            QLabel[role="splashChip"] {
                background: rgba(43, 213, 118, 0.10);
                border: 1px solid rgba(43, 213, 118, 0.30);
                border-radius: 13px;
                color: #43d98b;
                font-size: 9pt; font-weight: 600;
                padding: 5px 14px;
            }
            QProgressBar {
                background: rgba(255,255,255,0.07);
                border: none; border-radius: 2px;
                max-height: 4px; min-height: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2bd576, stop:1 #4da3ff);
                border-radius: 2px;
            }
            """
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.gl = DropletGLWidget(self)
        self.gl.start_animation()
        root_layout.addWidget(self.gl, 1)

        overlay = QWidget(self)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay_layout = QGridLayout(overlay)
        overlay_layout.setContentsMargins(56, 0, 56, 44)
        overlay_layout.setVerticalSpacing(8)

        self.title = QLabel("Bottom Hunter")
        self.title.setProperty("role", "splashTitle")
        self.tagline = QLabel("板块超跌反弹狩猎系统 · 研究模式")
        self.tagline.setProperty("role", "splashTag")

        chip_row = QHBoxLayout()
        chip_row.setSpacing(10)
        self.chip = QLabel("正在唤醒行情引擎…")
        self.chip.setProperty("role", "splashChip")
        chip_row.addWidget(self.chip)
        chip_row.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(8)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(320)

        overlay_layout.addWidget(self.title, 0, 0, Qt.AlignmentFlag.AlignLeft)
        overlay_layout.addWidget(self.tagline, 1, 0, Qt.AlignmentFlag.AlignLeft)
        overlay_layout.addWidget(self.progress, 2, 0, Qt.AlignmentFlag.AlignLeft)
        overlay_layout.addWidget(self.chip, 3, 0, Qt.AlignmentFlag.AlignLeft)
        overlay_layout.setRowStretch(4, 1)

        # 动态打点：行情/评分/验证/推送 四阶段文案轮换
        self._stages = (
            "正在唤醒行情引擎…",
            "加载 MatCap 玻璃渲染…",
            "校准信号评分模型…",
            "连接研究数据缓存…",
        )
        self._stage_index = 0
        self._dot_timer = None
        self._fade_timer = None
        self._fade_step = 0
        self.finished = False

    def start_progress(self) -> None:
        """Animate the stage text and progress towards ~92%."""
        from PySide6.QtCore import QTimer

        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._advance_stage)
        self._dot_timer.start(620)

    def _advance_stage(self) -> None:
        self._stage_index = (self._stage_index + 1) % len(self._stages)
        self.chip.setText(self._stages[self._stage_index])
        target = min(92, 8 + (self._stage_index + 1) * 21)
        self.progress.setValue(target)

    def set_progress(self, value: int, message: str | None = None) -> None:
        self.progress.setValue(max(0, min(100, int(value))))
        if message:
            self.chip.setText(message)

    def finish(self) -> None:
        """Fade the splash out and close it."""
        if self.finished:
            return
        self.finished = True
        if self._dot_timer is not None:
            self._dot_timer.stop()
        self.progress.setValue(100)
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_step_down)
        self._fade_timer.start(18)

    def _fade_step_down(self) -> None:
        self._fade_step += 1
        self.setWindowOpacity(max(0.0, 1.0 - self._fade_step / 22))
        if self._fade_step >= 22:
            self._fade_timer.stop()
            self.close()
