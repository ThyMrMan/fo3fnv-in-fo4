"""FNV's distant glow cards: region imposters that are only light, kept and drawn from afar.

FNV shows a region imposter only from inside the regions listing it, and
the converter leaves imposters out (regions.imposters) because each copies
a real object nearby. The Strip's night glow over the Mojave
(NVStripLightPollution cards, FXGlowSimpleFillHalf01Imposter sheets)
copies nothing: every shape of its mesh is unlit and alpha-blended. Those
references are kept, persistent and Is Full LOD, as Fallout4.esm's
GSCraterClouds01 glow is.

See: docs/fork/fo4_look.md#route-horizon
"""
import functools

from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import fnv_nif
from fo4_import.pipeline.export_index import export_file, export_records
from fo4_import.spike.regions import imposters

#: Base record types an imposter reference places.
BASES = ('STAT', 'ACTI', 'MSTT')


def unlit_blend(geom) -> bool:
    """Whether an FNV shape is unlit (BSShaderNoLightingProperty) and alpha-blended."""
    props = {type(p).__name__: p for p in geom.get_properties()}
    alpha = props.get('NiAlphaProperty')
    return 'BSShaderNoLightingProperty' in props and alpha is not None and bool(alpha.flags & 1)


@functools.cache
def light_only(export_dir, model: str) -> bool:
    """Whether FNV mesh `model` has shapes and every one is unlit_blend."""
    path = export_file(export_dir, 'meshes', model.replace('/', '\\').lower()) if model else None
    if path is None or not path.is_file():
        return False
    shapes = [b for b in fnv_nif(path).tree() if isinstance(b, NifFormat.NiGeometry)]
    return bool(shapes) and all(unlit_blend(s) for s in shapes)


@functools.cache
def glow_cards(export_dir) -> frozenset:
    """FNV FormIDs of the imposter references whose mesh is light_only."""
    listed = imposters()
    models = {int(r['FormID'], 16): r.get('Model.MODL', '') for sig in BASES for r in export_records(export_dir, sig)}
    return frozenset(int(r['FormID'], 16) for r in export_records(export_dir, 'REFR')
                     if int(r['FormID'], 16) in listed and light_only(export_dir, models.get(int(r['NAME'], 16), '')))
