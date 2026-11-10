"""FO3/FNV IsAnimPlaying on Fallout 4: the object sequence this script last played, timed from its mesh.

Fallout 4 cannot ask a NIF sequence whether it runs. A script that reads IsAnimPlaying
records, at each sequence it plays (PlayGroup, as PlayGamebryoAnimation), the reference, the group and
the real time it ends: the sequence's authored length in the target's FNV
mesh, endless for a looping one. TES4_AnimPlaying(<ref>, <group>) reads that
record: 1 from the play until the end while the 3D stays loaded, for the
same reference and group ("" any). A target the build cannot resolve to a
mesh (a ref variable) records no length, so it reads 0 as before.
See: docs/fork/fo4_plan_script_functions.md#phases
"""

import functools

from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import fnv_nif
from fo4_import.pipeline.export_index import export_file
from script_convert.target import is_fallout4

#: The read the call converts to.
READ = 'TES4_AnimPlaying'
#: NiControllerSequence cycle type CYCLE_CLAMP; the others (loop, reverse) repeat until another group plays.
CLAMP = 2
#: Seconds recorded for a repeating sequence: it runs until replaced.
ENDLESS = 1.0e9


@functools.cache
def sequence_seconds(export_dir: str, model: str) -> dict:
    """{sequence name, lower case: seconds it plays} of FNV mesh `model` (ENDLESS when it repeats); {} unread."""
    path = export_file(export_dir, 'meshes', model.replace('/', '\\').lower()) if model else None
    if path is None or not path.is_file():
        return {}
    out = {}
    for block in fnv_nif(path).tree():
        if isinstance(block, NifFormat.NiControllerSequence):
            span = (block.stop_time - block.start_time) / (block.frequency or 1.0)
            out[block.name.decode('cp1252').lower()] = span if block.cycle_type == CLAMP else ENDLESS
    return out


def _models(xref, ref: str, script_edid: str) -> list:
    """Authored models of `ref`'s base, or of the records the script sits on when `ref` is '' (Self)."""
    if ref:
        fid = xref.edid_to_formid.get(ref.lower(), '')
        return [xref.record_model.get(xref.record_base.get(fid, '') or fid, '')] if fid else []
    fid = next((f for f, e in xref.script_formid_to_edid.items() if e.lower() == script_edid.lower()), '')
    return [xref.record_model.get(owner, '') for owner in xref.attached_records(fid)] if fid else []


def seconds(ctx, ref: str, group: str) -> float:
    """The longest `group` sequence among the target's FNV meshes; 0.0 when none is known."""
    export_dir = getattr(ctx.xref, 'export_dir', '') if ctx.xref else ''
    if not export_dir:
        return 0.0
    found = [sequence_seconds(export_dir, m).get(group.lower(), 0.0) for m in _models(ctx.xref, ref, ctx.sc.edid)]
    return max(found, default=0.0)


def played(ctx, call, obj: str, group: str) -> list:
    """The lines recording that `obj` started `group`, in a Fallout 4 script reading IsAnimPlaying; else []."""
    if not (is_fallout4() and ctx.sc.uses_anim_playing):
        return []
    return [f'TES4_AnimRef = {obj}', f'TES4_AnimGroup = "{group}"',
            'TES4_AnimStart = Utility.GetCurrentRealTime()',
            f'TES4_AnimEnd = TES4_AnimStart + {seconds(ctx, call.ref, group):.4f}']


def anim_playing(ctx, call):
    """`[ref.]IsAnimPlaying [group]` on Fallout 4: TES4_AnimPlaying(<ref>, "<group>"); declines elsewhere."""
    if not is_fallout4():
        return None
    group = call.source(0, '').strip().strip('"').strip("'")
    return f'{READ}({ctx._resolve_objref_ref(call.ref, call.extends)}, "{group}")'


def declare(conv) -> list:
    """The record's variables and TES4_AnimPlaying for a script reading IsAnimPlaying; [] otherwise."""
    if not conv.sc.uses_anim_playing:
        return []
    return ['ObjectReference TES4_AnimRef', 'String TES4_AnimGroup', 'Float TES4_AnimStart', 'Float TES4_AnimEnd',
            '', f'Int Function {READ}(ObjectReference akRef, String asGroup)',
            '  {FNV IsAnimPlaying: 1 while the sequence this script last played on akRef runs (asGroup "" any).}',
            '  Float now = Utility.GetCurrentRealTime()',
            '  If akRef && akRef == TES4_AnimRef && (asGroup == "" || asGroup == TES4_AnimGroup) '
            '&& now >= TES4_AnimStart && now < TES4_AnimEnd && akRef.Is3DLoaded()',
            '    Return 1',
            '  EndIf',
            '  Return 0',
            'EndFunction', '']
