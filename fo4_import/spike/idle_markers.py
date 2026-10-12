"""FNV idle markers placed as the nearest vanilla FO4 marker, for the cell spike.

FNV's idle marker (IDLM) names FNV idle animations, which FO4 does not
have. A placed one becomes a reference to the Fallout4.esm form doing the
same (MARKERS): FO4's patrol marker for FNV's patrol and guard points, its
hand-warming furniture at a fire barrel, its push broom for sweeping and
raking, and so on. A marker with no counterpart is left out and counted.
A patrol point's pause time stays on the reference (placement.KEPT).

See: docs/fork/fo4_pipeline.md#packages
"""

from tes5_import.base.tes5_reader import first_sub, walk

#: FNV idle marker EditorID -> the Fallout4.esm IDLM or FURN in its place.
MARKERS = {
    'DefaultHumanPatrolIdleMarker': 'PatrolIdleMarker', 'PatrolScanAreaIdleMarker': 'PatrolIdleMarker',
    'DefaultGuardMarker': 'PatrolIdleMarker', 'DefaultHumanIdleMarker': 'NPCStandingExamineIdleMarker',
    'DefaultSmokingIdleMarker': 'NPCSmokeIdleMarker', 'DefaultFireBarrelIdleMarker': 'NPCHandWarmingStanding',
    'DefaultShopkeeperIdleMarker': 'NPCPushBroomSweep', 'DefaultRakingMarker': 'NPCPushBroomSweep',
    'MS17AgathaSweepsIdle': 'NPCPushBroomSweep', 'GobSweep': 'NPCPushBroomSweep',
    'MS16CowerIdleMarker': 'CowerLoopingIdleMarker', 'DogIdleMarker': 'DogmeatIdleMarkerSniffScratch',
    'DogSitIdleMarker': 'DogmeatIdleMarkerSniffScratch',
}


class IdleMarkers:
    """The vanilla FO4 form standing in for each FNV idle marker."""

    def __init__(self, fo4: bytes):
        """Find MARKERS' targets in Fallout4.esm bytes `fo4`."""
        wanted = set(MARKERS.values())
        self.vanilla = {}
        for rec, _ in walk(fo4, b'IDLM', b'FURN'):
            edid = (first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode()
            if edid in wanted:
                self.vanilla[edid] = rec.form_id

    def of(self, rec: dict) -> 'int | None':
        """Fallout4.esm FormID placed for FNV idle marker `rec`; None if none."""
        return self.vanilla.get(MARKERS.get(rec.get('EditorID', '')))
