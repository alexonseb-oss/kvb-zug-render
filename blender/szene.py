"""KVB-Zug Szene fuer den Employer-Branding-Pitch.

Blender-Skripte sind zwingend Python (bpy). Aufruf:
  Blender -b --factory-startup -P blender/szene.py -- --modus intro --stills 0,60,140 --prozent 50
  Blender -b --factory-startup -P blender/szene.py -- --modus intro            (alle Frames als PNG)
  Blender -b --factory-startup -P blender/szene.py -- --modus outro

Alle Farben, Texte und Kamerawerte stehen oben bzw. in ../titel.json.
"""
import bpy, bmesh, math, json, os, sys, random, argparse
from mathutils import Vector, Matrix, Quaternion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--modus", default="intro", choices=["intro", "outro"])
ap.add_argument("--stills", default="")
ap.add_argument("--prozent", type=int, default=100)
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--von", type=int, default=-1)
ap.add_argument("--bis", type=int, default=-1)
ap.add_argument("--blend", default="")
ap.add_argument("--fbx", default="")
ap.add_argument("--nur-blend", dest="nur_blend", action="store_true")
A = ap.parse_args(ARGV)

TITEL = json.load(open(os.path.join(ROOT, "titel.json"), encoding="utf-8"))

# ---------------------------------------------------------------- Konstanten
KVB_ROT = "#E10023"          # KVB-Rot wie im Team-Deck und im gelieferten Logo
WEISS = "#FFFFFF"
FPS = 30
INTRO_FRAMES = 150
OUTRO_FRAMES = 90
SENSOR = 36.0
LENS_NAH = 50.0
LOGO_Z = 1.18                # Hoehe Logo-Mitte an der Front
FRONT_X = 0.30               # Frontflaeche relativ zum Zug-Ursprung
FRAME_W = 1.689              # sichtbare Breite (m) im Logo-Frame
D_NAH = FRAME_W * LENS_NAH / SENSOR
LOGO_W_FRONT = 0.70          # 41 % der Bildbreite
BODY_W = 2.65
HALF = BODY_W / 2
FLOOR = 0.95
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_R = "/System/Library/Fonts/Supplemental/Arial.ttf"

CAM_FINAL = Vector((7.6, -9.0, 3.05))
CAM_FINAL_ZIEL = Vector((-0.25, -0.5, 2.78))
LENS_FINAL = 34.0
DFI_POS = Vector((4.4, -3.6, 3.3))
ZUG_STOP = -3.0
DOM_POS = (-384.0, 217.0)

random.seed(7)


def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def col(h, a=1.0):
    h = h.lstrip("#")
    return (lin(int(h[0:2], 16) / 255), lin(int(h[2:4], 16) / 255), lin(int(h[4:6], 16) / 255), a)


