"""3D liquid-glass droplet splash screen.

A real 3D scene rendered with QOpenGLWidget + GLSL shaders: a cluster of
glass droplets (icosphere meshes) lit by a MatCap texture, drifting in
a breathing cluster over the app's dark gradient. No extra dependencies
— PySide6 ships QtOpenGL, geometry is generated procedurally.

Design notes
------------
* MatCap shading gives the "real glass" look: the lighting+reflection
  response is baked into a 256px texture indexed by camera-space normals
  (technique from github.com/nidorx/matcaps).
* Fresnel rim + inner glow are added analytically in the fragment shader
  to fuse the droplets with the dark background.
* Droplets bob slowly (sine offsets); motion stays subtle so it reads as
  "liquid at rest" rather than a screensaver.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QElapsedTimer, QTimer
from PySide6.QtGui import QImage, QMatrix4x4, QSurfaceFormat, QVector3D
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture
from PySide6.QtOpenGLWidgets import QOpenGLWidget

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

VERTEX_SHADER = """
#version 140
in vec3 a_position;
in vec3 a_normal;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat4 u_model;
uniform mat3 u_normal_matrix;
out vec3 v_view_normal;
out vec3 v_view_position;
void main() {
    vec4 view_pos = u_view * u_model * vec4(a_position, 1.0);
    v_view_position = view_pos.xyz;
    v_view_normal = u_normal_matrix * a_normal;
    gl_Position = u_proj * view_pos;
}
"""

FRAGMENT_SHADER = """
#version 130
in vec3 v_view_normal;
in vec3 v_view_position;
uniform sampler2D u_matcap;
uniform vec3 u_tint;
uniform float u_alpha;
out vec4 frag_color;

