"""FNV reputations as FO4 globals in a FormList, which conditions read and TES4_Reputation keeps in step, and
their Pip-Boy page.

Each REPU becomes a FormList on FNV's own object id listing its globals in
the Skyrim build's order (reputation_falloutnv.SLOTS: infamy, fame, the
mixed, good and bad threshold, the maximum), so the converted scripts'
TES4_Reputation calls work alike: a script property naming the REPU gets
the list, and GetReputation / GetReputationThreshold read a global. On
Fallout 4 the list also holds the actor value its Pip-Boy page row shows
(slot 6, named as FNV names the faction) and the global showing that row
(slot 7); Pip-Boy Tabs reads both through a tab file in Data\\PBT, laid
out as the REPUTATION mod's (Nexus 79394): a title per fame and infamy
range, rows hidden until there is reputation.

See: docs/fork/fo4_pipeline.md#reputation
"""

import struct
from pathlib import Path

from fo4_import.base.support_records import pack_global
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord
from tes5_import.record_types.reputation_falloutnv import KARMA_AV, KARMA_GLOBAL, SLOTS

#: derive_formid site of a reputation's globals (key: the global's EditorID).
GLOBAL_SITE = 'FNV REPU GLOB'
#: derive_formid site of the Pip-Boy page's forms (key: the form's EditorID).
PAGE_SITE = 'FNV REPU page'
#: Key prefix of a reputation global in a form map: ('rep', REPU FormID, slot index).
SLOT_KEY = 'rep'
#: Pip-Boy Tabs pages a tab goes on: STAT, DATA.
STAT_PAGE, DATA_PAGE = 0, 2
#: Form map key of the karma global, which FNV's Karma actor value (on the player) reads as.
KARMA_KEY = ('av global', KARMA_AV)
#: The page rows' actor value layout, as the REPUTATION mod's RPTN_PBT_FirstAV_*: default 0, AVFL, NAM1.
AV_FLAGS, AV_KIND = 0x400, 8
#: FNV's titles by infamy range * 4 + fame range (TES4_Reputation.Range), as Pip-Boy Tabs' StringArray.
TITLES = ('Neutral|Accepted|Liked|Idolized|Shunned|Mixed|Smiling Troublemaker|Good-Natured Rascal|Hated|'
          'Sneering Punk|Unpredictable|Dark Hero|Vilified|Merciful Thug|Soft-Hearted Devil|Wild Child')


def write_reputations(builder, export_dir: Path) -> tuple:
    """({REPU EditorID: FO4 FormList}, {('rep', REPU FormID, slot): FO4 global}) of every FNV reputation, written,
    and the karma global (TES4Karma, KARMA_KEY) the scripts' RewardKarma sets; the page's row lists (actor
    values, shown globals) in `builder.reputation_page`."""
    names, slots, rows, shown = {}, {}, [], []
    for rec in export_records(export_dir, 'REPU'):
        if not rec.get('EditorID'):
            continue
        globs = [_global(builder, GLOBAL_SITE, f'TES4Rep{slot}_{rec["EditorID"]}',
                         float(rec.get('DATA.Value', 0) or 0) if start is None else start) for slot, start in SLOTS]
        rows.append(actor_value(builder, f'TES4RepTitle_{rec["EditorID"]}', rec.get('FULL') or rec['EditorID']))
        shown.append(_global(builder, PAGE_SITE, f'TES4RepShown_{rec["EditorID"]}', 0.0))
        fid = builder.fnv_id(rec['FormID'])
        builder.writer.add_record('FLST', _form_list(fid, f'FNV_{rec["EditorID"]}', globs + [rows[-1], shown[-1]]))
        names[rec['EditorID']] = fid
        slots.update({(SLOT_KEY, int(rec['FormID'], 16), i): g for i, g in enumerate(globs)})
    builder.reputation_page = [page_list(builder, 'TES4RepPageRows', rows),
                               page_list(builder, 'TES4RepPageShown', shown)]
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


def write_page(builder, data_dir: Path, plugin: str) -> Path:
    """Write the reputation tab (write_tab) on the DATA page; its path."""
    rows, shown = builder.reputation_page
    return write_tab(data_dir, plugin, ('Reputation', DATA_PAGE), rows, TITLES, shown)


def write_tab(data_dir: Path, plugin: str, tab: tuple, rows: int, titles: str, shown: 'int | None' = None) -> Path:
    """Write a Pip-Boy Tabs type 2 tab (Data\\PBT\\<plugin>_<name>.ini): `tab` (name, page), the FormList `rows`
    of actor values whose value picks from `titles` ('|'-separated), rows shown by FormList `shown`; its path."""
    name, page = tab
    path = data_dir / 'PBT' / f'{Path(plugin).stem}_{name}.ini'
    path.parent.mkdir(parents=True, exist_ok=True)
    filters = f'{plugin}|{shown & 0xFFFFFF:X}' if shown else ''
    path.write_text('\n'.join(['[Main]', 'INIVersion=2', 'TabType=2', 'ShowListOnly=0',
                               f'UniqueID={Path(plugin).stem}_{name}Tab', f'TabName={name}',
                               f'PageNumberToInsert={page}', f'FirstList={plugin}|{rows & 0xFFFFFF:X}',
                               f'StringArray={titles}', f'FilterList={filters}',
                               'SecondList=', 'MaxValueList=', 'Precision=', '']), encoding='utf-8')
    return path