# ---------------------------------------------------------------- Szene leeren
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = A.prozent
scene.render.fps = FPS
scene.render.film_transparent = False
scene.render.dither_intensity = 0.0
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
ee = scene.eevee
ee.taa_render_samples = A.samples
for attr, val in (("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    try:
        setattr(ee, attr, val)
    except Exception:
        pass
try:
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
except Exception:
    ee.use_motion_blur = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"


# ---------------------------------------------------------------- Material
def socket(node, name, typ=None, out=False):
    socks = node.outputs if out else node.inputs
    for s in socks:
        if s.name == name and (typ is None or s.type == typ):
            return s
    raise KeyError(name)


FLAT_VALUES = []   # Value-Nodes, die zwischen "flach" (Emission) und "beleuchtet" blenden


def mat_basic(name, c, rough=0.45, metal=0.0, coat=0.0, emit=None, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = col(c) if isinstance(c, str) else c
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    if emit:
        p.inputs["Emission Color"].default_value = col(emit)
        p.inputs["Emission Strength"].default_value = strength
    return m


def mat_emit(name, c, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = col(c) if isinstance(c, str) else c
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def mat_flat_mix(name, color_socket_builder, rough=0.35, coat=0.6):
    """Principled + Emission gleicher Farbe, gemischt ueber einen animierbaren Wert.
    Wert 1 = exakt die Markenfarbe (Frame 0 = Folie 1), Wert 0 = normal beleuchtet."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = rough
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Coat Roughness"].default_value = 0.08
    e = nt.nodes.new("ShaderNodeEmission")
    csock = color_socket_builder(nt)
    nt.links.new(csock, p.inputs["Base Color"])
    nt.links.new(csock, e.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    v = nt.nodes.new("ShaderNodeValue")
    v.outputs[0].default_value = 0.0
    nt.links.new(v.outputs[0], mix.inputs[0])
    nt.links.new(p.outputs[0], mix.inputs[1])
    nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    FLAT_VALUES.append(v)
    return m


def builder_const(h):
    def b(nt):
        r = nt.nodes.new("ShaderNodeRGB")
        r.outputs[0].default_value = col(h)
        return r.outputs[0]
    return b


def builder_livery(nt):
    """Lackierung nach Hoehe: unten KVB-Rot, Fensterband anthrazit, Dach weiss."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 4.0
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], ramp.inputs[0])
    el = ramp.color_ramp.elements
    el[0].position = 0.0
    el[0].color = col(KVB_ROT)
    el[1].position = 1.79 / 4.0
    el[1].color = col("#1E1F22")
    e3 = el.new(3.06 / 4.0)
    e3.color = col("#F3F3F1")
    return ramp.outputs["Color"]


M = {}
M["lack"] = mat_flat_mix("Lack", builder_livery)
M["logo"] = mat_emit("LogoWeiss", WEISS, 1.0)
M["tuer"] = mat_basic("TuerRot", KVB_ROT, rough=0.35, coat=0.6)
M["innen"] = mat_basic("Innenwand", "#D9D7D2", rough=0.6)
M["boden"] = mat_basic("Boden", "#3A3B3F", rough=0.7)
M["decke"] = mat_basic("Decke", "#E8E6E1", rough=0.5)
M["licht"] = mat_emit("Lichtband", "#FFF1DD", 6.0)
M["stange"] = mat_basic("Haltestange", "#F1C400", rough=0.3, metal=0.2)
M["gummi"] = mat_basic("Gummi", "#16171A", rough=0.8)
M["fahrwerk"] = mat_basic("Fahrwerk", "#202124", rough=0.6, metal=0.4)
M["scheinwerfer"] = mat_emit("Scheinwerfer", "#FFF8EE", 25.0)
M["drl"] = mat_emit("Tagfahrlicht", "#FFFFFF", 12.0)
M["ruecklicht"] = mat_emit("Ruecklicht", "#FF1A1A", 8.0)
M["led_ziel"] = mat_emit("ZielLED", "#FFB21A", 5.0)
M["ziel_bg"] = mat_basic("ZielSchwarz", "#050505", rough=0.2)
M["frontglas"] = mat_basic("Frontscheibe", "#07080B", rough=0.04, coat=1.0)


def mat_glas():
    m = bpy.data.materials.new("Glas")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    out = nt.nodes["Material Output"]
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs[0].default_value = col("#E8F0EE")
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.02
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.5
    mr = nt.nodes.new("ShaderNodeMath")
    mr.operation = "MULTIPLY_ADD"
    mr.inputs[1].default_value = 0.45
    mr.inputs[2].default_value = 0.04
    nt.links.new(fr.outputs[0], mr.inputs[0])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mr.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        pass
    return m


M["glas"] = mat_glas()


def mat_random(name, palette, seed_mul, rough=0.7, emit=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = rough
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    mm = nt.nodes.new("ShaderNodeMath")
    mm.operation = "MULTIPLY"
    mm.inputs[1].default_value = seed_mul
    fr = nt.nodes.new("ShaderNodeMath")
    fr.operation = "FRACT"
    nt.links.new(oi.outputs["Random"], mm.inputs[0])
    nt.links.new(mm.outputs[0], fr.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    el = ramp.color_ramp.elements
    n = len(palette)
    el[0].position = 0.0
    el[0].color = col(palette[0])
    el[1].position = 1.0 / n
    el[1].color = col(palette[1])
    for i in range(2, n):
        e = el.new(i / n)
        e.color = col(palette[i])
    nt.links.new(fr.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], p.inputs["Base Color"])
    return m


M["oberteil"] = mat_random("Oberteil", ["#1F2A44", "#2B2B2B", "#6E6E6E", "#B9A88A", "#4B5A3A", "#6B1E2A",
                                         "#3D5A80", "#E9E4DA", "#C89B2C", "#8A3B12", "#24453F", "#9AA3AD"], 1.0)
M["hose"] = mat_random("Hose", ["#1C2333", "#2A2A2A", "#33415C", "#5A5248", "#121212"], 7.31)
M["haut"] = mat_random("Haut", ["#F1C7A8", "#E0AC86", "#C68B62", "#8D5A3B", "#5C3A26", "#F4D2BB"], 3.77, rough=0.55)
M["haare"] = mat_random("Haare", ["#1A120D", "#3B2414", "#6B4423", "#C9A15A", "#8C8C8C", "#0E0E0E"], 5.13, rough=0.6)
M["display"] = mat_emit("Handydisplay", "#BFD9FF", 3.0)


# ---------------------------------------------------------------- Geometrie-Helfer
def obj_from_bm(name, bm, mats, parent=None, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    if parent:
        o.parent = parent
    return o


def faces_of(verts):
    return {f for v in verts for f in v.link_faces}


def bm_box(bm, x0, x1, y0, y1, z0, z1, mi=0):
    r = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
                              @ Matrix.Diagonal((x1 - x0, y1 - y0, z1 - z0, 1)))
    for f in faces_of(r["verts"]):
        f.material_index = mi
    return r["verts"]


def bm_cyl(bm, p0, p1, r0, r1=None, seg=12, mi=0):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    mtx = Matrix.Translation((p0 + p1) / 2) @ rot
    r = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r0,
                              radius2=r1 if r1 is not None else r0, depth=d.length, matrix=mtx)
    for f in faces_of(r["verts"]):
        f.material_index = mi
    return r["verts"]


def bm_sphere(bm, c, r, sc=(1, 1, 1), mi=0, u=14, v=9):
    mtx = Matrix.Translation(c) @ Matrix.Diagonal((sc[0], sc[1], sc[2], 1))
    rr = bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r, matrix=mtx)
    for f in faces_of(rr["verts"]):
        f.material_index = mi
    return rr["verts"]


def bake_modifiers(o):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = o.data
    o.modifiers.clear()
    o.data = me
    bpy.data.meshes.remove(old)


def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    scene.collection.objects.link(e)
    if parent:
        e.parent = parent
    return e


def axes_matrix(xax, yax, zax, loc):
    m = Matrix((xax, yax, zax)).transposed().to_4x4()
    m.translation = loc
    return m


# ---------------------------------------------------------------- Logo (Vektor)
def logo_mesh():
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=os.path.join(ROOT, "assets", "kvb-logo-weiss.svg"))
    curves = [o for o in bpy.data.objects if o not in before]
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for o in curves:
        o.data.resolution_u = 24
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for o in curves:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    for o in curves:
        bpy.data.objects.remove(o)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w = max(xs) - min(xs)
    for v in bm.verts:
        v.co = Vector(((v.co.x - cx) / w, (v.co.y - cy) / w, 0))
    me = bpy.data.meshes.new("KVB_Logo")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(M["logo"])
    return me


LOGO_ME = logo_mesh()


def place_logo(name, width, matrix, parent):
    o = bpy.data.objects.new(name, LOGO_ME)
    scene.collection.objects.link(o)
    o.parent = parent
    o.matrix_parent_inverse = Matrix()
    o.matrix_basis = matrix @ Matrix.Diagonal((width, width, width, 1))
    return o


