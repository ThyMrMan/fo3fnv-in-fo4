"""FO3/FNV's character system, for the cell spike.

The plugin gets the skill, SPECIAL, perk and trait lists, the skills' FNV names
and descriptions over the helper plugin's actor values, and a quest running
F3NV_CharacterRules and our level-up (F3NV_LevelUp, its tables): it opens FO4's
SPECIAL menu and our level-up menu as the tag and trait menus for the converted
scripts' CharacterMenu events, sets starting skills from SPECIAL and gives each
level's points at the game's rates. The game plugin also gets the level-up
options' MCM page; LevelUpMenuEx's INI an older build wrote is deleted.

See: docs/fork/research/fo4_target.md#decisions, docs/fork/fo4_level_up_plan.md#dropped
"""

from pathlib import Path

from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_avif, pack_gmst, pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.helpers_plugin import EDID_PREFIX, actor_value_form, form_id
from fo4_import.level_up import options
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.level_up import SCRIPT as LEVEL_UP_SCRIPT, TABLE_SCRIPT, av_records, skill_table, table_properties
from fo4_import.spike.pipboy_tabs import tab_quest
from fo4_import.pipeline.export_index import export_records, root_export
from script_convert.constants import FALLOUT4_ACTOR_VALUE_IDS, FALLOUT4_HELPER_QUESTS

RULES_SCRIPT = 'F3NV_CharacterRules'
SPECIAL = ('Strength', 'Perception', 'Endurance', 'Charisma', 'Intelligence', 'Agility', 'Luck')
#: Per game: the skills each SPECIAL stat governs (Fallout wiki, "Fallout: New Vegas skills" / "Fallout 3 skills").
GOVERNING = {
    'FalloutNV.esm': (('MeleeWeapons',), ('EnergyWeapons', 'Explosives', 'Lockpick'), ('Survival', 'Unarmed'),
                      ('Barter', 'Speech'), ('Medicine', 'Repair', 'Science'), ('Guns', 'Sneak'), ()),
    'Fallout3.esm': (('MeleeWeapons',), ('EnergyWeapons', 'Explosives', 'Lockpick'), ('BigGuns', 'Unarmed'),
                     ('Barter', 'Speech'), ('Medicine', 'Repair', 'Science'), ('SmallGuns', 'Sneak'), ()),
}
#: Per game: (skill points per Intelligence point, levels per perk). Both give 10 + those per level.
RATES = {'FalloutNV.esm': (0.5, 2), 'Fallout3.esm': (1.0, 1)}
SKILL_POINTS_BASE = 10
#: A DLC's level-up table quest: its FormID key.
TABLE_KEY = 'QUST FNV_LevelUpTable'
#: LevelUpMenuEx's INI folder, where an older build wrote <plugin stem>.ini.
PRKF_INI_DIR = 'PRKF'
#: Fallout4.esm's SPECIAL menu total (28) and FO3/FNV's: 40, ShowSPECIALBookMenu's default.
SPECIAL_POINTS_SETTING, SPECIAL_POINTS_ID, SPECIAL_POINTS = 'uSPECIALPoints', 0x00078744, 40


def _settings(export_dir: Path) -> dict:
    """{GMST EditorID: value} of the game's settings."""
    return {r.get('EditorID'): r.get('DATA.Value') for r in export_records(export_dir, 'GMST')}


def _skill_texts(builder, avifs: dict, skills: list, helper_index: int) -> None:
    """Override the helper plugin's skill actor values with the game's name and description (`avifs`, level_up's
    av_records)."""
    for i, name in enumerate(C.FNV_AV_NAMES):
        if name.replace(' ', '') in skills and i in avifs:
            rec = avifs[i]
            fid = actor_value_form(name.replace(' ', ''), helper_index)
            builder.writer.add_record('AVIF', pack_avif(fid, EDID_PREFIX + name.replace(' ', ''), rec.get('FULL', name),
                                                        rec.get('DESC', '')))


def _list(builder, edid: str, forms: list) -> int:
    """Write a form list of `forms`; its FormID."""
    fid = builder.new_id(f'FLST {edid}')
    builder.writer.add_record('FLST', R.pack_flst(fid, edid, forms))
    return fid


