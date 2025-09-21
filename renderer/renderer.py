# renderer/renderer.py — OBJ/cube viewer + Blender-style grid floor
from __future__ import annotations
import os, math
from typing import List, Tuple

from PySide6.QtCore import Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from OpenGL.GL import (
    glClearColor, glClear, glViewport, glEnable, glDisable, glLineWidth,
    glMatrixMode, glLoadIdentity, glTranslatef, glRotatef, glBegin, glEnd,
    glVertex3f, glColor3f, glColor4f, glPolygonMode, glBlendFunc,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_CULL_FACE,
    GL_PROJECTION, GL_MODELVIEW, GL_TRIANGLES, GL_FRONT_AND_BACK, GL_FILL,
    GL_LINE, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA
)
from OpenGL.GLU import gluPerspective
try:
    from OpenGL.GLUT import glutInit
except Exception:
    glutInit = None


def _hex_to_rgbf(h: str) -> Tuple[float, float, float]:
    h = h.lstrip("#"); return (int(h[0:2],16)/255.0, int(h[2:4],16)/255.0, int(h[4:6],16)/255.0)


class SimpleGLViewport(QOpenGLWidget):
    """
    Controls:
      A/D = orbit yaw, W/S = zoom, ↑/↓ = pitch, R = reset, G = toggle grid
    Loads OBJ (triangulates n-gons) or falls back to a unit cube.
    """

    def __init__(self, parent=None, bg_hex="#1b1b1f", line_hex="#E6E6EA", obj_path: str | None = "cube.obj"):
        super().__init__(parent)

        fmt = QSurfaceFormat(); fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(2,1); fmt.setProfile(QSurfaceFormat.NoProfile); fmt.setDepthBufferSize(24)
        self.setFormat(fmt)

        # theme
        self._bg = (*_hex_to_rgbf(bg_hex), 1.0)
        self._mesh_color = _hex_to_rgbf(line_hex)

        # camera
        self._yaw, self._pitch, self._dist, self._fov = 30.0, -20.0, 3.5, 60.0

        # controls
        self._keys = set()
        self._orbit_speed_deg, self._pitch_speed_deg, self._zoom_speed = 90.0, 60.0, 2.5

        # timing
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(16)
        self._elapsed = QElapsedTimer(); self._elapsed.start()

        # mesh
        self._tris: List[Tuple[Tuple[float,float,float], Tuple[float,float,float], Tuple[float,float,float]]] = []
        self._bbox = None
        self.model_label = "BUILT-IN"

        # grid settings (Y=0 plane)
        self._grid_enabled = True
        self._grid_spacing = 1.0       # world units between lines
        self._grid_half_lines = 60     # extends both +/-
        self._grid_major_every = 10    # thicker every N lines

        # try to load mesh
        if obj_path and os.path.exists(obj_path):
            self._load_obj(obj_path)
            if not self._tris:
                self._make_unit_cube()
            else:
                self._update_bounds(); self._frame_to_fit()
                self.model_label = os.path.basename(obj_path)
        else:
            self._make_unit_cube()

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(640, 400)

    # ---------- GL ----------
    def initializeGL(self):
        if glutInit is not None:
            try: glutInit()
            except Exception: pass
        glClearColor(*self._bg)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glLineWidth(1.4)

    def resizeGL(self, w:int, h:int):
        glViewport(0, 0, max(1,w), max(1,h))

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # projection
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        aspect = max(1e-3, self.width()/max(1.0, float(self.height())))
        gluPerspective(self._fov, aspect, 0.01, 1000.0)

        # view
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        glTranslatef(0.0, 0.0, -self._dist)
        glRotatef(-self._pitch, 1,0,0)
        glRotatef(-self._yaw,   0,1,0)

        # grid first (so mesh occludes it)
        if self._grid_enabled:
            self._draw_grid()

        # mesh solid
        r,g,b = self._mesh_color
        glColor3f(r,g,b)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glBegin(GL_TRIANGLES)
        for a,b,c in self._tris: glVertex3f(*a); glVertex3f(*b); glVertex3f(*c)
        glEnd()

        # wire overlay
        glDisable(GL_CULL_FACE)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE); glLineWidth(1.0)
        glBegin(GL_TRIANGLES)
        for a,b,c in self._tris: glVertex3f(*a); glVertex3f(*b); glVertex3f(*c)
        glEnd()
        glEnable(GL_CULL_FACE); glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    # ---------- Grid ----------
    def _draw_grid(self):
        # subtle gray lines with alpha fade; axes colored
        minor_rgba = (0.72, 0.74, 0.80, 0.12)
        major_rgba = (0.78, 0.80, 0.88, 0.25)
        x_axis     = (1.00, 0.25, 0.30, 0.90)   # X = red
        z_axis     = (0.25, 0.95, 0.35, 0.90)   # Z = green

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        size = self._grid_spacing * self._grid_half_lines

        # lines parallel to X (varying Z)
        glLineWidth(1.0)
        glBegin(GL_LINE)
        glEnd()  # (no-op; keeps PyOpenGL happy when switching widths)

        for i in range(-self._grid_half_lines, self._grid_half_lines + 1):
            z = i * self._grid_spacing
            # fade with distance from center
            t = 1.0 - min(1.0, abs(i) / float(self._grid_half_lines))
            fade = 0.18 + 0.55 * (t**1.5)  # non-linear for nicer falloff

            if i == 0:
                glLineWidth(1.8); glBegin(GL_LINES); glColor4f(*x_axis)  # X-axis line is along Z=0? (actually that's Z axis visually)
                glVertex3f(-size, 0.0, 0.0); glVertex3f(size, 0.0, 0.0); glEnd()
            else:
                rgba = major_rgba if (i % self._grid_major_every == 0) else minor_rgba
                glLineWidth(1.0 if rgba is minor_rgba else 1.4)
                r,g,b,a = rgba; glBegin(GL_LINES); glColor4f(r,g,b, a*fade)
                glVertex3f(-size, 0.0, z); glVertex3f(size, 0.0, z); glEnd()

        # lines parallel to Z (varying X)
        for i in range(-self._grid_half_lines, self._grid_half_lines + 1):
            x = i * self._grid_spacing
            t = 1.0 - min(1.0, abs(i) / float(self._grid_half_lines))
            fade = 0.18 + 0.55 * (t**1.5)

            if i == 0:
                glLineWidth(1.8); glBegin(GL_LINES); glColor4f(*z_axis)  # Z-axis
                glVertex3f(0.0, 0.0, -size); glVertex3f(0.0, 0.0, size); glEnd()
            else:
                rgba = major_rgba if (i % self._grid_major_every == 0) else minor_rgba
                glLineWidth(1.0 if rgba is minor_rgba else 1.4)
                r,g,b,a = rgba; glBegin(GL_LINES); glColor4f(r,g,b, a*fade)
                glVertex3f(x, 0.0, -size); glVertex3f(x, 0.0, size); glEnd()

        glDisable(GL_BLEND)

    # ---------- Update loop ----------
    def _tick(self):
        dt = max(0.0, self._elapsed.restart()/1000.0)
        self._apply_controls(dt)
        self.update()

    def _apply_controls(self, dt: float):
        if Qt.Key_A in self._keys: self._yaw = (self._yaw - self._orbit_speed_deg*dt) % 360.0
        if Qt.Key_D in self._keys: self._yaw = (self._yaw + self._orbit_speed_deg*dt) % 360.0
        if Qt.Key_W in self._keys: self._dist = max(0.25, self._dist - self._zoom_speed*dt)
        if Qt.Key_S in self._keys: self._dist = self._dist + self._zoom_speed*dt
        if Qt.Key_Up in self._keys:   self._pitch = max(-89.0, self._pitch - self._pitch_speed_deg*dt)
        if Qt.Key_Down in self._keys: self._pitch = min( 89.0, self._pitch + self._pitch_speed_deg*dt)

    # ---------- Input ----------
    def keyPressEvent(self, e):
        self._keys.add(e.key())
        if e.key() == Qt.Key_R:
            self._yaw, self._pitch, self._dist = 30.0, -20.0, 3.5
        elif e.key() == Qt.Key_G:
            self._grid_enabled = not self._grid_enabled

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat(): return
        self._keys.discard(e.key())

    # ---------- Mesh helpers ----------
    def _make_unit_cube(self):
        s=0.5
        v=[(-s,-s,-s),( s,-s,-s),( s, s,-s),(-s, s,-s),
           (-s,-s, s),( s,-s, s),( s, s, s),(-s, s, s)]
        idx=[(0,1,2),(0,2,3),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
             (2,3,7),(2,7,6),(1,2,6),(1,6,5),(0,3,7),(0,7,4)]
        self._tris=[(v[a],v[b],v[c]) for a,b,c in idx]
        self._update_bounds()

    def _load_obj(self, path:str):
        verts: List[Tuple[float,float,float]] = []
        faces: List[List[int]] = []
        with open(path,"r",encoding="utf-8") as f:
            for line in f:
                if not line or line.startswith("#"): continue
                parts = line.strip().split()
                if not parts: continue
                if parts[0]=="v" and len(parts)>=4:
                    verts.append((float(parts[1]),float(parts[2]),float(parts[3])))
                elif parts[0]=="f" and len(parts)>=4:
                    idxs=[]
                    for tok in parts[1:]:
                        base=tok.split("/")[0]
                        if not base: continue
                        i=int(base)
                        if i<0: i=len(verts)+i+1
                        idxs.append(i-1)
                    if len(idxs)>=3: faces.append(idxs)

        tris=[]
        for face in faces:
            if len(face)==3:
                a,b,c=face; tris.append((verts[a],verts[b],verts[c]))
            else:
                for i in range(1,len(face)-1):
                    tris.append((verts[face[0]],verts[face[i]],verts[face[i+1]]))
        self._tris=tris
        self._update_bounds()

    def _update_bounds(self):
        if not self._tris: self._bbox=None; return
        xs=[p[0] for tri in self._tris for p in tri]
        ys=[p[1] for tri in self._tris for p in tri]
        zs=[p[2] for tri in self._tris for p in tri]
        self._bbox=(min(xs),min(ys),min(zs),max(xs),max(ys),max(zs))

    def _frame_to_fit(self):
        if not self._bbox: return
        minx,miny,minz,maxx,maxy,maxz=self._bbox
        size=max(maxx-minx, maxy-miny, maxz-minz, 1e-6)
        radius=size*0.6
        fov_rad=math.radians(self._fov*0.5)
        self._dist=max(0.25, radius/max(1e-6, math.sin(fov_rad))*1.2)
        self._yaw,self._pitch=30.0,-20.0
