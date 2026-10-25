"""Drawing parts with moderngl (OpenGL 3.3 core, so macOS runs it too): diffuse, normal (a two-channel BC5 map,
Z rebuilt) and specular maps, Blinn-Phong lit from beside the camera, alpha test and blending, an orbit camera
about the model's bounds (Fallout 4 is Z-up). The look approximates the game's, not its shaders.

See: docs/fork/fo4_gui.md#preview
"""

import math
from dataclasses import dataclass

import moderngl
import numpy as np
from PIL import Image

from fo4_import.app.preview.materials import Surface
from fo4_import.app.preview.scene import bounds

#: A part with no surface: untextured, opaque.
PLAIN = Surface(None, None, None, -1, False, False)
#: Background color (RGBA).
BACKGROUND = (0.17, 0.18, 0.2, 1.0)
FIELD_OF_VIEW = 35.0
#: Per map, in texture unit order: (sampler uniform, materials.Surface field, "has it" uniform).
MAPS = (('diffuse_map', 'diffuse', 'has_diffuse'), ('normal_map', 'normal', 'has_normal'),
        ('spec_map', 'specular', 'has_spec'), ('palette_map', 'palette', 'has_palette'))

VERTEX = '''
#version 330
uniform mat4 mvp;
in vec3 in_pos;
in vec3 in_nrm;
in vec2 in_uv;
in vec4 in_tan;
out vec3 v_pos;
out vec3 v_nrm;
out vec2 v_uv;
out vec4 v_tan;
void main() {
    v_pos = in_pos;
    v_nrm = in_nrm;
    v_uv = in_uv;
    v_tan = in_tan;
    gl_Position = mvp * vec4(in_pos, 1.0);
}
'''

FRAGMENT = '''
#version 330
uniform sampler2D diffuse_map;
uniform sampler2D normal_map;
uniform sampler2D spec_map;
uniform sampler2D palette_map;
uniform bool has_diffuse;
uniform bool has_normal;
uniform bool has_spec;
uniform bool has_palette;
uniform float palette_row;
uniform bool blend;
uniform float alpha_ref;
uniform vec3 eye;
uniform vec3 light;
in vec3 v_pos;
in vec3 v_nrm;
in vec2 v_uv;
in vec4 v_tan;
out vec4 f_color;
void main() {
    vec4 base = has_diffuse ? texture(diffuse_map, v_uv) : vec4(0.7, 0.7, 0.7, 1.0);
    if (alpha_ref >= 0.0 && base.a < alpha_ref) discard;
    if (has_palette) base.rgb = texture(palette_map, clamp(vec2(base.g, palette_row), 0.0, 1.0)).rgb;
    vec3 n = normalize(gl_FrontFacing ? v_nrm : -v_nrm);
    if (has_normal) {
        vec3 t = normalize(v_tan.xyz - n * dot(n, v_tan.xyz));
        vec3 b = cross(n, t) * v_tan.w;
        vec2 rg = texture(normal_map, v_uv).rg * 2.0 - 1.0;
        vec3 tn = vec3(rg, sqrt(max(0.0, 1.0 - dot(rg, rg))));
        n = normalize(t * tn.x + b * tn.y + n * tn.z);
    }
    vec3 l = normalize(light);
    vec3 h = normalize(l + normalize(eye - v_pos));
    vec2 spec = has_spec ? texture(spec_map, v_uv).rg : vec2(0.2, 0.3);
    float lit = max(dot(n, l), 0.0);
    float shine = pow(max(dot(n, h), 0.0), 2.0 + spec.g * 126.0) * spec.r;
    f_color = vec4(base.rgb * (0.35 + 0.75 * lit) + vec3(shine * 0.6), blend ? base.a : 1.0);
}
'''


@dataclass
class Camera:
    """An orbit about the model: yaw and pitch in degrees, distance as a multiple of the model's radius."""
    yaw: float = 35.0
    pitch: float = 15.0
    zoom: float = 3.6