void main() {
    vec3 normal = normalize(v_view_normal);
    // MatCap lookup: camera-space normal -> texture coordinate.
    vec2 muv = normal.xy * 0.5 + vec2(0.5);
    vec3 matcap = texture(u_matcap, muv).rgb;

    vec3 view_dir = normalize(-v_view_position);
    float fresnel = pow(1.0 - max(dot(normal, view_dir), 0.0), 3.0);

    // Tint the matcap towards the droplet colour, keep highlights white.
    vec3 body = matcap * u_tint;
    vec3 rim = vec3(0.62, 0.85, 0.95) * fresnel * 0.55;
    vec3 color = body + rim;

    // Soft alpha: centre solid, edges fade like a lens.
    float edge = smoothstep(0.0, 0.35, max(dot(normal, view_dir), 0.0));
    float alpha = u_alpha * mix(0.35, 1.0, edge);
    frag_color = vec4(color, alpha);
}
"""


def icosphere(subdivisions: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Unit icosphere; returns (vertices float32 [n,3], indices uint32 [m,3])."""
    t = (1.0 + 5.0**0.5) / 2.0
    base = np.array(
        [
            [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
            [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
            [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
        ],
        dtype=np.float64,
    )
    base /= np.linalg.norm(base, axis=1, keepdims=True)
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    vertices = [tuple(v) for v in base]
    cache: dict[tuple[int, int], int] = {}

    def midpoint(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key in cache:
            return cache[key]
        va = np.array(vertices[a])
        vb = np.array(vertices[b])
        mid = va + vb
        mid /= np.linalg.norm(mid)
        vertices.append(tuple(mid))
        cache[key] = len(vertices) - 1
        return cache[key]

    current = faces
    for _ in range(subdivisions):
        refined = []
        for a, b, c in current:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            refined += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        current = refined
    array = np.array(vertices, dtype=np.float32)
    indices = np.array(current, dtype=np.uint32)
    return array, indices


def look_at(eye: np.ndarray, center: np.ndarray, up: np.ndarray) -> np.ndarray:
    forward = center - eye
    forward /= np.linalg.norm(forward)
    side = np.cross(forward, up)
    side /= np.linalg.norm(side)
    up2 = np.cross(side, forward)
    matrix = np.eye(4, dtype=np.float32)
    matrix[0, :3], matrix[1, :3], matrix[2, :3] = side, up2, -forward
    matrix[0, 3] = -np.dot(side, eye)
    matrix[1, 3] = -np.dot(up2, eye)
    matrix[2, 3] = np.dot(forward, eye)
    return matrix


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    fov = math.radians(fov_deg)
    focal = 1.0 / math.tan(fov / 2)
    matrix = np.zeros((4, 4), dtype=np.float32)
    matrix[0, 0] = focal / aspect
    matrix[1, 1] = focal
    matrix[2, 2] = (far + near) / (near - far)
    matrix[2, 3] = 2 * far * near / (near - far)
    matrix[3, 2] = -1
    return matrix


DROPLETS = (
    # (x, y, z, radius, phase, wobble)
    (0.00, 0.05, 0.0, 1.00, 0.0, 0.030),
    (-1.55, 0.72, 0.55, 0.42, 1.7, 0.045),
    (1.48, 0.66, -0.40, 0.36, 3.1, 0.050),
    (-1.05, -0.95, -0.35, 0.30, 4.6, 0.055),
    (1.10, -1.02, 0.50, 0.26, 5.9, 0.060),
    (2.35, -0.10, 0.85, 0.20, 2.4, 0.065),
    (-2.45, -0.30, 0.75, 0.18, 0.8, 0.070),
)

TINTS = (
    (0.72, 0.95, 1.00),
    (0.62, 0.90, 0.98),
    (0.80, 0.96, 0.92),
    (0.58, 0.86, 1.00),
    (0.66, 0.92, 0.97),
    (0.74, 0.93, 0.88),
    (0.60, 0.88, 1.00),
)


class DropletGLWidget(QOpenGLWidget):
    """The 3D splash canvas; embed at the centre of the splash dialog."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        format = QSurfaceFormat()
        format.setSamples(0)
        format.setAlphaBufferSize(8)
        pass  # setFormat disabled during debugging
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        self._program = QOpenGLShaderProgram(self)
        self._vbo = None
        self._ibo = None
        self._index_count = 0
        self._timer = QElapsedTimer()
        self._timer.start()

    # ---- Qt overrides -------------------------------------------------

    def initializeGL(self) -> None:  # noqa: N802 (Qt naming)
        gl = self.context().functions()
        gl.glEnable(0x0BE2)  # GL_BLEND
        gl.glBlendFunc(0x0302, 0x0303)  # SRC_ALPHA / ONE_MINUS_SRC_ALPHA
        gl.glEnable(0x0B71)  # GL_DEPTH_TEST
        gl.glDepthFunc(0x0203)  # GL_LEQUAL
        gl.glClearColor(0.0, 0.0, 0.0, 0.0)

        self._program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX_SHADER)
        self._program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT_SHADER)
        self._program.bindAttributeLocation("a_position", 0)
        self._program.bindAttributeLocation("a_normal", 1)
        self._program.link()

        vertices, indices = icosphere(3)
        # Expand to a plain triangle list: drawArrays avoids the flaky
        # drawElements pointer marshalling in this PySide6 build.
        expanded = vertices[indices.reshape(-1)]
        self._vertex_count = int(expanded.shape[0])
        self._vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._vertex_buffer.create()
        self._vertex_buffer.bind()
        self._vertex_buffer.allocate(expanded.tobytes(), expanded.nbytes)
        self._vertex_buffer.release()

        image = QImage(str(ASSETS_DIR / "matcap_default.png"))
        self._matcap = self.bind_matcap(image)
        self.start_animation()

    def bind_matcap(self, image: QImage) -> QOpenGLTexture:
        texture = QOpenGLTexture(image.mirrored())
        texture.setMinificationFilter(QOpenGLTexture.Filter.LinearMipMapLinear)
        texture.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
        texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
        texture.generateMipMaps()
        return texture

    def resizeGL(self, width: int, height: int) -> None:  # noqa: N802
        gl = self.context().functions()
        gl.glViewport(0, 0, int(width * self.devicePixelRatioF()), int(height * self.devicePixelRatioF()))

    def paintGL(self) -> None:  # noqa: N802
        gl = self.context().functions()
        gl.glClear(0x4000 | 0x0100)  # GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT
        seconds = self._timer.elapsed() / 1000.0

        aspect = max(self.width(), 1) / max(self.height(), 1)
        view = look_at(np.array([0.0, 0.0, 4.6]), np.zeros(3), np.array([0.0, 1.0, 0.0]))
        proj = perspective(38.0, aspect, 0.1, 40.0)

        self._program.bind()
        self._matcap.bind(0)
        self._program.setUniformValue("u_matcap", 0)

        self._vertex_buffer.bind()
        stride = 3 * 4
        self._program.enableAttributeArray(0)
        self._program.setAttributeBuffer(0, 0x1406, 0, 3, stride)  # GL_FLOAT
        # Normals equal positions on a unit sphere: same buffer, same layout.
        self._program.enableAttributeArray(1)
        self._program.setAttributeBuffer(1, 0x1406, 0, 3, stride)

        for index, (x, y, z, radius, phase, wobble) in enumerate(DROPLETS):
            bob = math.sin(seconds * 0.7 + phase) * wobble
            sway = math.cos(seconds * 0.5 + phase * 1.3) * wobble * 0.6
            breathe = 1.0 + 0.015 * math.sin(seconds * 1.1 + phase)
            scale = radius * breathe
            model = np.eye(4, dtype=np.float32)
            model[0, 0] = scale
            model[1, 1] = scale
            model[2, 2] = scale
            model[0, 3] = x + sway
            model[1, 3] = y + bob
            model[2, 3] = z
            self._program.setUniformValue('u_view', _to_qmat4(view))
            self._program.setUniformValue('u_proj', _to_qmat4(proj))
            self._program.setUniformValue('u_model', _to_qmat4(model))
            # Uniform scale + rotation-free model: normal matrix is just scale³.
            normal_matrix = np.eye(3, dtype=np.float32) * scale
            self._program.setUniformValue('u_normal_matrix', _to_qmat3(normal_matrix))
            tint = TINTS[index % len(TINTS)]
            self._program.setUniformValue('u_tint', QVector3D(*tint))
            base_alpha = 0.92 if index == 0 else 0.80
            alpha_value = float(base_alpha + 0.04 * math.sin(seconds * 0.9 + phase))
            self._program.setUniformValue1f("u_alpha", alpha_value)
            gl.glDrawArrays(0x0004, 0, self._vertex_count)  # GL_TRIANGLES

        self._vertex_buffer.release()
        self._program.release()

    def start_animation(self) -> None:
        self._animator = QTimer(self)
        self._animator.timeout.connect(self.update)
        self._animator.start(33)  # ~30 fps: liquid, cheap.


def _to_qmat4(matrix: np.ndarray) -> QMatrix4x4:
    return QMatrix4x4(matrix.flatten().tolist())


def _to_qmat3(matrix: np.ndarray):
    from PySide6.QtGui import QMatrix3x3

    return QMatrix3x3(matrix.flatten().tolist())
