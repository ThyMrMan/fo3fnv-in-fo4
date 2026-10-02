"""FO3/FNV game settings as the game sees them: the exe's defaults, then the masters' GMSTs, then this plugin's.

The defaults are each exe's own table (tes4_export/<game>_engine_settings.json,
read out of Fallout3.exe and FalloutNV.exe); a plugin's GMST overrides one, as
in game. Fallout3.esm sets `fAVDNPCHealthLevelMult` to 5 over the exe's 20.

See: docs/commentary/tes5_import_falloutnv_actors.md#game-settings
"""

import json

from ..actors.combat_style import game_settings
from ..character_data_falloutnv import ENGINE_SETTINGS, game_of
from .world_falloutnv import is_fallout_source

#: Setting name -> value for this run's FO3/FNV source; empty for any other.
_SETTINGS: dict = {}


def load_fallout_settings(by_type: dict, master_export: dict, export_dir: str) -> None:
    """Load the effective settings of an FO3/FNV source, once per run."""
    _SETTINGS.clear()
    if not is_fallout_source():
        return
    with open(ENGINE_SETTINGS[game_of(export_dir)], encoding='utf-8') as handle:
        defaults = json.load(handle)['settings']
    _SETTINGS.update(game_settings(by_type, master_export, defaults)[0])


def setting(name: str) -> float:
    """One loaded setting's value; KeyError for a name the game does not have."""
    return _SETTINGS[name]
