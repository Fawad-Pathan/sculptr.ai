# ai/generator.py
# Minimal "text -> mesh" generator: picks a primitive and writes mesh.obj
import os, time, math
from dataclasses import dataclass

@dataclass
class GenResult:
    ok: bool
    mesh_path: str | None
    meta: dict

class GeneratorEngine:
    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

    # --------- public API ----------
    def generate(self, prompt: str) -> GenResult:
        """Pick a primitive from the prompt and write an OBJ. Returns its path."""
        shape = self._decide_shape(prompt)
        verts, faces = self._make_shape(shape)
        job_dir = os.path.join(self.out_dir, f"job_{int(time.time())}")
        os.makedirs(job_dir, exist_ok=True)
        mesh_path = os.path.join(job_dir, "mesh.obj")
        self._write_obj(mesh_path, verts, faces)
        return GenResult(ok=True, mesh_path=mesh_path, meta={"shape": shape, "prompt": prompt})

    # --------- shape selection ----------
    def _decide_shape(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ("donut", "torus", "bagel", "ring")):       return "torus"
        if any(k in p for k in ("sphere", "ball", "planet", "head")):       return "sphere"
        if any(k in p for k in ("cone", "ice cream", "pyramid-ish")):       return "cone"
        if any(k in p for k in ("cylinder", "tube", "can")):                return "cylinder"
        return "cube"

    # --------- primitive builders (return triangles) ----------
    def _make_shape(self, name: str):
        if name == "sphere":   return self._uv_sphere(0.6, 32, 16)
        if name == "torus":    return self._torus(0.65, 0.22, 40, 24)
        if name == "cone":     return self._cone(0.6, 1.0, 40)
        if name == "cylinder": return self._cylinder(0.5, 1.0, 40)
        return self._cube(1.0)

    def _cube(self, size=1.0):
        s = size * 0.5
        v = [(-s,-s,-s),( s,-s,-s),( s, s,-s),(-s, s,-s),
             (-s,-s, s),( s,-s, s),( s, s, s),(-s, s, s)]
        f = [(0,1,2),(0,2,3),(4,5,6),(4,6,7),
             (0,1,5),(0,5,4),(2,3,7),(2,7,6),
             (1,2,6),(1,6,5),(0,3,7),(0,7,4)]
        return v, f

    def _uv_sphere(self, radius=0.5, seg=32, rings=16):
        verts = []; faces = []
        def idx(i,j): return i*seg + (j % seg)
        for i in range(rings+1):
            theta = math.pi * i / rings
            y = radius * math.cos(theta)
            r = radius * math.sin(theta)
            for j in range(seg):
                phi = 2*math.pi * j / seg
                x = r * math.cos(phi); z = r * math.sin(phi)
                verts.append((x, y, z))
        for i in range(rings):
            for j in range(seg):
                a = idx(i, j); b = idx(i+1, j); c = idx(i+1, j+1); d = idx(i, j+1)
                if i == 0:          faces.append((a, b, c))
                elif i == rings-1:  faces.append((a, b, d))
                else:               faces.append((a, b, c)); faces.append((a, c, d))
        return verts, faces

    def _cone(self, radius=0.5, height=1.0, seg=32):
        verts = []; faces = []
        for j in range(seg):
            phi = 2*math.pi*j/seg
            x = radius*math.cos(phi); z = radius*math.sin(phi)
            verts.append((x, -height/2, z))
        apex_i = len(verts);  verts.append((0.0,  height/2, 0.0))
        center_i = len(verts); verts.append((0.0, -height/2, 0.0))
        for j in range(seg):
            a = j; b = (j+1)%seg
            faces.append((a, b, apex_i))      # side
            faces.append((center_i, b, a))    # base
        return verts, faces

    def _cylinder(self, radius=0.5, height=1.0, seg=32):
        verts = []; faces = []
        top=[]; bot=[]
        for j in range(seg):
            phi = 2*math.pi*j/seg
            x = radius*math.cos(phi); z = radius*math.sin(phi)
            top.append(len(verts)); verts.append((x,  height/2, z))
            bot.append(len(verts)); verts.append((x, -height/2, z))
        top_c = len(verts); verts.append((0.0,  height/2, 0.0))
        bot_c = len(verts); verts.append((0.0, -height/2, 0.0))
        for j in range(seg):
            a = bot[j]; b = bot[(j+1)%seg]; c = top[(j+1)%seg]; d = top[j]
            faces.append((a, b, c)); faces.append((a, c, d))  # side
            faces.append((top_c, d, c))                        # top
            faces.append((bot_c, b, a))                        # bottom
        return verts, faces

    def _torus(self, R=0.6, r=0.25, seg=32, ring=16):
        verts = []; faces = []
        for i in range(ring):
            u = 2*math.pi*i/ring; cu, su = math.cos(u), math.sin(u)
            for j in range(seg):
                v = 2*math.pi*j/seg; cv, sv = math.cos(v), math.sin(v)
                x = (R + r*cv) * cu
                y =  r * sv
                z = (R + r*cv) * su
                verts.append((x, y, z))
        def idx(i,j): return (i%ring)*seg + (j%seg)
        for i in range(ring):
            for j in range(seg):
                a=idx(i,j); b=idx(i+1,j); c=idx(i+1,j+1); d=idx(i,j+1)
                faces.append((a,b,c)); faces.append((a,c,d))
        return verts, faces

    # --------- OBJ writer ----------
    def _write_obj(self, path: str, verts, faces):
        with open(path, "w", encoding="utf-8") as f:
            f.write("o generated\n")
            for x,y,z in verts:
                f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            for a,b,c in faces:
                f.write(f"f {a+1} {b+1} {c+1}\n")  # OBJ is 1-based

if __name__ == "__main__":
    eng = GeneratorEngine(out_dir=os.path.join(os.path.dirname(__file__), "..", "outputs"))
    print(eng.generate("donut"))