# ---------------------------------------------------------------- Zug
ZUG = empty("Zug")
L_END = -29.0
DOORS = [-3.4, -9.6, -19.4, -25.6]
DOOR_W = 1.3
JOINT = -14.5


def body():
    front = [(0.0, 0.35), (FRONT_X, 0.62), (FRONT_X, 1.76), (-0.55, 3.15), (-1.0, 3.55)]
    rear = [(L_END - x, z) for (x, z) in front]
    prof = [rear[0]] + front + list(reversed(rear))[:-1]
    prof = [rear[0], front[0], front[1], front[2], front[3], front[4], rear[4], rear[3], rear[2], rear[1]]
    bm = bmesh.new()
    vs = [bm.verts.new((x, -HALF, z)) for x, z in prof]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.y += BODY_W
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = obj_from_bm("Wagenkasten", bm, [M["lack"], M["innen"]], ZUG, smooth=True)
    bv = o.modifiers.new("bevel", "BEVEL")
    bv.width = 0.2
    bv.segments = 6
    bv.limit_method = "ANGLE"
    bv.angle_limit = math.radians(25)
    bv.harden_normals = True
    so = o.modifiers.new("solid", "SOLIDIFY")
    so.thickness = 0.05
    so.offset = -1
    so.material_offset = 1
    so.use_even_offset = True
    # Ausschnitte
    cb = bmesh.new()
    for x in DOORS:
        bm_box(cb, x - DOOR_W / 2, x + DOOR_W / 2, -HALF - 0.5, HALF + 0.5, FLOOR + 0.03, 3.08)
    for (a, b) in WINDOW_SPANS:
        for (p, q) in panes(a, b):
            bm_box(cb, p, q, -HALF - 0.5, HALF + 0.5, 1.84, 2.98)
    cutter = obj_from_bm("Ausschnitte", cb, [])
    cutter.hide_render = True
    bo = o.modifiers.new("cut", "BOOLEAN")
    bo.operation = "DIFFERENCE"
    bo.object = cutter
    try:
        bo.solver = "EXACT"
    except Exception:
        pass
    bake_modifiers(o)
    bpy.data.objects.remove(cutter)
    return o


def panes(a, b, target=1.15, pillar=0.12):
    n = max(1, round((b - a) / target))
    w = (b - a - (n - 1) * pillar) / n
    return [(a + i * (w + pillar), a + i * (w + pillar) + w) for i in range(n)]


WINDOW_SPANS = [(-2.45, -1.35), (-8.75, -4.25), (-14.1, -10.45), (-18.55, -14.9), (-24.75, -20.25), (-27.65, -26.45)]

body()

# Glas in den Fensteroeffnungen
bmg = bmesh.new()
for (a, b) in WINDOW_SPANS:
    for (p, q) in panes(a, b):
        for s in (-1, 1):
            y = s * (HALF - 0.025)
            bm_box(bmg, p, q, y - 0.004, y + 0.004, 1.84, 2.98)
obj_from_bm("Seitenfenster", bmg, [M["glas"]], ZUG)

# Tueren: rote Fluegel mit grossen Scheiben, beidseitig
bmt = bmesh.new()
bmtg = bmesh.new()
for x in DOORS:
    for s in (-1, 1):
        y = s * (HALF - 0.04)
        for leaf in (0, 1):
            x0 = x - DOOR_W / 2 + leaf * DOOR_W / 2 + 0.01
            x1 = x0 + DOOR_W / 2 - 0.02
            bm_box(bmt, x0, x1, y - 0.02, y + 0.02, FLOOR + 0.03, FLOOR + 0.24)
            bm_box(bmt, x0, x1, y - 0.02, y + 0.02, 2.90, 3.08)
            bm_box(bmt, x0, x0 + 0.07, y - 0.02, y + 0.02, FLOOR + 0.24, 2.90)
            bm_box(bmt, x1 - 0.07, x1, y - 0.02, y + 0.02, FLOOR + 0.24, 2.90)
            bm_box(bmtg, x0 + 0.07, x1 - 0.07, y - 0.004, y + 0.004, FLOOR + 0.24, 2.90)
obj_from_bm("Tueren", bmt, [M["tuer"]], ZUG)
obj_from_bm("Tuerglas", bmtg, [M["glas"]], ZUG)

# Faltenbalg am Gelenk
bmj = bmesh.new()
bm_box(bmj, JOINT - 0.12, JOINT + 0.12, -HALF - 0.012, HALF + 0.012, 0.45, 3.5)
obj_from_bm("Gelenk", bmj, [M["gummi"]], ZUG)

# Innenraum
bmi = bmesh.new()
bm_box(bmi, -28.4, -1.95, -HALF + 0.06, HALF - 0.06, FLOOR - 0.1, FLOOR, 0)
bm_box(bmi, -28.4, -1.95, -HALF + 0.06, HALF - 0.06, 3.28, 3.32, 1)
bm_box(bmi, -2.0, -1.95, -HALF + 0.06, HALF - 0.06, FLOOR, 3.3, 1)          # Fuehrerstandswand
bm_box(bmi, -28.4, -28.35, -HALF + 0.06, HALF - 0.06, FLOOR, 3.3, 1)
for s in (-1, 1):
    bm_box(bmi, -28.3, -2.05, s * 0.62 - 0.07, s * 0.62 + 0.07, 3.255, 3.28, 2)
obj_from_bm("Innenraum", bmi, [M["boden"], M["decke"], M["licht"]], ZUG)

bms = bmesh.new()
for s in (-1, 1):
    bm_cyl(bms, (-28.2, s * 0.72, FLOOR + 1.9), (-2.1, s * 0.72, FLOOR + 1.9), 0.018, seg=8)
    x = -27.4
    while x < -2.5:
        if all(abs(x - d) > 0.8 for d in DOORS):
            bm_cyl(bms, (x, s * 0.72, FLOOR), (x, s * 0.72, 3.28), 0.02, seg=8)
        x += 2.3
