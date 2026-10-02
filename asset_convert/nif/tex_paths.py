"""Texture path normalizing, shared by the converter and the shader builder.

Both are pure string/slot readers with no NIF state, so they sit below every
module that needs them.
"""
from asset_convert.game_paths import current_namespace


def bs_pp_texture_slots(prop):
    """Diffuse, normal and glow paths from an FO3/FNV BSShaderPPLightingProperty.

    FO3/FNV keep their paths in a BSShaderTextureSet on this property rather
    than on NiTexturingProperty, in the same slot order Skyrim uses: 0 diffuse,
    1 normal, 2 glow. All three are AUTHORED, so the normal is taken verbatim
    instead of being derived from the diffuse name.

    See: docs/commentary/asset_convert_nif.md#fo3fnv-shader-properties
    """
    tex_set = getattr(prop, 'texture_set', None)
    if tex_set is None:
        return b'', b'', b''
    slots = list(getattr(tex_set, 'textures', ()) or ())

    def slot(i):
        """The i-th texture path, or empty when absent or blank."""
        return slots[i] if i < len(slots) and slots[i] else b''

    return slot(0), slot(1), slot(2)


#: Source extensions that always ship as DDS, whatever the mesh calls them.
IMAGE_EXTS = ('tga', 'bmp')


def texture_rel_path(raw) -> str:
    """An authored texture path below `textures\\`, separators normalized FIRST.

    A leading 'data\\' and then 'textures\\' are dropped; every other segment
    is kept, 'lowres\\' included (`full_res_twin` decides its fallback).
    See: docs/commentary/asset_convert_texture.md#per-game-asset-namespace
    """
    path = raw.decode('utf-8', errors='replace') \
        if isinstance(raw, bytes) else str(raw)
    path = path.replace('/', '\\')
    if path.lower().startswith('data\\'):
        path = path[len('data\\'):]
    if path.lower().startswith('textures\\'):
        path = path[len('textures\\'):]
    return path


def rewrite_tex_path(raw_bytes):
    """The namespaced Skyrim path for an AUTHORED texture path; .tga/.bmp -> .dds.

    See: docs/commentary/asset_convert_shader.md#rewrite-tex-path
    """
    return ('Textures\\' + current_namespace() + '\\'
            + as_dds(texture_rel_path(raw_bytes)))


def full_res_twin(tex):
    """The full-resolution path a rewritten 'lowres\\' texture mirrors, or None.

    See: docs/commentary/asset_convert_shader.md#lowres-textures
    """
    prefix = 'Textures\\' + current_namespace() + '\\'
    lowres = prefix + 'lowres\\'
    if tex.lower().startswith(lowres.lower()):
        return prefix + tex[len(lowres):]
    return None


def as_dds(path: str) -> str:
    """A texture path with a .tga or .bmp extension changed to .dds.

    Morrowind names textures .tga but its archives ship .dds, substituting at
    load; without this every converted path names a file that does not exist.
    """
    stem, dot, ext = path.rpartition('.')
    if dot and ext.lower() in IMAGE_EXTS:
        return stem + '.dds'
    return path
