# renderer/renderer.py
# Simple QOpenGLWidget 3D viewer with:
# - OBJ loader (triangulates n-gons)
# - Grid floor like Blender
# - Free-fly camera (WASD + mouse look)
# - Basic OpenGL fixed-function lighting
# - reset_view() and load_new_obj() for ui.py

from __future__ import annotations
import math, os, time
from typing import List, Tuple

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QPoint, QTimer
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluLookAt

def _hex_to_rgbf(h: str) -> Tuple[float, float, float]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return r, g, b

def _normalize(v):
    x, y, z = v
    l = math.sqrt(x*x + y*y + z*z) or 1.0
    return (x/l, y/l, z/l)

def _cross(a, b):
    ax, ay, az = a; bx, by, bz = b
    return (ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx)

def _sub(a,b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def _add(a,b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def _mul(v, s: float):
    return (v[0]*s, v[1]*s, v[2]*s)

class SimpleGLViewport(QOpenGLWidget):
    def __init__(self, parent=None, bg_hex="#1b1b1f", line_hex="#E6E6EA", obj_path=None):
        super().__init__(parent)
        self._bg = _hex_to_rgbf(bg_hex)
        self._line = _hex_to_rgbf(line_hex)

        # mesh
        self._verts: List[Tuple[float,float,float]] = []
        self._faces: List[Tuple[int,int,int]] = []
        self._vnorms: List[Tuple[float,float,float]] = []  # per-vertex normals
        self._bbox = None     # (minx,miny,minz,maxx,maxy,maxz)
        self._center = (0.0, 0.0, 0.0)
        self._grid_enabled = True

        # camera (free-fly)
        self._yaw = 35.0
        self._pitch = -20.0
        self._dist = 3.5         # framing distance used by reset
        self._cam_pos = (0.0, 0.75, 3.5)  # starting pos slightly above ground
        self._move_speed = 1.5
        self._keys = set()

        # mouse
        self._last_mouse = QPoint()
        self._dragging_look = False

        # timer for continuous movement
        self._last_t = time.perf_counter()
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(16)

        self.setFocusPolicy(Qt.StrongFocus)  # capture WASD

        # optionally load obj
        if obj_path and os.path.exists(obj_path):
            self._load_obj(obj_path)
            self._frame_to_fit()

    # ------------- public API (used by ui.py) -------------
    def reset_view(self):
        if self._bbox:
            self._frame_to_fit()
        else:
            # default
            self._yaw, self._pitch = 35.0, -20.0
            self._cam_pos = (0.0, 0.75, 3.5)
            self._dist = 3.5
        self.update()

    def load_new_obj(self, path: str):
        if os.path.exists(path):
            self._load_obj(path)
            self._frame_to_fit()
            self.update()

    # ------------- GL lifecycle -------------
    def initializeGL(self):
        r,g,b = self._bg
        glClearColor(r, g, b, 1.0)
        glEnable(GL_DEPTH_TEST)

        # lighting
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, (5.0, 8.0, 5.0, 1.0))     # pos
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  (0.95, 0.95, 0.95, 1.0))
        glLightfv(GL_LIGHT0, GL_SPECULAR, (0.65, 0.65, 0.65, 1.0))
        glLightfv(GL_LIGHT0, GL_AMBIENT,  (0.15, 0.15, 0.18, 1.0))

        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.25, 0.25, 0.25, 1.0))
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
        glShadeModel(GL_SMOOTH)

    def resizeGL(self, w, h):
        if h == 0: h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w/float(h), 0.05, 500.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # camera
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        fwd, right, up = self._basis()
        target = _add(self._cam_pos, fwd)
        gluLookAt(self._cam_pos[0], self._cam_pos[1], self._cam_pos[2],
                  target[0],        target[1],        target[2],
                  up[0],            up[1],            up[2])

        # draw grid (unlit lines)
        if self._grid_enabled:
            glDisable(GL_LIGHTING)
            self._draw_grid()
            glEnable(GL_LIGHTING)

        # draw mesh (lit)
        self._draw_mesh()

    # ------------- per-frame update -------------
    def _tick(self):
        now = time.perf_counter()
        dt = max(0.0, min(0.05, now - self._last_t))
        self._last_t = now
        self._update_movement(dt)
        self.update()

    # ------------- input -------------
    def keyPressEvent(self, e):
        self._keys.add(e.key())
        if e.key() == Qt.Key_R:
            self.reset_view()
        elif e.key() == Qt.Key_G:
            self._grid_enabled = not self._grid_enabled
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        # make sure to remove even if auto-repeated
        self._keys.discard(e.key())
        super().keyReleaseEvent(e)

    def mousePressEvent(self, e):
        self.setFocus()  # ensure key events go here
        if e.button() == Qt.RightButton:
            self._dragging_look = True
        self._last_mouse = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            self._dragging_look = False
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e):
        p = e.position().toPoint()
        dx = p.x() - self._last_mouse.x()
        dy = p.y() - self._last_mouse.y()
        self._last_mouse = p

        if self._dragging_look:
            # mouse sensitivity
            self._yaw   += dx * 0.2
            self._pitch += -dy * 0.2
            self._pitch = max(-89.9, min(89.9, self._pitch))
        self.update()
        super().mouseMoveEvent(e)

    def wheelEvent(self, e):
        # dolly forward/back
        delta = e.angleDelta().y() / 120.0
        speed = self._move_speed * 0.75
        fwd, _, _ = self._basis()
        self._cam_pos = _add(self._cam_pos, _mul(fwd, delta * speed))
        self.update()
        super().wheelEvent(e)

    def _update_movement(self, dt: float):
        if not self._keys:
            return
        # hold Shift to move faster
        fast = (Qt.Key_Shift in self._keys)
        spd = self._move_speed * (2.25 if fast else 1.0)

        fwd, right, up = self._basis()
        move = (0.0, 0.0, 0.0)
        if Qt.Key_W in self._keys: move = _add(move, fwd)
        if Qt.Key_S in self._keys: move = _sub(move, fwd)
        if Qt.Key_D in self._keys: move = _add(move, right)
        if Qt.Key_A in self._keys: move = _sub(move, right)
        if Qt.Key_E in self._keys: move = _add(move, up)      # up
        if Qt.Key_Q in self._keys: move = _sub(move, up)      # down

        if move != (0.0,0.0,0.0):
            move = _normalize(move)
            self._cam_pos = _add(self._cam_pos, _mul(move, spd * dt))

    # ------------- camera math -------------
    def _basis(self):
        # forward from yaw/pitch (degrees)
        cp = math.radians(self._pitch)
        cy = math.radians(self._yaw)
        fwd = (math.cos(cp)*math.sin(cy), math.sin(cp), math.cos(cp)*math.cos(cy))
        fwd = _normalize(fwd)
        world_up = (0.0, 1.0, 0.0)
        right = _normalize(_cross(fwd, world_up))
        up = _normalize(_cross(right, fwd))
        return fwd, right, up

    # ------------- drawing -------------
    def _draw_grid(self, half=20, step=1.0):
        # axis colors + faint grid
        lr, lg, lb = (0.35, 0.35, 0.40)
        xr, xg, xb = (0.85, 0.25, 0.25)   # X red
        zr, zg, zb = (0.25, 0.70, 0.85)   # Z cyan-ish

        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(-half, half+1):
            if i == 0:
                glColor3f(xr,xg,xb)  # X axis
                glVertex3f(-half*step, 0.0, 0.0); glVertex3f(half*step, 0.0, 0.0)
                glColor3f(zr,zg,zb)  # Z axis
                glVertex3f(0.0, 0.0, -half*step); glVertex3f(0.0, 0.0, half*step)
            else:
                glColor3f(lr,lg,lb)
                # lines parallel to Z
                glVertex3f(i*step, 0.0, -half*step); glVertex3f(i*step, 0.0, half*step)
                # lines parallel to X
                glVertex3f(-half*step, 0.0, i*step); glVertex3f(half*step, 0.0, i*step)
        glEnd()

    def _draw_mesh(self):
        if not self._verts or not self._faces:
            return

        glColor3f(*self._line)

        # pick flat vs smooth (smooth if we computed normals)
        smooth = bool(self._vnorms) and (len(self._vnorms) == len(self._verts))
        glBegin(GL_TRIANGLES)
        if smooth:
            for a,b,c in self._faces:
                na = self._vnorms[a]; nb = self._vnorms[b]; nc = self._vnorms[c]
                ax,ay,az = self._verts[a]; bx,by,bz = self._verts[b]; cx,cy,cz = self._verts[c]
                glNormal3f(*na); glVertex3f(ax,ay,az)
                glNormal3f(*nb); glVertex3f(bx,by,bz)
                glNormal3f(*nc); glVertex3f(cx,cy,cz)
        else:
            # flat shading per face
            for a,b,c in self._faces:
                v0 = self._verts[a]; v1 = self._verts[b]; v2 = self._verts[c]
                n = _normalize(_cross(_sub(v1,v0), _sub(v2,v0)))
                glNormal3f(*n)
                glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v2)
        glEnd()

    # ------------- OBJ loading + fit -------------
    def _load_obj(self, path: str):
        verts = []; faces = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line or line.startswith("#"): continue
                parts = line.strip().split()
                if not parts: continue
                if parts[0] == "v" and len(parts) >= 4:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    verts.append((x, y, z))
                elif parts[0] == "f" and len(parts) >= 4:
                    idxs = []
                    for p in parts[1:]:
                        # forms: "v", "v/t", "v//n", "v/t/n"
                        v = p.split("/")[0]
                        if not v: continue
                        idx = int(v)
                        if idx < 0: idx = len(verts) + idx + 1
                        idxs.append(idx-1)  # OBJ -> 0-based
                    # triangulate fan
                    for i in range(1, len(idxs)-1):
                        faces.append((idxs[0], idxs[i], idxs[i+1]))

        self._verts = verts
        self._faces = faces
        self._compute_bounds()
        self._compute_vertex_normals()

    def _compute_bounds(self):
        if not self._verts:
            self._bbox = None
            self._center = (0.0, 0.0, 0.0)
            return
        xs = [v[0] for v in self._verts]
        ys = [v[1] for v in self._verts]
        zs = [v[2] for v in self._verts]
        self._bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        self._center = ((min(xs)+max(xs))/2.0, (min(ys)+max(ys))/2.0, (min(zs)+max(zs))/2.0)

    def _compute_vertex_normals(self):
        if not self._verts or not self._faces:
            self._vnorms = []
            return
        acc = [(0.0,0.0,0.0) for _ in self._verts]
        for a,b,c in self._faces:
            v0 = self._verts[a]; v1 = self._verts[b]; v2 = self._verts[c]
            n = _normalize(_cross(_sub(v1,v0), _sub(v2,v0)))
            acc[a] = _add(acc[a], n)
            acc[b] = _add(acc[b], n)
            acc[c] = _add(acc[c], n)
        self._vnorms = [_normalize(n) for n in acc]

    def _frame_to_fit(self):
        if not self._bbox:
            self._cam_pos = (0.0, 0.75, 3.5)
            self._yaw, self._pitch = 35.0, -20.0
            self._dist = 3.5
            return
        minx,miny,minz, maxx,maxy,maxz = self._bbox
        size = max(maxx-minx, maxy-miny, maxz-minz)
        size = max(size, 0.25)
        self._dist = 2.2 * size
        self._yaw, self._pitch = 35.0, -20.0
        # put camera back from center along -forward
        fwd, _, _ = self._basis()
        self._cam_pos = _sub(self._center, _mul(fwd, self._dist))
