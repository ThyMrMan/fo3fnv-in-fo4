"""CleanroomUI.esl: Cleanroom UI's own plugin, written with the game build until the converter takes that repo.

One start-game quest at CLEANROOM_HOLDER carrying F3NV_LevelUpHolder, which every level-up host announces itself
to, so F3NV_LevelUp.Get() finds the running one. The bytes are the ones Cleanroom UI's crui/plugin.py writes, so
both copies are one file to the game.

See: docs/fork/fo4_level_up_plan.md#plugin
"""

from pathlib import Path

from fo4_import.base.support_records import pack_script_quest
from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import FO4PluginWriter
from script_convert.constants import CLEANROOM_HOLDER, CLEANROOM_PLUGIN

HOLDER_EDID, HOLDER_SCRIPT = 'CleanroomUI_LevelUpHolder', 'F3NV_LevelUpHolder'
AUTHOR, DESCRIPTION = 'Cleanroom UI', 'Cleanroom UI: shared forms of the menu framework'


def build(data_dir: Path) -> Path:
    """Write <data_dir>/CleanroomUI.esl, a light master with no masters; its path."""
    writer = FO4PluginWriter(masters=[], is_esm=True, is_esl=True, author=AUTHOR, description=DESCRIPTION)
    writer.add_record('QUST', pack_script_quest(CLEANROOM_HOLDER, HOLDER_EDID, object_scripts([(HOLDER_SCRIPT, {}, {})])))
    writer.next_object_id = CLEANROOM_HOLDER + 1
    out = Path(data_dir) / CLEANROOM_PLUGIN
    out.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(out))
    return out