obj_from_bm("Haltestangen", bms, [M["stange"]], ZUG, smooth=True)

# Fahrwerk
bmf = bmesh.new()
for x in (-2.6, -12.5, -16.5, -26.4):
    bm_box(bmf, x - 1.2, x + 1.2, -1.0, 1.0, 0.05, 0.45)
    for dx in (-0.9, 0.9):
        for s in (-1, 1):
            bm_cyl(bmf, (x + dx, s * 0.72 - 0.05, 0.36), (x + dx, s * 0.72 + 0.05, 0.36), 0.33, seg=18)
obj_from_bm("Fahrwerk", bmf, [M["fahrwerk"]], ZUG)

# Front: Scheibe, Lichter, Zielanzeige
slant_a, slant_b = Vector((FRONT_X - 0.1, 0, 1.86)), Vector((-0.5, 0, 3.07))
up = (slant_b - slant_a).normalized()
nrm = Vector((-up.z, 0, -up.x)) * -1
nrm = Vector((up.z, 0, -up.x))
if nrm.x < 0:
    nrm = -nrm
bmw = bmesh.new()
mid = (slant_a + slant_b) / 2 + nrm * 0.03
length = (slant_b - slant_a).length
mtx = axes_matrix(Vector((0, 1, 0)), up, nrm, mid) @ Matrix.Diagonal((2.25, length, 0.01, 1))
r = bmesh.ops.create_cube(bmw, size=1.0, matrix=mtx)
obj_from_bm("Frontscheibe", bmw, [M["frontglas"]], ZUG)

bmh = bmesh.new()
for s in (-1, 1):
    bm_cyl(bmh, (FRONT_X - 0.01, s * 1.0, 0.82), (FRONT_X + 0.02, s * 1.0, 0.82), 0.075, seg=20)
obj_from_bm("Scheinwerfer", bmh, [M["scheinwerfer"]], ZUG)
bmd = bmesh.new()
for s in (-1, 1):
    bm_box(bmd, FRONT_X - 0.01, FRONT_X + 0.015, s * 1.0 - 0.18 if s < 0 else s * 1.0 - 0.02,
           s * 1.0 + 0.02 if s < 0 else s * 1.0 + 0.18, 0.66, 0.69)
obj_from_bm("Tagfahrlicht", bmd, [M["drl"]], ZUG)
bmr = bmesh.new()
for s in (-1, 1):
    bm_cyl(bmr, (L_END - FRONT_X + 0.01, s * 1.0, 0.82), (L_END - FRONT_X - 0.02, s * 1.0, 0.82), 0.07, seg=16)
obj_from_bm("Ruecklicht", bmr, [M["ruecklicht"]], ZUG)

for s in (-1, 1):
    ld = bpy.data.lights.new(f"Frontlicht{s}", "SPOT")
    ld.energy = 900
    ld.spot_size = math.radians(55)
    ld.spot_blend = 0.6
    ld.color = (1.0, 0.96, 0.9)
    lo = bpy.data.objects.new(ld.name, ld)
    scene.collection.objects.link(lo)
    lo.parent = ZUG
    lo.location = (FRONT_X + 0.1, s * 1.0, 0.82)
    lo.rotation_euler = (0, math.radians(-90 + 8), 0)

# Zielanzeige oben auf der Schraege
za, zb = Vector((-0.58, 0, 3.18)), Vector((-0.97, 0, 3.53))
zup = (zb - za).normalized()
zn = Vector((zup.z, 0, -zup.x))
if zn.x < 0:
    zn = -zn
zmid = (za + zb) / 2 + zn * 0.015
bmz = bmesh.new()
bmesh.ops.create_cube(bmz, size=1.0, matrix=axes_matrix(Vector((0, 1, 0)), zup, zn, zmid)
                      @ Matrix.Diagonal((1.9, (zb - za).length * 0.82, 0.01, 1)))
obj_from_bm("Zielanzeige", bmz, [M["ziel_bg"]], ZUG)


def text_obj(name, body, size, mat, font=FONT_B, align="LEFT", maxw=None, parent=None, matrix=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.resolution_u = 6
    o = bpy.data.objects.new(name, cu)
    scene.collection.objects.link(o)
    o.data.materials.append(mat)
    if parent:
        o.parent = parent
    if matrix is not None:
        o.matrix_basis = matrix
    bpy.context.view_layer.update()
    if maxw:
        dims = o.dimensions.x / max(o.scale.x, 1e-6)
        if dims > maxw:
            o.scale.x *= maxw / dims
    return o


ztxt = f"{TITEL['zugziel_linie']}   {TITEL['zugziel_text']}"
text_obj("Zieltext", ztxt, 0.16, M["led_ziel"], parent=ZUG, align="CENTER", maxw=1.75,
         matrix=axes_matrix(Vector((0, 1, 0)), zup, zn, zmid + zn * 0.012))

# Logos: Front (Frame-0-Logo) + Seiten
place_logo("Logo_Front", LOGO_W_FRONT,
           axes_matrix(Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((FRONT_X + 0.003, 0, LOGO_Z))),
           ZUG)
for x in (-6.5, -22.5):
    place_logo(f"Logo_Seite{x}", 0.62,
               axes_matrix(Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0)), Vector((x, -HALF - 0.004, 1.33))),
               ZUG)

# Innenlicht
for x in (-24, -18, -11, -5):
    la = bpy.data.lights.new(f"Innen{x}", "AREA")
    la.energy = 650
    la.shape = "RECTANGLE"
    la.size = 3.5
    la.size_y = 1.2
    la.color = (1.0, 0.9, 0.78)
    lo = bpy.data.objects.new(la.name, la)
    scene.collection.objects.link(lo)
    lo.parent = ZUG
    lo.location = (x, 0, 3.2)


