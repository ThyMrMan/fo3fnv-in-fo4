"""The route each creature skeleton folder no hand rule names takes to Fallout 4, first that works:

1. the rule of a ruled folder whose skeleton has the same bones (a stats, fnv or item rule);
2. an own rig derived from its files (rig.derive);
3. a stand-in by its FNV creature type (DATA.CreatureType), when it has a skeleton but no rig can be derived;
4. an unseen speaker with its model beside it (talking_machines), when it has no skeleton.

Each folder's route is counted in the build log (`creature route (<how>): <folder>`).

See: docs/fork/fo4_auto_rig_plan.md#order
"""

from dataclasses import dataclass
from pathlib import Path

from fo4_import.nif.creature import PAIRS
from fo4_import.nif.file import block_names
from fo4_import.pipeline.export_index import asset_root
from fo4_import.rig.derive import derived
from fo4_import.rig.records import fnv_parts
from fo4_import.rig.table import rigs
from fo4_import.spike.replacements import BASE, Replacement


def _target(edid: str, mode: str) -> Replacement:
    """A route's Fallout4.esm target `edid` in `mode`."""
    return Replacement(BASE, edid, mode, category='creature', origin='route')


#: A derived rig's NPC (as every hand rig's).
RIG = _target('EncMolerat01Template', 'rig')
#: Stand-ins by FNV creature type: 4 super mutant, 5 feral ghoul, 6 robot; any other (animals, insects) ANIMAL.
BY_TYPE = {4: _target('EncSuperMutantTemplate', 'stats'), 5: _target('encFeralGhoul01Template', 'stats'),
           6: _target('EncProtectron01Template', 'stats')}
ANIMAL = _target('EncMolerat01Template', 'stats')
#: A creature with no skeleton: an unseen speaker that never moves, its model placed beside it.
STILL = _target('EncProtectron01Template', 'speaker')
#: Every target a route may name, keyed as Creatures indexes its targets.
TARGETS = {f'route {e.edid} {e.mode}': e for e in (RIG, *BY_TYPE.values(), ANIMAL, STILL)}
#: The rule modes a same-skeleton folder may share (a rig or speaker rule is its own folder's files).
SHARED_MODES = ('stats', 'fnv', 'item')
SKELETON = 'skeleton.nif'


@dataclass(frozen=True)
class Route:
    """A folder's entry, how it was found, the ruled folder it shares (same skeleton) and its derived rig."""
    entry: Replacement
    how: str
    alias: str = ''
    rig: object = None


class Routes:
    """The routes of one build's unruled creature folders, worked out once each on first use."""

    def __init__(self, export_dir: Path, rules: dict, members: dict, people, counts):
        """`members`: {folder: [creatures]}; `people`: creatures -> (talks, armed)."""
        self.export_dir, self.rules, self.members, self.people, self.counts = export_dir, rules, members, people, counts
        self.made, self.bones = {}, {}

    def of(self, folder: str) -> 'Route | None':
        """`folder`'s route; None for a ruled folder or one no creature's own model is in."""
        if folder in self.rules or folder not in self.members:
            return None
        if folder not in self.made:
            self.made[folder] = route = self._find(folder)
            self.counts[f'creature route ({route.how}): {folder}'] += 1
        return self.made[folder]

    def rig(self, folder: str):
        """`folder`'s own rig: the hand table's, else its derived one; None."""
        route = self.of(folder)
        return rigs().get(folder) or (route.rig if route else None)

    def pair(self, folder: str):
        """`folder`'s nif.creature Pair, else its same-skeleton folder's."""
        route = self.of(folder)
        return PAIRS.get(folder) or (PAIRS.get(route.alias) if route else None)

    def _find(self, folder: str) -> Route:
        """The first route that works for unruled `folder` (the module notes)."""
        skeleton = self._skeleton(folder)
        if not skeleton.is_file():
            return Route(STILL, 'no skeleton: an unseen speaker')
        root = skeleton.parent
        same = self._same_skeleton(skeleton)
        if same:
            return Route(self.rules[same], f'same skeleton as {same}', same)
        rig, why = derived(folder, root, fnv_parts(folder), self.people(self.members[folder]))
        if rig is not None:
            return Route(RIG, 'own rig derived from its files', rig=rig)
        kind = int(self.members[folder][0].get('DATA.CreatureType', 0) or 0)
        return Route(BY_TYPE.get(kind, ANIMAL), f'stand-in by creature type {kind} ({why})')

    def _same_skeleton(self, skeleton: Path) -> str:
        """The first ruled folder (SHARED_MODES) whose skeleton has `skeleton`'s bone names; ''."""
        names = self._names(skeleton)
        for folder, entry in sorted(self.rules.items()):
            other = self._skeleton(folder)
            if entry.mode in SHARED_MODES and other.is_file() and self._names(other) == names:
                return folder
        return ''

    def _skeleton(self, folder: str) -> Path:
        """`folder`'s skeleton.nif from the first export layer holding the file."""
        return Path(asset_root(self.export_dir, 'meshes', folder, SKELETON))

    def _names(self, skeleton: Path) -> frozenset:
        """The node names of skeleton NIF `skeleton`, read once."""
        if skeleton not in self.bones:
            self.bones[skeleton] = frozenset(block_names(skeleton.read_bytes(), 'NiNode'))
        return self.bones[skeleton]
