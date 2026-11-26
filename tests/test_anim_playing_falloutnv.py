"""IsAnimPlaying on Fallout 4: a linked variable is timed from its linked reference's mesh, a door from its state.

See: docs/fork/fo4_plan_script_functions.md#phases
"""

from types import SimpleNamespace

from script_convert import anim_playing_falloutnv as A
from script_convert.tes4 import nodes as N


def test_only_a_bare_get_linked_ref_marks_a_variable():
    """`set myLink to GetLinkedRef` marks myLink; `x.GetLinkedRef` and other values do not."""
    body = [N.Assign(target=N.Ident('myLink'), value=N.Ident('getLinkedRef')),
            N.Assign(target=N.Ident('other'), value=N.Member(N.Ident('myLink'), 'getLinkedRef')),
            N.Assign(target=N.Ident('called'), value=N.Call('GetLinkedRef')),
            N.Assign(target=N.Ident('far'), value=N.Call('GetLinkedRef', receiver=N.Ident('myLink'))),
            N.Assign(target=N.Ident('n'), value=N.Ident('getSelf'))]
    assert A.linked_vars([body]) == {'mylink', 'called'}


def test_a_linked_variable_takes_its_linked_references_models(monkeypatch):
    """The script sits on base 0x10, placed as 0x20 linked to 0x30 (a vertibird): the vertibird's model."""
    monkeypatch.setattr(A, '_placements', lambda folder: ({'00000010': ['00000020']}, {'00000020': '00000030'}))
    xref = SimpleNamespace(export_dir='x', script_formid_to_edid={'00000001': 'VertibirdSCRIPT'},
                           attached_records=lambda fid: ['00000010'], record_base={'00000030': '00000040'},
                           record_model={'00000040': 'vertibird.nif', '00000010': 'handle.nif'}, edid_to_formid={})
    ctx = SimpleNamespace(xref=xref, sc=SimpleNamespace(edid='VertibirdSCRIPT', linked_vars=frozenset({'linkedref'})))
    assert A._models(ctx, 'linkedRef') == ['vertibird.nif'] and A._models(ctx, '') == ['handle.nif']
    assert A._models(ctx, 'unknownRef') == []


def test_a_linked_variable_names_its_linked_references_bases(monkeypatch):
    """linked_bases follows the placed reference's XLKR to its base; another name or no export gives none."""
    monkeypatch.setattr(A, '_placements', lambda folder: ({'00000010': ['00000020']}, {'00000020': '00000030'}))
    xref = SimpleNamespace(export_dir='x', script_formid_to_edid={'00000001': 'PodSCRIPT'},
                           attached_records=lambda fid: ['00000010'], record_base={'00000030': '00000040'})
    ctx = SimpleNamespace(xref=xref, sc=SimpleNamespace(edid='PodSCRIPT', linked_vars=frozenset({'mylink'})))
    assert A.linked_bases(ctx, 'myLink') == ['00000040'] and A.linked_bases(ctx, 'other') == []
    ctx.xref = None
    assert A.linked_bases(ctx, 'myLink') == []


def test_a_door_the_script_did_not_play_reads_its_open_state():
    """A door falls back to GetOpenState: opening (2) or closing (4)."""
    text = '\n'.join(A.DECLARE)
    assert 'GetBaseObject() as Door' in text and 'TES4_OpenState == 2 || TES4_OpenState == 4' in text
