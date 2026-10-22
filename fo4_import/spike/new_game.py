"""The FO3/FNV opening on Fallout 4: one start-game quest running TES4_NewGame.

Fallout 4's New Game runs MQ101 stage 0 (its intro movie, then the character
creation state). TES4_NewGame waits that out, undoes it with vanilla's own
calls, stops Fallout 4's opening quests and sets the source game's first
stage (START): FNV's VCG00 stage 0 moves the player to Doc Mitchell's and
plays FNV's intro. A coc from the main menu skips MQ101 stage 0, so the
source game waits: stage 10 (`setstage FNV_NewGame 10`) starts it by hand.
Nothing in Fallout4.esm is overridden.

See: docs/fork/fo4_pipeline.md#new-game
"""

from pathlib import Path

from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.character import SPECIAL
from script_convert.constants import FALLOUT4_ACTOR_VALUE_IDS

#: Source plugin -> (the quest whose stage opens its game, that stage).
START = {'FalloutNV.esm': ('VCG00', 0)}
#: Fallout4.esm forms the script is given: MQ101, MQ102 (MQ03QuestScript's quest), TimeScale, the mirror imods.
MQ101, MQ102, TIME_SCALE, CAMERA_IMOD, MIRROR_IMOD = 0x1ED86, 0x1CC2A, 0x3A, 0x1A71FC, 0x1E9902
#: Fallout 4's opening quests besides MQ101: SanctuaryHills, Radio, TVStation, PlayerComments, Vault111.
OPENING_QUESTS = (0xC3309, 0xBA4F3, 0xBA4F2, 0xF03D6, 0xD34DC)
SITE, SCRIPT, PLAYER = 'FNV new game quest', 'TES4_NewGame', 0x14
#: The quest's Player alias (its only one, forced to the player) and its script, which traces player hits on load.
PLAYER_ALIAS, ALIAS_SCRIPT = 0, 'TES4_NewGamePlayer'
#: The source game's player base record.
PLAYER_BASE = 0x7
#: The stage starting the source game by hand (setstage FNV_NewGame 10), its fragment script and function.
START_BY_HAND, FRAGMENTS, FRAGMENT = 10, 'TES4_NewGameStart', 'Fragment_Stage_0010_Item_00'


def build(builder, export_dir: Path, quests: dict) -> None:
    """Write the new game quest when the source game's opening quest is in `quests` {EditorID: FO4 FormID}."""
    quest, stage = START.get(export_dir.name, (None, 0))
    if quest not in quests:
        return
    fid = builder.writer.derive_formid(SITE, export_dir.name)
    props = {'MQ101': MQ101, 'MQ102': MQ102, 'TimeScale': TIME_SCALE, 'StartQuest': quests[quest],
             'CharGenCameraImod': CAMERA_IMOD, 'CharGenMirrorImod': MIRROR_IMOD, 'SkillGates': builder.perks.gates}
    values = {'OpeningQuests': ('objects', list(OPENING_QUESTS)), 'StartStage': ('int', stage),
              'Special': ('objects', [FALLOUT4_ACTOR_VALUE_IDS[s] for s in SPECIAL]),
              'SpecialStart': ('floats', start_special(export_dir))}
    vmad = quest_fragments(FRAGMENTS, [(START_BY_HAND, 0, FRAGMENT)],
                           aliases=[(PLAYER_ALIAS, fid, [(ALIAS_SCRIPT, {}, {})])], scripts=[(SCRIPT, props, values)])
    builder.writer.add_record('QUST', R.pack_qust(fid, 'FNV_NewGame', '', 0, [START_BY_HAND], 'Player', PLAYER, vmad))
    builder.scripts.used.append(FRAGMENTS)
    builder.counts['QUST (new game)'] += 1


def start_special(export_dir: Path) -> list:
    """The source game's player record SPECIAL values, in SPECIAL's order."""
    player = next(r for r in export_records(export_dir, 'NPC_') if int(r['FormID'], 16) == PLAYER_BASE)
    return [float(player[f'DATA.{stat}']) for stat in SPECIAL]