def build(builder, export_dir: Path, data_dir: Path, plugin: str, helper_index: int) -> None:
    """Write the character-rule records into `builder`'s plugin `plugin` (the rules quest also carries our level-up
    state, level_up), the Pip-Boy's SKILLS tab and, for the game plugin only, the level-up options' MCM page (a DLC's
    perks reach the game's list by its form list merge, its own tables by _table)."""
    game = root_export(export_dir).name
    governing = GOVERNING[game]
    skills = sorted({s for group in governing for s in group}, key=lambda s: C.FNV_AV_NAMES.index(
        next(n for n in C.FNV_AV_NAMES if n.replace(' ', '') == s)))
    settings, avifs = _settings(export_dir), av_records(export_dir)
    _skill_texts(builder, avifs, skills, helper_index)
    skill_forms = [actor_value_form(s, helper_index) for s in skills]
    special_forms = [FALLOUT4_ACTOR_VALUE_IDS[s] for s in SPECIAL]
    skill_list = _list(builder, 'FNV_Skills', skill_forms)
    governed = [_list(builder, f'FNV_GovernedBy{stat}', [actor_value_form(s, helper_index) for s in group])
                for stat, group in zip(SPECIAL, governing)]
    objects = {'TES4CharacterEvents': form_id(FALLOUT4_HELPER_QUESTS['F3NV_CharacterEvents'], helper_index),
               'SpecialStats': _list(builder, 'FNV_SpecialStats', special_forms),
               'GovernedSkills': _list(builder, 'FNV_GovernedSkills', governed),
               'Traits': _list(builder, 'FNV_Traits', builder.perks.traits())}
    per_int, per_perk = RATES[game]
    values = {'SkillPointsBase': ('int', SKILL_POINTS_BASE), 'SkillPointsPerIntelligence': ('float', per_int),
              'LevelsPerPerk': ('int', per_perk), 'TagBonus': ('int', int(float(settings['fAVDTagSkillBonus']))),
              'TraitCount': ('int', int(settings.get('iTraitMenuMaxNumTraits', 0))),
              'SkillBase': ('float', float(settings['fAVDSkillBarterBase'])), **stage_properties(builder.perks)}
    tables = _list(builder, 'FNV_LevelUpTables', [])
    level_up = (LEVEL_UP_SCRIPT, {'Perks': _list(builder, 'FNV_Perks', builder.perks.playable()), 'Skills': skill_list,
                                  'Specials': objects['SpecialStats'], 'Events': objects['TES4CharacterEvents'],
                                  'Tables': tables}, skill_table(avifs, skills))
    quest = builder.new_id('QUST FNV_CharacterRules')
    table = (TABLE_SCRIPT, {'Tables': tables}, table_properties(builder, avifs, special_forms + skill_forms))
    builder.writer.add_record('QUST', pack_script_quest(quest, 'FNV_CharacterRules', quest_fragments(
        '', [], scripts=[(RULES_SCRIPT, objects, values), level_up, *_table(builder, quest, table)])))
    builder.scripts.used.extend((RULES_SCRIPT, LEVEL_UP_SCRIPT, TABLE_SCRIPT))
    builder.writer.add_record('GMST', pack_gmst(SPECIAL_POINTS_ID, SPECIAL_POINTS_SETTING, SPECIAL_POINTS))
    if not builder.built:
        builder.counts['MCM page files'] += options.install(data_dir, plugin, quest)
        builder.counts["LevelUpMenuEx INI deleted (an older build's)"] += drop_prkf_ini(data_dir, plugin)
    tab_quest(builder, 'SKILLS', skill_list)


def _table(builder, rules: int, table: tuple) -> list:
    """`table` (script, objects, values) as a script of the rules quest `rules` in the game build; a DLC's (`rules` a
    master's) on a start-game quest of its own, written when it lists a perk or trait.
    See: docs/fork/fo4_level_up_plan.md#tables
    """
    if rules >> 24 == builder.writer.own_index:
        return [table]
    if table[2]['RankForms'][1] or table[2]['TraitForms'][1]:
        edid = f'FNV_LevelUpTable_{plugin_stem(builder.export_dir)}'
        builder.writer.add_record('QUST', pack_script_quest(builder.new_id(TABLE_KEY, key=TABLE_KEY), edid,
                                                            quest_fragments('', [], scripts=[table])))
    return []


def stage_properties(perks) -> dict:
    """The rules' StagePerks, StageQuests, StageIndexes and StageScripts (each quest's fragment script): `perks`'
    quest stage effects, one per index.
    See: docs/fork/fo4_pipeline.md#intense-training
    """
    ranks, quests, stages, scripts = zip(*perks.stage_effects) if perks.stage_effects else ((), (), (), ())
    return {'StagePerks': ('objects', list(ranks)), 'StageQuests': ('objects', list(quests)),
            'StageIndexes': ('ints', list(stages)), 'StageScripts': ('strings', list(scripts))}


def drop_prkf_ini(data_dir: Path, plugin: str) -> int:
    """Delete LevelUpMenuEx's INI an older build wrote for `plugin` (Data/PRKF/<stem>.ini), and its folder once
    empty; 1 if one was deleted.
    See: docs/fork/fo4_level_up_plan.md#dropped
    """
    folder = Path(data_dir) / PRKF_INI_DIR
    old = folder / f'{Path(plugin).stem}.ini'
    if not old.is_file():
        return 0
    old.unlink()
    if not any(folder.iterdir()):
        folder.rmdir()
    return 1