# ---------------------------------------------------------------- Fahrgaeste
def person_variant(kind):
    bm = bmesh.new()
    # 0 Oberteil, 1 Hose, 2 Haut, 3 Haare, 4 Display
    for sx in (-0.09, 0.09):
        bm_cyl(bm, (sx, 0, 0.0), (sx, 0, 0.88), 0.075, 0.085, seg=10, mi=1)
    bm_cyl(bm, (0, 0, 0.82), (0, 0, 1.44), 0.17, 0.2, seg=14, mi=0)
    bm_sphere(bm, (0, 0, 1.43), 0.21, (1, 0.62, 0.42), mi=0)
    bm_cyl(bm, (0, 0, 1.48), (0, 0, 1.6), 0.055, seg=10, mi=2)
    bm_sphere(bm, (0, 0, 1.68), 0.105, (0.9, 1.0, 1.15), mi=2)
    hair_drop = 0.0 if kind % 2 == 0 else 0.05
    bm_sphere(bm, (0, -0.012, 1.715 - hair_drop * 0.3), 0.112, (0.93, 1.03, 0.95 + hair_drop), mi=3)
    # Arme
    sides = [(-1, "down"), (1, "down")]
    if kind in (1, 4):
        sides = [(-1, "down"), (1, "up")]
    if kind in (2, 5):
        sides = [(-1, "phone"), (1, "phone")]
    if kind == 3:
        sides = [(-1, "up"), (1, "down")]
    for s, mode in sides:
        sh = Vector((s * 0.22, 0, 1.43))
        if mode == "down":
            hand = Vector((s * 0.27, 0.02, 0.86))
        elif mode == "up":
            hand = Vector((s * 0.2, 0.0, 1.98))
        else:
            hand = Vector((s * 0.06, -0.3, 1.18))
        elbow = (sh + hand) / 2 + Vector((s * 0.05, 0.05 if mode == "phone" else 0, 0))
        bm_cyl(bm, sh, elbow, 0.055, 0.05, seg=8, mi=0)
        bm_cyl(bm, elbow, hand, 0.05, 0.045, seg=8, mi=0)
        bm_sphere(bm, hand, 0.045, mi=2, u=8, v=6)
    if kind in (2, 5):
        bm_box(bm, -0.04, 0.04, -0.34, -0.33, 1.15, 1.29, mi=4)
    if kind == 4:
        bm_box(bm, -0.16, 0.16, 0.13, 0.3, 0.95, 1.4, mi=1)   # Rucksack
    me = bpy.data.meshes.new(f"Person{kind}")
    bm.to_mesh(me)
    bm.free()
    for m in (M["oberteil"], M["hose"], M["haut"], M["haare"], M["display"]):
        me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    return me


VARIANTS = [person_variant(k) for k in range(6)]
LEUTE = empty("Fahrgaeste", parent=ZUG)
count = 0
lanes = [-1.02, -0.52, -0.02, 0.48, 0.98]


def add_person(x, y, rot, scale):
    global count
    o = bpy.data.objects.new(f"P{count}", random.choice(VARIANTS))
    scene.collection.objects.link(o)
    o.parent = LEUTE
    o.location = (x, y, FLOOR)
    o.rotation_euler = (0, 0, rot)
    o.scale = (scale, scale, scale)
    count += 1


x = -27.9
while x < -2.4:
    if abs(x - JOINT) > 0.25:
        for ly in lanes:
            if random.random() < 0.93:
                yy = ly + random.uniform(-0.07, 0.07)
                if ly < -0.9:
                    rot = random.choice([0, 0, math.pi / 2, -math.pi / 2]) + random.uniform(-0.5, 0.5)
                else:
                    rot = random.uniform(0, 2 * math.pi)
                add_person(x + random.uniform(-0.08, 0.08), yy, rot, random.uniform(0.92, 1.08))
    x += random.uniform(0.4, 0.48)
# Gesichter direkt an den Tuerscheiben
for d in DOORS:
    for dx in (-0.33, 0.0, 0.33):
        add_person(d + dx + random.uniform(-0.05, 0.05), -HALF + 0.27, random.uniform(-0.4, 0.4), random.uniform(0.95, 1.07))
print("Fahrgaeste:", count)

# ---------------------------------------------------------------- Haltestelle
M["beton"] = None


def mat_nass():
    m = bpy.data.materials.new("BetonNass")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.35
    nz.inputs["Detail"].default_value = 6
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.color_ramp.elements[0].position = 0.58
    rp.color_ramp.elements[0].color = (0.07, 0.07, 0.07, 1)
    rp.color_ramp.elements[1].position = 0.61
    rp.color_ramp.elements[1].color = (0.6, 0.6, 0.6, 1)
    nt.links.new(nz.outputs["Fac"], rp.inputs[0])
    nt.links.new(rp.outputs[0], p.inputs["Roughness"])
    p.inputs["Base Color"].default_value = col("#55565A")
    return m


M["beton"] = mat_nass()
M["kante"] = mat_basic("Kante", "#B9B9B2", rough=0.6)
M["schotter"] = mat_basic("Gleisbett", "#232220", rough=0.9)
M["schiene"] = mat_basic("Schiene", "#9EA2A8", rough=0.25, metal=1.0)
M["mast"] = mat_basic("Mast", "#5D6266", rough=0.5, metal=0.6)
M["lampe"] = mat_emit("Lampe", "#FFD9A6", 20.0)
M["dach"] = mat_basic("Wartehalle", "#3B3E42", rough=0.5, metal=0.3)
M["stadt"] = mat_basic("Stadt", "#141821", rough=0.9)
M["fenster_stadt"] = mat_emit("Stadtfenster", "#FFC478", 2.0)
M["dom"] = mat_basic("Dom", "#1A2033", rough=0.9)