def tangents(part) -> np.ndarray:
    """Per-vertex tangents (xyz, handedness w) of a scene Part from its UVs, for normal mapping."""
    p, uv, n, tris = part.positions, part.uvs, part.normals, part.triangles.astype(np.int64)
    e1, e2 = p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]]
    d1, d2 = uv[tris[:, 1]] - uv[tris[:, 0]], uv[tris[:, 2]] - uv[tris[:, 0]]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) > 1e-12, 1.0 / np.where(det == 0, 1.0, det), 0.0)[:, None]
    face_t, face_b = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r, (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r
    t, b = np.zeros_like(p), np.zeros_like(p)
    for k in range(3):
        np.add.at(t, tris[:, k], face_t)
        np.add.at(b, tris[:, k], face_b)
    t -= n * np.sum(n * t, axis=1, keepdims=True)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    w = np.where(np.sum(np.cross(n, t) * b, axis=1) < 0.0, -1.0, 1.0)
    return np.hstack([t, w[:, None]]).astype(np.float32)


def matrices(center: np.ndarray, radius: float, camera: Camera, aspect: float) -> tuple:
    """(model-view-projection matrix, eye position, light direction) for `camera` about the bounds."""
    yaw, pitch = math.radians(camera.yaw), math.radians(camera.pitch)
    offset = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    distance = radius * camera.zoom
    eye = center + offset * distance
    forward = (center - eye) / np.linalg.norm(center - eye)
    side = np.cross(forward, [0.0, 0.0, 1.0])
    side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array([1.0, 0.0, 0.0])
    up = np.cross(side, forward)
    view = np.eye(4)
    view[0, :3], view[1, :3], view[2, :3] = side, up, -forward
    view[:3, 3] = -view[:3, :3] @ eye
    near, far, f = distance * 0.01, distance * 10.0, 1.0 / math.tan(math.radians(FIELD_OF_VIEW) / 2)
    proj = np.zeros((4, 4))
    proj[0, 0], proj[1, 1] = f / aspect, f
    proj[2, 2], proj[2, 3], proj[3, 2] = (far + near) / (near - far), 2 * far * near / (near - far), -1.0
    return proj @ view, eye, offset + up * 0.6 + side * 0.3


class Renderer:
    """Parts uploaded once to a moderngl context and drawn into any framebuffer."""

    def __init__(self, ctx):
        """A renderer on moderngl context `ctx`."""
        self.ctx = ctx
        self.program = ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        for unit, (sampler, _, _) in enumerate(MAPS):
            self.program[sampler].value = unit
        self.blank = ctx.texture((1, 1), 4, b'\xff\xff\xff\xff')
        self.draws, self.center, self.radius = [], np.zeros(3), 1.0

    def upload(self, parts: list, surfaces: list) -> None:
        """Replace what is drawn with `parts` (scene Parts) and their `surfaces` (materials.Surface)."""
        self.release()
        self.center, self.radius = bounds(parts)
        for part, surface in zip(parts, surfaces):
            surface = surface or PLAIN
            data = np.hstack([part.positions, part.normals, part.uvs, tangents(part)]).astype('f4')
            vbo, ibo = self.ctx.buffer(data.tobytes()), self.ctx.buffer(part.triangles.astype('u4').tobytes())
            vao = self.ctx.vertex_array(self.program, [(vbo, '3f 3f 2f 4f', 'in_pos', 'in_nrm', 'in_uv', 'in_tan')],
                                        ibo)
            maps = [self._texture(getattr(surface, attr)) for _, attr, _ in MAPS]
            self.draws.append((vao, [vbo, ibo], maps, surface))
        self.draws.sort(key=lambda d: d[3].blend)

    def _texture(self, texture):
        """A moderngl texture of a materials.Texture with mipmaps; None for none."""
        if texture is None:
            return None
        made = self.ctx.texture((texture.width, texture.height), 4, texture.rgba)
        made.build_mipmaps()
        made.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        return made

    def draw(self, fbo, camera: Camera) -> None:
        """Clear `fbo` and draw every part as `camera` sees it."""
        fbo.use()
        fbo.clear(*BACKGROUND)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        mvp, eye, light = matrices(self.center, self.radius, camera, fbo.width / max(fbo.height, 1))
        self.program['mvp'].write(mvp.T.astype('f4').tobytes())
        self.program['eye'].value, self.program['light'].value = tuple(eye), tuple(light)
        for vao, _, maps, surface in self.draws:
            self._draw_one(vao, maps, surface)
        self.ctx.disable(moderngl.BLEND)
        self.ctx.depth_mask = True

    def _draw_one(self, vao, maps: list, surface) -> None:
        """Draw one part with its maps and alpha settings."""
        for unit, ((_, _, flag), texture) in enumerate(zip(MAPS, maps)):
            (texture or self.blank).use(unit)
            self.program[flag].value = texture is not None
        self.program['palette_row'].value = surface.palette_row
        self.program['alpha_ref'].value = surface.alpha_test / 255.0 if surface.alpha_test >= 0 else -1.0
        self.program['blend'].value = surface.blend
        if surface.blend:
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self.ctx.depth_mask = False
        vao.render()

    def release(self) -> None:
        """Free the uploaded parts."""
        for vao, buffers, maps, _ in self.draws:
            vao.release()
            for item in [*buffers, *(m for m in maps if m is not None)]:
                item.release()
        self.draws = []


def render_image(parts: list, surfaces: list, size: tuple = (512, 512), camera: 'Camera | None' = None) -> Image.Image:
    """`parts` drawn off screen (no window) at `size`, as an RGBA image."""
    ctx = moderngl.create_standalone_context(require=330)
    try:
        fbo = ctx.framebuffer(color_attachments=[ctx.renderbuffer(size, 4)], depth_attachment=ctx.depth_renderbuffer(size))
        renderer = Renderer(ctx)
        renderer.upload(parts, surfaces)
        renderer.draw(fbo, camera or Camera())
        return Image.frombytes('RGBA', size, fbo.read(components=4)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    finally:
        ctx.release()
