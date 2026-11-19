"""FNV idle markers placed as the vanilla FO4 marker playing what theirs plays, for the cell spike.

FNV's idle marker (IDLM) lists FNV idles (the export's IDLA.Idle[i]), which FO4 does not have. As FNV
plays one of them at random, a placed one becomes a reference to the
Fallout4.esm IDLM or FURN playing the like of what most of them play
(PLAYS); one with no idles becomes FO4's empty marker, and MARKERS keeps
two earlier choices. A marker none of whose idles FO4 plays is the empty one too (spike.cell.idle).
A patrol point's pause time stays on the reference (placement.KEPT).

See: docs/fork/fo4_pipeline.md#audit-fixes
"""

from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import first_sub, walk, zstr

#: Fallout4.esm marker -> the FNV idles it plays the like of, by file name start (humans) or skeleton folder.
PLAYS = {
    'PatrolIdleMarker': ('2h', '3rdp_1hp_', '3rdp_2h', 'pointingallert', 'creatures\\ghoul', 'creatures\\deathclaw',
                         'creatures\\smspinebreaker'),
    'NPCStandingExamineIdleMarker': ('specialidle_swatting', 'specialidle_bitingnails', 'specialidle_scratchingself',
                                     'specialidle_pickingnose', 'specialidle_sneezing', 'picknose', 'lookingaround',
                                     'sirelaxed', 'ttpntrlarmscrossed', 'sleepyrubeyes', 'handsonhip', 'handsclasped',
                                     'mq05drliwatchesdad'),
    'NPCSmokeIdleMarker': ('smokingstanding',), 'NPCHandWarmingStanding': ('ms09specialidle_warmingup',),
    'NPCPushBroomSweep': ('sweeping', 'raking'), 'CowerLoopingIdleMarker': ('3rdp_cowering',),
    'DogmeatIdleMarkerSniffScratch': ('creatures\\dog',), 'NPCBartender': ('3rdp_specialidle_barkeeper',),
    'NPCHoldingClipboardIdleMarker': ('readpaperonhand',), 'NPCInspectWounded': ('doctorheal',),
    'NPCInstituteConsoleMediumHeight': ('scientistinspectterminal', 'ppurityterminaluse', 'useconsole', 'useintercom'),
    'NPCKneelWrenchHorizontal': ('3rdp_specialidle_repairingflr',), 'NPCWeldingLow': ('dlcpittweldinglow',),
    'NPCStandHammerVertical': ('3rdp_specialidle_repairwall',),
    'NPCStandHammerHorizontal': ('3rdp_specialidle_workbench',),
    'NPCStandDrinkCoffee': ('3rdp_specialidle_wowmanizing', 'drinkingstanding'),
}
#: FNV idle marker EditorID -> the Fallout4.esm marker it keeps, though most of its idles name another.
MARKERS = {'DefaultShopkeeperIdleMarker': 'NPCPushBroomSweep', 'MS16CowerIdleMarker': 'CowerLoopingIdleMarker'}
#: The Fallout4.esm idle marker with no idles, for an FNV one with none.
EMPTY = 'EmptyIdleMarker'


def plays(model: str) -> str:
    """FNV idle animation `model`'s creature skeleton folder, else its file name."""
    parts = model.lower().replace('/', '\\').split('\\')
    return '\\'.join(parts[:2]) if parts[0] == 'creatures' else parts[-1]


def stand_in(edid: str, idles: list) -> 'str | None':
    """The Fallout4.esm marker for FNV idle marker `edid` whose idles play `idles` (plays()), ties to the first;
    None when FO4 plays none of them."""
    if edid in MARKERS or not idles:
        return MARKERS.get(edid, EMPTY)
    named = [marker for idle in idles for marker, what in PLAYS.items() if idle.startswith(what)]
    return max(named, key=named.count) if named else None


def listed_idles(rec: dict) -> list:
    """The idle FormIDs FNV export record `rec` (a PACK or IDLM) lists (IDLA.Idle[i]), in order."""
    ids, i = [], 0
    while f'IDLA.Idle[{i}]' in rec:
        ids, i = ids + [int(rec[f'IDLA.Idle[{i}]'], 16)], i + 1
    return ids


def idle_lists(markers, idles) -> dict:
    """{IDLM FormID: [plays() of each listed idle]} of export IDLM and IDLE records."""
    anims = {int(rec['FormID'], 16): plays(rec.get('Model.MODL', '')) for rec in idles}
    return {int(rec['FormID'], 16): [anims.get(i, '') for i in listed_idles(rec)] for rec in markers}


class IdleMarkers:
    """The vanilla FO4 form standing in for each FNV idle marker."""

    def __init__(self, fo4: bytes, export_dir):
        """Stand-ins found in Fallout4.esm bytes `fo4` for the idle markers of FNV export `export_dir`."""
        wanted = {*PLAYS, *MARKERS.values(), EMPTY}
        self.vanilla = {}
        for rec, _ in walk(fo4, b'IDLM', b'FURN'):
            edid = zstr(first_sub(rec.body, b'EDID') or b'')
            if edid in wanted:
                self.vanilla[edid] = rec.form_id
        self.idles = idle_lists(export_records(export_dir, 'IDLM'), export_records(export_dir, 'IDLE'))

    def of(self, rec: dict) -> tuple:
        """(FO4 FormID or None; FO4 marker, else what it plays most) for FNV IDLM `rec`."""
        idles = self.idles.get(int(rec['FormID'], 16), [])
        edid = stand_in(rec.get('EditorID', ''), idles)
        return self.vanilla.get(edid), edid or max(idles, key=idles.count)
