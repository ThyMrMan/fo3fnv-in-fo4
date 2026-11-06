"""FNV reputations as FO4 globals in a FormList, which conditions read and TES4_Reputation keeps in step, and
their Pip-Boy page.

Each REPU becomes a FormList on FNV's own object id listing its globals in
the Skyrim build's order (reputation_falloutnv.SLOTS: infamy, fame, the
mixed, good and bad threshold, the maximum), so the converted scripts'
TES4_Reputation calls work alike: a script property naming the REPU gets
the list, and GetReputation / GetReputationThreshold read a global. On
Fallout 4 the list also holds the actor value its Pip-Boy page row shows
(slot 6, named as FNV names the faction) and the global showing that row
(slot 7): the Pip-Boy's REPUTATION tab (pipboy_tabs) shows a title per
fame and infamy range, rows hidden until there is reputation, as the
REPUTATION mod (Nexus 79394) lays it out.

See: docs/fork/fo4_pipeline.md#reputation
"""

import struct
from pathlib import Path

from fo4_import.base.support_records import pack_global
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.pipboy_tabs import tab_formid, tab_quest
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord
from tes5_import.record_types.reputation_falloutnv import KARMA_AV, KARMA_GLOBAL, SLOTS

#: derive_formid site of a reputation's globals (key: the global's EditorID).
GLOBAL_SITE = 'FNV REPU GLOB'
#: derive_formid site of the Pip-Boy page's forms (key: the form's EditorID).
PAGE_SITE = 'FNV REPU page'
#: Key prefix of a reputation global in a form map: ('rep', REPU FormID, slot index).
SLOT_KEY = 'rep'
#: Form map key of the karma global, which FNV's Karma actor value (on the player) reads as.
KARMA_KEY = ('av global', KARMA_AV)
#: The page rows' actor value layout, as the REPUTATION mod's RPTN_PBT_FirstAV_*: default 0, AVFL, NAM1.
AV_FLAGS, AV_KIND = 0x400, 8
#: F3NV_ReputationTab's texts and the FalloutNV.esm game settings holding them.
CHANGE_TEXTS = {'FameGained': 'sRepPositiveGain', 'FameReduced': 'sRepPositiveLoss',
                'InfamyGained': 'sRepNegativeGain', 'InfamyReduced': 'sRepNegativeLoss'}
#: F3NV_ReputationTab's title sounds: FalloutNV.exe's sRepChangePosSound and sRepChangeNegSound (SOUN EditorIDs).
TITLE_SOUNDS = {'TitleUp': 'UIRepGood', 'TitleDown': 'UIRepBad'}
#: The REPUTATION tab's script, which also holds what a reputation change shows.
TAB_SCRIPT = 'F3NV_ReputationTab'
#: FNV's titles by infamy range * 4 + fame range (TES4_Reputation.Range).
TITLES = ('Neutral', 'Accepted', 'Liked', 'Idolized', 'Shunned', 'Mixed', 'Smiling Troublemaker', 'Good-Natured Rascal',
          'Hated', 'Sneering Punk', 'Unpredictable', 'Dark Hero', 'Vilified', 'Merciful Thug', 'Soft-Hearted Devil',
          'Wild Child')


