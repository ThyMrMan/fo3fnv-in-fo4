"""The preview in a Qt window: a QOpenGLWidget drawing through render.Renderer; drag to orbit, wheel to zoom.

The OpenGL format is asked for before the QApplication exists (surface_format), 3.3 core, as macOS needs.
Importing this module needs no display; making the application does.

See: docs/fork/fo4_gui.md#preview
"""

from pathlib import Path

import moderngl
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication

from fo4_import.app.preview import scene
from fo4_import.app.preview.render import Camera, Renderer

#: Degrees turned per pixel dragged; zoom factor per wheel notch; zoom limits (multiples of the model's radius).
TURN, ZOOM_STEP, ZOOM_RANGE = 0.5, 0.9, (0.6, 20.0)


def surface_format() -> None:
    """Ask Qt for OpenGL 3.3 core with depth and 4x multisampling for every window (before QApplication)."""
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)


def open_model(mesh: str, files, materials) -> tuple:
    """(parts, surfaces) of `mesh`: a file on disk, else a Data path found through `files`."""
    raw = Path(mesh).read_bytes() if Path(mesh).is_file() else files.read(mesh)
    if raw is None:
        raise FileNotFoundError(f'{mesh} is not a file and no Data folder or archive has it')
    parts = scene.load(raw)
    return parts, [materials.surface(p) for p in parts]


class PreviewWidget(QOpenGLWidget):
    """A 3D preview of one model."""

    def __init__(self, parent=None):
        """An empty preview."""
        super().__init__(parent)
        self.camera, self.ctx, self.renderer, self.pending, self.last = Camera(), None, None, None, None
        self.setMinimumSize(320, 320)

    def show_model(self, parts: list, surfaces: list) -> None:
        """Draw `parts` (scene) with `surfaces` (materials) from now on."""
        self.pending = parts, surfaces
        if self.renderer is not None:
            self.makeCurrent()
            self.renderer.upload(*self.pending)
            self.doneCurrent()
        self.update()

    def initializeGL(self) -> None:
        """Make the moderngl context on Qt's and upload a model given before it existed."""
        self.ctx = moderngl.create_context()
        self.renderer = Renderer(self.ctx)
        if self.pending:
            self.renderer.upload(*self.pending)

    def paintGL(self) -> None:
        """Draw into Qt's framebuffer."""
        self.renderer.draw(self.ctx.detect_framebuffer(self.defaultFramebufferObject()), self.camera)

    def mousePressEvent(self, event) -> None:
        """Start a drag."""
        self.last = event.position()

    def mouseMoveEvent(self, event) -> None:
        """Orbit by the drag."""
        if self.last is not None:
            delta = event.position() - self.last
            self.camera.yaw -= delta.x() * TURN
            self.camera.pitch = max(-89.0, min(89.0, self.camera.pitch + delta.y() * TURN))
            self.last = event.position()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        """End a drag."""
        self.last = None

    def wheelEvent(self, event) -> None:
        """Zoom by the wheel."""
        zoom = self.camera.zoom * ZOOM_STEP ** (event.angleDelta().y() / 120.0)
        self.camera.zoom = max(ZOOM_RANGE[0], min(ZOOM_RANGE[1], zoom))
        self.update()


def show(parts: list, surfaces: list, title: str) -> int:
    """Open a window previewing `parts` until it is closed; the application's exit code."""
    surface_format()
    app = QApplication.instance() or QApplication([])
    widget = PreviewWidget()
    widget.setWindowTitle(title)
    widget.resize(800, 700)
    widget.show_model(parts, surfaces)
    widget.show()
    return app.exec()
