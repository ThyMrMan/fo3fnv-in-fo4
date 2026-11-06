"""FNV's ambient idle tree on Fallout 4: what of it is built, and its records' shape.

See: docs/fork/fo4_idles.md#trees
"""

import struct
from collections import Counter, defaultdict
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import idles as ID
from tes5_import.base.tes5_reader import sub_map

ROOT, NO_WEAPON, WEAPON, SMOKE, SCRATCH, ARMORED = 0x10, 0x11, 0x12, 0x13, 0x14, 0x15


def _raw(func: str, value: float = 1.0, op: int = 0) -> str:
    """One FNV condition on the subject, raw hex."""
    return struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), 0, 0, 0, 0).hex()


def _idle(fid: int, edid: str, parent: int, clip: str = '', previous: int = 0, *conds: str) -> dict:
    """An FNV IDLE record: a group node without `clip`."""
    return {'FormID': f'{fid:08X}', 'EditorID': edid, 'ANAM.Parent': f'{parent:08X}', 'ANAM.Previous': f'{previous:08X}',
            'Model.MODL': clip or 'Characters\\_Male\\IdleAnims', 'ConditionCount': str(len(conds)),
            **{f'Condition[{i}].Raw': c for i, c in enumerate(conds)}}


def _tree() -> 'ID.Idles':
    """GeneralIdles: a weapon-out group, a no-weapon group (smoking, scratching), an armor-rated leaf."""
    recs = [_idle(ROOT, 'GeneralIdles', 0, '', 0, _raw('IsSneaking', 0.0)),
            _idle(WEAPON, 'NPCWeaponIdles', ROOT, '', 0, _raw('IsWeaponOut')),
            _idle(NO_WEAPON, 'NPCNonWeaponIdles', ROOT, '', WEAPON, _raw('IsWeaponOut', 0.0)),
            _idle(SMOKE, 'NPCSmokingIdle', NO_WEAPON, 'Characters\\_Male\\IdleAnims\\Smoking.kf'),
            _idle(ARMORED, 'Relaxed', NO_WEAPON, 'Characters\\_Male\\IdleAnims\\Relaxed.kf', SMOKE,
                  _raw('GetArmorRating', 10.0, 0xA0)),
            _idle(SCRATCH, 'ScratchingSelf', NO_WEAPON, 'Characters\\_Male\\IdleAnims\\Scratch.kf', ARMORED,
                  _raw('GetRandomPercent', 84.0, 0x80))]
    idles = ID.Idles.__new__(ID.Idles)
    idles.builder = SimpleNamespace(fnv_id=lambda fnv: 0x0B000000 | fnv, counts=Counter(), script_vars={},
                                    ids=SimpleNamespace(is_own=lambda fnv: True))
    idles.records = {int(r['FormID'], 16): r for r in recs}
    idles.names = {r['EditorID'].lower(): fid for fid, r in idles.records.items()}
    idles.used, idles.counted, idles.form_map, idles.tree, idles.groups = {}, set(), {}, {}, set()
    idles.checked = {SMOKE: '', ARMORED: '', SCRATCH: ''}
    idles.kids = defaultdict(list)
    for fid, rec in idles.records.items():
        idles.kids[int(rec['ANAM.Parent'], 16)].append(fid)
    idles._ambient_tree()
    return idles


def test_the_tree_keeps_what_converts_and_leaves_out_the_drawn_weapon_branch():
    """Root, no-weapon group, smoking and scratching built; the weapon group and an unconvertible test left out."""
    idles = _tree()
    assert set(idles.used) == {ROOT, NO_WEAPON, SMOKE, SCRATCH} and idles.groups == {ROOT, NO_WEAPON}
    assert idles.builder.counts['ambient idle left out (conditions)'] == 2


def test_the_root_hangs_under_action_idle_and_a_left_out_previous_is_skipped():
    """Root under ActionIdle; scratching's previous skips the left-out leaf to smoking; the group follows nothing."""
    idles = _tree()
    assert idles._links(ROOT) == (ID.ACTION_IDLE, 0)
    assert idles._links(SCRATCH) == (0x0B000000 | NO_WEAPON, 0x0B000000 | SMOKE)
    assert idles._links(NO_WEAPON) == (0x0B000000 | ROOT, 0)


def test_a_group_node_is_graph_and_conditions_only_as_vanillas_are():
    """No event, no clip, not loose; a leaf keeps its play-once event and clip."""
    idles = _tree()
    group = sub_map(ID.pack_idle(1, idles.records[NO_WEAPON], idles.tree[NO_WEAPON], (ID.ROOT_GRAPH, ''),
                                 idles._links(NO_WEAPON))[24:])
    leaf = sub_map(ID.pack_idle(2, idles.records[SMOKE], b'', (ID.ROOT_GRAPH, 'X.hkx'), idles._links(SMOKE))[24:])
    assert b'ENAM' not in group and b'GNAM' not in group and group[b'DATA'][2] == 0 and b'CTDA' in group
    assert leaf[b'ENAM'].rstrip(b'\0') == ID.PLAY_ONCE.encode() and leaf[b'GNAM'].rstrip(b'\0') == b'X.hkx'


def test_a_plugin_not_owning_the_root_builds_no_tree():
    """A DLC build (its export carries its master's idles) leaves the tree to the master."""
    idles = _tree()
    idles.builder.ids.is_own = lambda fnv: False
    assert idles.ambient_records() == []
