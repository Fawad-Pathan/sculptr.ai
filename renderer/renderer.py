from __future__ import annotations
import math
from typing import List, Tuple

from PySide6.QtCore import Qt, QPointF, QElapsedTimer, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget

# PyOpenGL (pip install PyOpenGL PyOpenGL_accelerate)
from OpenGL.GL import (
    glClearColor, glClear, glViewport, glEnable, glDisable, glLineWidth,
    glMatrixMode, glLoadIdentity, glTranslatef, glRotatef, glScalef, glBegin, glEnd,
    glVertex3f, glColor3f, glPolygonMode,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_CULL_FACE,
    GL_PROJECTION, GL_MODELVIEW, GL_TRIANGLES, GL_FRONT_AND_BACK, GL_FILL, GL_LINE
)
from OpenGL.GLU import gluPerspective


def _hex_to_rgbf(h: str) -> Tuple[float, float, float]:
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


class SimpleGLViewport(QOpenGLWidget):
    """
    Minimal 3D viewport:
      • Loads OBJ (triangulates quads / n-gons)
      • FPS cam: WASD, Space/Ctrl up/down, Shift sprint
      • Mouse look: hold Right Mouse Button
      • Esc releases mouse look
    """

    def __init__(self, parent=None, bg_hex: str = "#1b1b1f", line_hex: str = "#E6E6EA", obj_path: str = "cube.obj"):
        super().__init__(parent)

        # Request compat profile so fixed-function pipeline works
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.NoProfile)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)

        # Appearance
        self._bg = (*_hex_to_rgbf(bg_hex), 1.0)
        self._mesh_color = _hex_to_rgbf(line_hex)

        # Camera state
        self._cam_pos = [0.0, 0.0, 4.5]   # x, y, z (y is up)
        self._yaw = 0.0                   # degrees
        self._pitch = 0.0                 # degrees
        self._speed = 3.0                 # units/sec
        self._mouse_sens = 0.12           # deg per pixel
        self._keys = set()
        self._mouse_look = False
        self._last_mouse = QPointF(0, 0)

        # Timing
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)   # <-- requires def _tick below
        self._timer.start(16)  # ~60 FPS
        self._dt_timer = QElapsedTimer()
        self._dt_timer.start()

        # Mesh
        self._obj_path = obj_path
        self._tris: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]] = []
        self._center = (0.0, 0.0, 0.0)
        self._scale = 1.0

        # Input focus
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

    # ---------- Public API ----------
    def reset_view(self):
        self._cam_pos[:] = [0.0, 0.0, 4.5]
        self._yaw = 0.0
        self._pitch = 0.0
        self.update()

    # ---------- QOpenGLWidget ----------
    def initializeGL(self):
        glClearColor(*self._bg)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glLineWidth(1.6)

        # Try load OBJ; fallback if missing
        try:
            self._load_obj(self._obj_path)
        except Exception:
            self._make_default_cube()

        self._normalize_mesh()

    def resizeGL(self, w: int, h: int):
        h = max(1, h)
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Projection
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = max(1e-3, self.width() / max(1.0, float(self.height())))
        gluPerspective(60.0, aspect, 0.05, 1000.0)

        # View
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glRotatef(-self._pitch, 1, 0, 0)
        glRotatef(-self._yaw,   0, 1, 0)
        glTranslatef(-self._cam_pos[0], -self._cam_pos[1], -self._cam_pos[2])

        # Model (center + scale)
        glTranslatef(-self._center[0], -self._center[1], -self._center[2])
        glScalef(self._scale, self._scale, self._scale)

        # Solid
        glColor3f(*self._mesh_color)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glBegin(GL_TRIANGLES)
        for a, b, c in self._tris:
            glVertex3f(*a); glVertex3f(*b); glVertex3f(*c)
        glEnd()

        # Wireframe overlay
        glDisable(GL_CULL_FACE)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glLineWidth(1.0)
        glBegin(GL_TRIANGLES)
        for a, b, c in self._tris:
            glVertex3f(*a); glVertex3f(*b); glVertex3f(*c)
        glEnd()
        glEnable(GL_CULL_FACE)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    # ---------- Input ----------
    def keyPressEvent(self, e):
        self._keys.add(e.key())
        if e.key() == Qt.Key_Escape and self._mouse_look:
            self._mouse_look = False
            self.unsetCursor()
            self.releaseMouse()

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        self._keys.discard(e.key())

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._mouse_look = True
            self._last_mouse = e.position()
            self.setCursor(Qt.BlankCursor)
            self.grabMouse()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            self._mouse_look = False
            self.unsetCursor()
            self.releaseMouse()

    def mouseMoveEvent(self, e):
        if not self._mouse_look:
            return
        delta = e.position() - self._last_mouse
        self._last_mouse = e.position()
        self._yaw   = (self._yaw   + delta.x() * self._mouse_sens) % 360.0
        self._pitch = max(-89.0, min(89.0, self._pitch - delta.y() * self._mouse_sens))
        self.update()

    # ---------- Tick ----------
    def _tick(self):
        dt_ms = self._dt_timer.restart()
        dt = max(0.0, dt_ms / 1000.0)
        if self.hasFocus():
            self._update_movement(dt)
        self.update()

    def _update_movement(self, dt: float):
        yaw = math.radians(self._yaw)
        forward = [math.sin(yaw), 0.0, -math.cos(yaw)]
        right   = [math.cos(yaw), 0.0,  math.sin(yaw)]

        speed = self._speed * (2.25 if (Qt.Key_Shift in self._keys or Qt.Key_Shift_L in self._keys or Qt.Key_Shift_R in self._keys) else 1.0)

        vel = [0.0, 0.0, 0.0]
        if Qt.Key_W in self._keys: vel = [vel[i] + forward[i] for i in range(3)]
        if Qt.Key_S in self._keys: vel = [vel[i] - forward[i] for i in range(3)]
        if Qt.Key_D in self._keys: vel = [vel[i] + right[i]   for i in range(3)]
        if Qt.Key_A in self._keys: vel = [vel[i] - right[i]   for i in range(3)]
        if Qt.Key_Space in self._keys:  vel[1] += 1.0
        if Qt.Key_Control in self._keys or Qt.Key_C in self._keys: vel[1] -= 1.0

        mag = math.sqrt(vel[0]*vel[0] + vel[1]*vel[1] + vel[2]*vel[2])
        if mag > 1e-6:
            vel = [v / mag for v in vel]
            self._cam_pos[0] += vel[0] * speed * dt
            self._cam_pos[1] += vel[1] * speed * dt
            self._cam_pos[2] += vel[2] * speed * dt

    # ---------- OBJ loading & normalization ----------
    def _load_obj(self, path: str):
        verts: List[Tuple[float, float, float]] = []
        faces: List[List[int]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line or line.startswith("#"):
                    continue
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "v" and len(parts) >= 4:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                elif parts[0] == "f" and len(parts) >= 4:
                    idxs = []
                    for tok in parts[1:]:
                        vtok = tok.split("/")[0]
                        if not vtok:
                            continue
                        i = int(vtok)
                        if i < 0:
                            i = len(verts) + i + 1
                        idxs.append(i - 1)
                    faces.append(idxs)

        tris: List[Tuple[Tuple[float,float,float], Tuple[float,float,float], Tuple[float,float,float]]] = []
        for face in faces:
            if len(face) == 3:
                a,b,c = face
                tris.append((verts[a], verts[b], verts[c]))
            elif len(face) == 4:
                a,b,c,d = face
                tris.append((verts[a], verts[b], verts[c]))
                tris.append((verts[a], verts[c], verts[d]))
            else:
                # fan triangulate n-gons
                for i in range(1, len(face)-1):
                    tris.append((verts[face[0]], verts[face[i]], verts[face[i+1]]))

        if not tris:
            raise ValueError("OBJ contained no faces")
        self._tris = tris

    def _make_default_cube(self):
        s = 0.5
        v = [(-s,-s,-s),( s,-s,-s),( s, s,-s),(-s, s,-s),
             (-s,-s, s),( s,-s, s),( s, s, s),(-s, s, s)]
        idx = [
            (0,1,2),(0,2,3),
            (4,5,6),(4,6,7),
            (0,1,5),(0,5,4),
            (2,3,7),(2,7,6),
            (1,2,6),(1,6,5),
            (0,3,7),(0,7,4),
        ]
        self._tris = [(v[a], v[b], v[c]) for a,b,c in idx]

    def _normalize_mesh(self):
        xs = [p[0] for tri in self._tris for p in tri]
        ys = [p[1] for tri in self._tris for p in tri]
        zs = [p[2] for tri in self._tris for p in tri]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        minz, maxz = min(zs), max(zs)
        cx, cy, cz = (minx + maxx)/2.0, (miny + maxy)/2.0, (minz + maxz)/2.0
        size = max(maxx-minx, maxy-miny, maxz-minz, 1e-6)
        self._center = (cx, cy, cz)
        self._scale = 2.0 / size  # fit into ~2x2x2