bm = bmesh.new()
bm_box(bm, -75, 46, -9, -1.55, 0, 0.9, 0)
bm_box(bm, -75, 46, -1.78, -1.66, 0.9, 0.902, 1)
obj_from_bm("Bahnsteig", bm, [M["beton"], M["kante"]])
bm = bmesh.new()
bm_box(bm, -300, 300, -1.55, 60, -0.05, 0.0, 0)
bm_box(bm, -300, 300, -60, -9, -0.05, 0.0, 0)
obj_from_bm("Boden", bm, [M["schotter"]])
bm = bmesh.new()
for s in (-1, 1):
    bm_box(bm, -300, 300, s * 0.7175 - 0.035, s * 0.7175 + 0.035, 0.0, 0.15)
obj_from_bm("Schienen", bm, [M["schiene"]])

bm = bmesh.new()
bm_cyl(bm, (-300, 0, 5.6), (300, 0, 5.6), 0.012, seg=6)
for x in range(-120, 121, 32):
    bm_cyl(bm, (x, 2.6, 0), (x, 2.6, 6.4), 0.11, 0.09, seg=10)
    bm_cyl(bm, (x, 2.6, 6.0), (x, 0, 5.7), 0.03, seg=6)
obj_from_bm("Oberleitung", bm, [M["mast"]], smooth=True)

for x in (-26, -12, 16, 30):
    bm = bmesh.new()
    bm_cyl(bm, (x, -6.3, 0.9), (x, -6.3, 5.2), 0.06, seg=10, mi=0)
    bm_cyl(bm, (x, -6.3, 5.2), (x, -5.4, 5.25), 0.04, seg=8, mi=0)
    bm_box(bm, x - 0.25, x + 0.25, -5.6, -5.2, 5.12, 5.18, 1)
    obj_from_bm(f"Laterne{x}", bm, [M["mast"], M["lampe"]], smooth=False)
    lp = bpy.data.lights.new(f"Laternenlicht{x}", "POINT")
    lp.energy = 450
    lp.color = (1.0, 0.8, 0.58)
    lp.shadow_soft_size = 0.3
    lo = bpy.data.objects.new(lp.name, lp)
    scene.collection.objects.link(lo)
    lo.location = (x, -5.4, 5.0)

# Wartehalle
bm = bmesh.new()
for x in (-9.5, -3.5):
    for y in (-8.2, -6.6):
        bm_box(bm, x - 0.05, x + 0.05, y - 0.05, y + 0.05, 0.9, 3.4)
bm_box(bm, -10, -3, -8.5, -6.2, 3.4, 3.52)
obj_from_bm("Wartehalle", bm, [M["dach"]])
bm = bmesh.new()
bm_box(bm, -9.45, -3.55, -8.22, -8.18, 1.0, 3.3)
obj_from_bm("Wartehallenglas", bm, [M["glas"]])

# Stadt-Silhouette und Dom
dom_ang = math.atan2(DOM_POS[1], DOM_POS[0])
i = 0
while i < 30:
    x = random.uniform(-300, 140)
    y = random.choice([random.uniform(70, 150), random.uniform(-200, -120)])
    if abs(math.atan2(y, x) - dom_ang) < math.radians(11) or abs(math.atan2(y - CAM_FINAL.y, x - CAM_FINAL.x) - math.atan2(DOM_POS[1] - CAM_FINAL.y, DOM_POS[0] - CAM_FINAL.x)) < math.radians(9):
        continue
    i += 1
    w, d, h = random.uniform(12, 30), random.uniform(10, 20), random.uniform(10, 24)
    bm = bmesh.new()
    bm_box(bm, x - w / 2, x + w / 2, y - d / 2, y + d / 2, 0, h, 0)
    for k in range(int(w * h / 22)):
        fx = random.uniform(x - w / 2 + 1, x + w / 2 - 1)
        fz = random.uniform(2, h - 2)
        fy = y - d / 2 - 0.05 if y > 0 else y + d / 2 + 0.05
        if random.random() < 0.45:
            bm_box(bm, fx - 0.4, fx + 0.4, fy - 0.03, fy + 0.03, fz - 0.55, fz + 0.55, 1)
    obj_from_bm(f"Haus{i}", bm, [M["stadt"], M["fenster_stadt"]])


def dom(cx, cy, s=1.0):
    bm = bmesh.new()
    for dy in (-11, 11):
        ty = cy + dy * s
        bm_box(bm, cx - 9 * s, cx + 9 * s, ty - 7 * s, ty + 7 * s, 0, 98 * s)
        bm_box(bm, cx - 7 * s, cx + 7 * s, ty - 5.5 * s, ty + 5.5 * s, 98 * s, 112 * s)
        bm_cyl(bm, (cx, ty, 112 * s), (cx, ty, 157 * s), 6.2 * s, 0.4 * s, seg=8)
        for ox in (-8.5, 8.5):
            for oy in (-6.5, 6.5):
                bm_cyl(bm, (cx + ox * s, ty + oy * s, 0), (cx + ox * s, ty + oy * s, 108 * s), 1.2 * s, 0.4 * s, seg=6)
    bm_box(bm, cx - 120 * s, cx - 9 * s, cy - 15 * s, cy + 15 * s, 0, 44 * s)
    bm_cyl(bm, (cx - 120 * s, cy, 44 * s), (cx - 9 * s, cy, 44 * s), 15 * s, 2 * s, seg=4)
    bm_box(bm, cx - 70 * s, cx - 50 * s, cy - 45 * s, cy + 45 * s, 0, 44 * s)
    bm_cyl(bm, (cx - 60 * s, cy, 44 * s), (cx - 60 * s, cy, 75 * s), 3 * s, 0.2 * s, seg=8)
    obj_from_bm("Koelner_Dom", bm, [M["dom"]])


dom(DOM_POS[0], DOM_POS[1], 0.85)

