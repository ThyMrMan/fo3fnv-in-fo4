"""The rig table (data/creature_rigs.json): per FNV skeleton folder, what its own-rig conversion needs that FNV's
files do not say.

See: docs/fork/fo4_own_rig.md#table
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'creature_rigs.json'
#: The bone FO4 hangs equip slot 0's gun on; another slot's is WEAPON<slot> (weapon_node).
WEAPON = 'WEAPON'


def weapon_node(slot: int) -> str:
    """The node equip slot `slot`'s gun hangs on (the race's ZNAM for it)."""
    return WEAPON if slot == 0 else f'{WEAPON}{slot}'


@dataclass(frozen=True)
class Rig:
    """One creature's entry: its folder, project name, template records and files, clips, attacks and bones, and its
    guns: (ranged clip role, equip slot, bones whose subtrees the clip plays on, FNV node they fire from), the slot
    an EQUP EditorID until records.with_slots makes it the index in its race's slots, adding `slots` (EQUP FormIDs)
    its template race lacks."""
    folder: str
    project: str
    template: dict
    clips: dict
    attacks: dict
    parts: dict
    default_part: str
    pose_bones: tuple
    guns: tuple = ()
    slots: tuple = ()

    @property
    def fire_nodes(self) -> dict:
        """{equip slot: the FNV node its guns fire from}."""
        return {slot: node for _, slot, _, node in self.guns}

    @property
    def actor_dir(self) -> str:
        """Its FO4 folder under Meshes (`Actors\\FNVGecko`)."""
        return f'Actors\\{self.project}'

    def path(self, *parts: str) -> str:
        """A path in its folder (`Actors\\FNVGecko\\Behaviors\\...`)."""
        return '\\'.join((self.actor_dir,) + parts)


@lru_cache(maxsize=1)
def rigs() -> dict:
    """{skeleton folder: Rig} of the shipped table."""
    raw = json.loads(TABLE.read_text(encoding='utf-8'))
    return {folder: Rig(folder=folder, project=e['project'], template=e['template'], clips=e['clips'],
                        attacks=e['attacks'], parts=e['parts'], default_part=e['default_part'],
                        pose_bones=tuple(e['pose_bones']),
                        guns=tuple((role, slot, tuple(bones), node)
                                   for role, (slot, bones, node) in e.get('guns', {}).items()))
            for folder, e in raw.items() if not folder.startswith('_')}