def write_reputations(builder, export_dir: Path) -> tuple:
    """({REPU EditorID: FO4 FormList}, {('rep', REPU FormID, slot): FO4 global}) of every FNV reputation, written,
    and the karma global (TES4Karma, KARMA_KEY) the scripts' RewardKarma sets; the page's row lists (actor
    values, shown globals) and change_messages() in `builder.reputation_page`; each list also holds the
    REPUTATION tab's quest."""
    names, slots, rows, shown, tab = {}, {}, [], [], tab_formid(builder, 'REPUTATION')
    for rec in export_records(export_dir, 'REPU'):
        if not rec.get('EditorID'):
            continue
        globs = [_global(builder, GLOBAL_SITE, f'TES4Rep{slot}_{rec["EditorID"]}',
                         float(rec.get('DATA.Value', 0) or 0) if start is None else start) for slot, start in SLOTS]
        rows.append(actor_value(builder, f'TES4RepTitle_{rec["EditorID"]}', rec.get('FULL') or rec['EditorID']))
        shown.append(_global(builder, PAGE_SITE, f'TES4RepShown_{rec["EditorID"]}', 0.0))
        fid = builder.fnv_id(rec['FormID'])
        builder.writer.add_record('FLST', _form_list(fid, f'FNV_{rec["EditorID"]}',
                                                     globs + [rows[-1], shown[-1], tab]))
        names[rec['EditorID']] = fid
        slots.update({(SLOT_KEY, int(rec['FormID'], 16), i): g for i, g in enumerate(globs)})
    builder.reputation_page = [page_list(builder, 'TES4RepPageRows', rows),
                               page_list(builder, 'TES4RepPageShown', shown), change_messages(builder, export_dir)]
    builder.counts['reputations'] = len(names)
    names[KARMA_GLOBAL] = slots[KARMA_KEY] = _global(builder, GLOBAL_SITE, KARMA_GLOBAL, 0.0)
    return names, slots


def _global(builder, site: str, edid: str, value: float) -> int:
    """A float global `edid` on a FormID hashed at `site`, written."""
    fid = builder.writer.derive_formid(site, edid)
    builder.writer.add_record('GLOB', pack_global(fid, edid, 'f', value))
    return fid


def actor_value(builder, edid: str, name: str) -> int:
    """A Pip-Boy page row's actor value `edid` shown as `name` (PAGE_SITE), written."""
    fid = builder.writer.derive_formid(PAGE_SITE, edid)
    subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('FULL', name)
    subs += pack_string_subrecord('DESC', '') + pack_string_subrecord('ANAM', name)
    subs += pack_subrecord('NAM0', struct.pack('<f', 0.0)) + pack_subrecord('AVFL', struct.pack('<I', AV_FLAGS))
    subs += pack_subrecord('NAM1', struct.pack('<I', AV_KIND))
    builder.writer.add_record('AVIF', pack_fo4_record('AVIF', fid, 0, subs))
    return fid


def page_list(builder, edid: str, forms: list) -> int:
    """A FormList `edid` of `forms` on a FormID hashed at PAGE_SITE, written."""
    fid = builder.writer.derive_formid(PAGE_SITE, edid)
    builder.writer.add_record('FLST', _form_list(fid, edid, forms))
    return fid


def _form_list(fid: int, edid: str, forms: list) -> bytes:
    """An FO4 FormList `edid` of `forms` (LNAM each)."""
    subs = pack_string_subrecord('EDID', edid) + b''.join(pack_subrecord('LNAM', struct.pack('<I', f)) for f in forms)
    return pack_fo4_record('FLST', fid, 0, subs)


def change_messages(builder, export_dir: Path) -> tuple:
    """({TAB_SCRIPT sound property: FO4 SNDR}, {text property: ('string', FalloutNV.esm's text)}) of what a
    reputation change shows; a sound or text FNV lacks is left out.
    See: docs/fork/fo4_pipeline.md#reputation-messages
    """
    settings = {r.get('EditorID'): r.get('DATA.Value', '') for r in export_records(export_dir, 'GMST')}
    texts = {prop: ('string', settings[edid]) for prop, edid in CHANGE_TEXTS.items() if settings.get(edid)}
    by_edid = {r.get('EditorID'): fnv for fnv, r in builder.sounds.records.items()}
    sounds = {prop: builder.sounds.descriptor(by_edid.get(edid, 0)) for prop, edid in TITLE_SOUNDS.items()}
    return {prop: fid for prop, fid in sounds.items() if fid}, texts


def write_page(builder) -> int:
    """Write the REPUTATION tab on TAB_SCRIPT, with what a change shows; its FormID."""
    rows, shown, messages = builder.reputation_page
    return tab_quest(builder, 'REPUTATION', rows, TITLES, shown, TAB_SCRIPT, messages)