# ---------------------------------------------------------------- DFI-Anzeige (gross, mit Gliederung)
DFI = empty("DFI", DFI_POS)
vcam = CAM_FINAL - DFI_POS
DFI.rotation_euler = (0, 0, math.atan2(vcam.x, -vcam.y))
M["gehaeuse"] = mat_basic("DFI_Gehaeuse", "#C9CCD0", rough=0.35, metal=0.7)
M["dfi_schwarz"] = mat_basic("DFI_Rahmen", "#0B0C10", rough=0.3)
SCR_W, SCR_H = 2.5, 1.72
HW, HH = SCR_W / 2 + 0.1, SCR_H / 2 + 0.08
TOP = HH + 0.95
bm = bmesh.new()
bm_box(bm, -HW, HW, -0.07, 0.1, -HH, HH, 0)
bm_box(bm, -HW - 0.06, HW + 0.06, -0.13, 0.13, HH, HH + 0.07, 0)                 # Dach
bm_cyl(bm, (0.0, 0.25, HH + 0.07), (0.0, 0.25, TOP), 0.05, seg=10, mi=0)
bm_box(bm, -SCR_W / 2 - 0.02, SCR_W / 2 + 0.02, -0.075, -0.07, -SCR_H / 2 - 0.02, SCR_H / 2 + 0.02, 1)
obj_from_bm("DFI_Gehaeuse", bm, [M["gehaeuse"], M["dfi_schwarz"]], DFI)
bm = bmesh.new()
bm_cyl(bm, (0, 0.25, TOP), (0, 1.2, TOP), 0.06, seg=10)
bm_cyl(bm, (0, 1.2, -(DFI_POS.z - 0.9)), (0, 1.2, TOP + 0.07), 0.09, seg=12)
obj_from_bm("DFI_Mast", bm, [M["mast"]], DFI)

N_Z = len(TITEL["zeilen"])
U = SCR_H / (1.45 + N_Z + 1.05)
KOPF = 1.45 * U
M["dfi_kopf"] = mat_emit("DFI_Kopf", "#1B1A57", 1.0)
M["dfi_hell"] = mat_emit("DFI_Hell", "#4650B2", 1.0)
M["dfi_dunkel"] = mat_emit("DFI_Dunkel", "#25236B", 1.0)
M["dfi_text"] = mat_emit("DFI_Text", "#FFFFFF", 1.15)
bm = bmesh.new()
top = SCR_H / 2
bm_box(bm, -SCR_W / 2, SCR_W / 2, -0.09, -0.08, top - KOPF, top, 0)
for i in range(N_Z):
    z1 = top - KOPF - i * U
    bm_box(bm, -SCR_W / 2, SCR_W / 2, -0.09, -0.08, z1 - U, z1, 1 if i % 2 == 0 else 2)
bm_box(bm, -SCR_W / 2, SCR_W / 2, -0.09, -0.08, -SCR_H / 2, -SCR_H / 2 + 1.05 * U, 0)
obj_from_bm("DFI_Zeilen", bm, [M["dfi_kopf"], M["dfi_hell"], M["dfi_dunkel"]], DFI)

TXT_ROT = Matrix.Rotation(math.radians(90), 4, "X")


def dfi_text(name, body, x, z, size, align="LEFT", maxw=None, font=FONT_B):
    mtx = Matrix.Translation((x, -0.092, z)) @ TXT_ROT
    return text_obj(name, body, size, M["dfi_text"], font=font, align=align, maxw=maxw, parent=DFI, matrix=mtx)


L0 = -SCR_W / 2 + 0.07
R0 = SCR_W / 2 - 0.07
zc = top - KOPF / 2
dfi_text("K_l", TITEL["kopf_links"], L0, zc, KOPF * 0.62, maxw=SCR_W * 0.72)
dfi_text("K_r", TITEL["kopf_rechts"], R0, zc, KOPF * 0.45, align="RIGHT")
for i, (lin_, ziel, zeit) in enumerate(TITEL["zeilen"]):
    zc = top - KOPF - i * U - U / 2
    dfi_text(f"Z{i}_l", lin_, L0 + 0.04, zc, U * 0.66, maxw=0.25)
    dfi_text(f"Z{i}_z", ziel, L0 + 0.34, zc, U * 0.66, maxw=SCR_W - 0.95)
    dfi_text(f"Z{i}_t", zeit, R0, zc, U * 0.6, align="RIGHT", maxw=0.45)
zc = -SCR_H / 2 + 1.05 * U / 2
dfi_text("Lauf", TITEL["laufschrift"], L0, zc, U * 0.5, maxw=SCR_W - 0.14, font=FONT_R)

# ---------------------------------------------------------------- Welt (blaue Stunde)
world = bpy.data.worlds.new("BlaueStunde")
scene.world = world
world.use_nodes = True
wt = world.node_tree
bg = wt.nodes["Background"]
tc = wt.nodes.new("ShaderNodeTexCoord")
sep = wt.nodes.new("ShaderNodeSeparateXYZ")
mr = wt.nodes.new("ShaderNodeMapRange")
mr.inputs["From Min"].default_value = -0.08
mr.inputs["From Max"].default_value = 0.7
ramp = wt.nodes.new("ShaderNodeValToRGB")
el = ramp.color_ramp.elements
el[0].position = 0.0
el[0].color = col("#0C0F18")
el[1].position = 1.0
el[1].color = col("#08122E")
for pos, h in ((0.1, "#B4664A"), (0.16, "#7D6680"), (0.3, "#2D3D78"), (0.6, "#14214D")):
    e = el.new(pos)
    e.color = col(h)
