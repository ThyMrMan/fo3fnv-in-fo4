"""FO3/FNV IsAnimPlaying on Fallout 4: the object sequence this script last played, timed from its mesh.

Fallout 4 cannot ask a NIF sequence whether it runs. A script that reads IsAnimPlaying
records, at each sequence it plays (PlayGroup, as PlayGamebryoAnimation), the reference, the group and
the real time it ends: the sequence's authored length in the target's FNV
mesh, endless for a looping one. TES4_AnimPlaying(<ref>, <group>) reads that
record: 1 from the play until the end while the 3D stays loaded, for the
same reference and group ("" any). A target held in a variable the script set from its own GetLinkedRef is
timed from the linked references of its placed references (XLKR); another variable records no length. A door
the script did not play reads Fallout 4's own GetOpenState: playing while opening or closing.
See: docs/fork/fo4_plan_script_functions.md#phases
"""

import functools

from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import fnv_nif
from fo4_import.pipeline.export_index import export_file, export_records
from script_convert.target import is_fallout4
from script_convert.tes4 import nodes as N

#: The read the call converts to.
READ = 'TES4_AnimPlaying'
#: NiControllerSequence cycle type CYCLE_CLAMP; the others (loop, reverse) repeat until another group plays.
CLAMP = 2
#: Seconds recorded for a repeating sequence: it runs until replaced.
ENDLESS = 1.0e9
#: Fallout 4 GetOpenState values of a door moving (opening, closing), as FO3/FNV's.
OPENING, CLOSING = 2, 4


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


@functools.cache
def _placements(export_dir: str) -> tuple:
    """({base FormID: its placed references}, {placed reference: its linked reference}) of the export's REFRs."""
    placed, linked = {}, {}
    for rec in export_records(export_dir, 'REFR'):
        placed.setdefault(rec.get('NAME', ''), []).append(rec['FormID'])
        if rec.get('XLKR.LinkedRef'):
            linked[rec['FormID']] = rec['XLKR.LinkedRef']
    return placed, linked


def linked_vars(bodies: list) -> frozenset:
    """The variables (lower case) `bodies` set from the script's own GetLinkedRef."""
    return frozenset(st.target.called for body in bodies for st in N.walk_stmts(body)
                     if isinstance(st, N.Assign) and st.target is not None and _own_linked_ref(st.value))


def _own_linked_ref(value) -> bool:
    """Whether `value` is a bare GetLinkedRef, not `x.GetLinkedRef`."""
    return isinstance(value, (N.Ident, N.Call)) and value.called == 'getlinkedref' \
        and getattr(value, 'receiver', None) is None


def _script_fid(xref, script_edid: str) -> str:
    """The FormID of script `script_edid`; '' when unknown."""
    return next((f for f, e in xref.script_formid_to_edid.items() if e.lower() == script_edid.lower()), '')


def linked_bases(ctx, ref: str) -> list:
    """Base FormIDs of the references `ref` can hold when the script set it from its own GetLinkedRef: those
    linked from each placed reference of the records the script sits on; [] for another name."""
    xref = ctx.xref
    export_dir = getattr(xref, 'export_dir', '') if xref else ''
    fid = _script_fid(xref, ctx.sc.edid) if export_dir and ref.lower() in ctx.sc.linked_vars else ''
    if not fid:
        return []
    placed, linked = _placements(str(export_dir))
    refs = [r for owner in xref.attached_records(fid) for r in placed.get(owner, [owner])]
    return [xref.record_base.get(linked[r], '') or linked[r] for r in refs if r in linked]


def _models(ctx, ref: str) -> list:
    """Authored models of `ref`'s base: a linked variable's linked references, or the records the script sits on
    when `ref` is '' (Self)."""
    xref = ctx.xref
    if ref and ref.lower() in ctx.sc.linked_vars:
        return [xref.record_model.get(base, '') for base in linked_bases(ctx, ref)]
    if ref:
        fid = xref.edid_to_formid.get(ref.lower(), '')
        return [xref.record_model.get(xref.record_base.get(fid, '') or fid, '')] if fid else []
    fid = _script_fid(xref, ctx.sc.edid)
    return [xref.record_model.get(owner, '') for owner in xref.attached_records(fid)] if fid else []


def seconds(ctx, ref: str, group: str) -> float:
    """The longest `group` sequence among the target's FNV meshes; 0.0 when none is known."""
    export_dir = getattr(ctx.xref, 'export_dir', '') if ctx.xref else ''
    if not export_dir:
        return 0.0
    found = [sequence_seconds(export_dir, m).get(group.lower(), 0.0) for m in _models(ctx, ref)]
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


#: The variables and TES4_AnimPlaying a script reading IsAnimPlaying carries (script_helpers adds them).
DECLARE = ['ObjectReference TES4_AnimRef', 'String TES4_AnimGroup', 'Float TES4_AnimStart', 'Float TES4_AnimEnd',
           '', f'Int Function {READ}(ObjectReference akRef, String asGroup)',
           '  {FNV IsAnimPlaying: 1 while the sequence this script last played on akRef runs (asGroup "" any), or',
           '   while a door it did not play opens or closes.}',
           '  Float now = Utility.GetCurrentRealTime()',
           '  If akRef && akRef == TES4_AnimRef && (asGroup == "" || asGroup == TES4_AnimGroup) '
           '&& now >= TES4_AnimStart && now < TES4_AnimEnd && akRef.Is3DLoaded()',
           '    Return 1',
           '  ElseIf akRef && akRef != TES4_AnimRef && akRef.GetBaseObject() as Door',
           '    Int TES4_OpenState = akRef.GetOpenState()',
           f'    Return (TES4_OpenState == {OPENING} || TES4_OpenState == {CLOSING}) as Int',
           '  EndIf',
           '  Return 0',
           'EndFunction', '']