wt.links.new(tc.outputs["Generated"], sep.inputs[0])
wt.links.new(sep.outputs["Z"], mr.inputs["Value"])
wt.links.new(mr.outputs[0], ramp.inputs[0])
wt.links.new(ramp.outputs[0], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 1.0

# Fuelllicht von oben (blaeulich) und Kante
for name, loc, rot, energy, c, size in (
        ("Himmel", (0, -6, 14), (0, 0, 0), 1800, (0.6, 0.7, 1.0), 30),
        ("Kante", (-14, 9, 7), (math.radians(-60), 0, math.radians(200)), 900, (0.7, 0.75, 1.0), 10)):
    la = bpy.data.lights.new(name, "AREA")
    la.energy = energy
    la.size = size
    la.color = c
    lo = bpy.data.objects.new(name, la)
    scene.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = rot

# ---------------------------------------------------------------- Kamera + Animation
cam_d = bpy.data.cameras.new("Kamera")
cam_d.sensor_fit = "HORIZONTAL"
cam_d.sensor_width = SENSOR
cam_d.clip_start = 0.05
cam_d.clip_end = 2000
cam_d.dof.use_dof = True
cam_d.dof.aperture_fstop = 5.6
CAM = bpy.data.objects.new("Kamera", cam_d)
scene.collection.objects.link(CAM)
scene.camera = CAM
CAM.rotation_mode = "QUATERNION"


def look(frm, to):
    return (to - frm).to_track_quat("-Z", "Y")


def smooth(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * t * (t * (t * 6 - 15) + 10)


def lerp(a, b, t):
    return a + (b - a) * t


Q_FINAL = look(CAM_FINAL, CAM_FINAL_ZIEL)
FOCUS_FINAL = (DFI_POS - CAM_FINAL).length * 0.9


def front_pose(xf, dist=D_NAH, z=LOGO_Z, zl=LOGO_Z):
    pos = Vector((xf + FRONT_X + dist, 0.0, z))
    return pos, look(pos, Vector((xf + FRONT_X, 0.0, zl)))


def key_flat(f, v):
    for node in FLAT_VALUES:
        node.outputs[0].default_value = v
        node.outputs[0].keyframe_insert("default_value", frame=f)


def key_cam(f, pos, q, lens, focus):
    CAM.location = pos
    CAM.rotation_quaternion = q
    cam_d.lens = lens
    cam_d.dof.focus_distance = focus
    CAM.keyframe_insert("location", frame=f)
    CAM.keyframe_insert("rotation_quaternion", frame=f)
    cam_d.keyframe_insert("lens", frame=f)
    cam_d.dof.keyframe_insert("focus_distance", frame=f)


if A.modus == "intro":
    N = INTRO_FRAMES
    for f in range(0, N + 1):
        u = min(f / 140.0, 1.0)
        xf = -45.0 + (45.0 + ZUG_STOP) * (1 - (1 - u) ** 2)
        ZUG.location = (xf, 0, 0)
        ZUG.keyframe_insert("location", frame=f)
        s = smooth(8, 120, f)
        tp, tq = front_pose(xf)
        pos = tp.lerp(CAM_FINAL, s)
        q = tq.slerp(Q_FINAL, s)
        key_cam(f, pos, q, lerp(LENS_NAH, LENS_FINAL, s), lerp(D_NAH, FOCUS_FINAL, s))
        key_flat(f, 1.0 - smooth(3, 20, f))
    scene.frame_start, scene.frame_end = 0, N - 1
else:
    N = OUTRO_FRAMES
    for f in range(0, N + 1):
        u = f / float(N - 4)
        u = min(u, 1.0)
        xf = ZUG_STOP + 40.0 * u * u
        ZUG.location = (xf, 0, 0)
        ZUG.keyframe_insert("location", frame=f)
        w = smooth(36, N - 4, f)
        dist = lerp(9.0, D_NAH, w)
        z = lerp(1.7, LOGO_Z, w)
        tp, tq = front_pose(xf, dist, z, lerp(1.45, LOGO_Z, w))
        s = smooth(0, 48, f)
        pos = CAM_FINAL.lerp(tp, s)
        q = Q_FINAL.slerp(tq, s)
        lens = lerp(LENS_FINAL, lerp(35.0, LENS_NAH, w), s)
        key_cam(f, pos, q, lens, lerp(FOCUS_FINAL, dist, s))
        key_flat(f, smooth(N - 12, N - 4, f))
    scene.frame_start, scene.frame_end = 0, N - 1

# ---------------------------------------------------------------- Tempo
for o in scene.objects:
    if o.type == "LIGHT" and o.name not in ("Himmel", "Kante"):
        o.data.use_shadow = False
    if o.type == "LIGHT" and o.name.startswith("Innen"):
        o.data.specular_factor = 0.0
try:
    rto = ee.ray_tracing_options
    rto.trace_max_roughness = 0.25
    rto.resolution_scale = "2"
    rto.use_denoise = True
except Exception as e:
    print("RT-Optionen", e)

# ---------------------------------------------------------------- Ausgabe
outdir = os.path.join(ROOT, "out", A.modus)
os.makedirs(outdir, exist_ok=True)
if A.blend:
    ziel = A.blend if os.path.isabs(A.blend) else os.path.join(ROOT, "out", A.blend)
    scene.render.filepath = "//render_" + A.modus + "/f_"
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=ziel, compress=True)
    if A.fbx:
        bpy.ops.object.select_all(action="DESELECT")
        for o in scene.objects:
            if o.type in ("CAMERA", "EMPTY", "MESH") and (o.animation_data or (o.parent and o.parent.animation_data)):
                o.select_set(True)
        bpy.ops.export_scene.fbx(filepath=A.fbx, use_selection=True, bake_anim=True,
                                 bake_anim_use_all_actions=False, object_types={"CAMERA", "EMPTY", "MESH"})
    print("BLEND", ziel)
    if A.nur_blend:
        sys.exit(0)
if A.stills:
    for f in [int(x) for x in A.stills.split(",")]:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(ROOT, "out", f"still_{A.modus}_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("STILL", scene.render.filepath)
else:
    if A.von >= 0:
        scene.frame_start = A.von
    if A.bis >= 0:
        scene.frame_end = A.bis
    scene.render.filepath = os.path.join(outdir, "f_")
    bpy.ops.render.render(animation=True)
    print("FERTIG", outdir)
