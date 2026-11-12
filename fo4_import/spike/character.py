"""FO3/FNV's character system on LevelUpMenuEx, for the cell spike.

LevelUpMenuEx (PRKF) reads `Data\\PRKF\\*.ini`: form lists of its skills and
perks (`Plugin.esp|<hex id>`, split at `|`), points per level, and whether
FO4's perk chart is off. The plugin gets those lists, the game's traits
(perks.Perks), the skills' FNV names and descriptions over the helper
plugin's actor values, and a quest running F3NV_CharacterRules: it opens FO4's
SPECIAL menu and LevelUpMenuEx's tag and trait menus for the converted
scripts' CharacterMenu events, sets starting skills from SPECIAL and tops up
each level's points to the game's rates.

See: docs/fork/research/fo4_target.md#decisions
"""

from pathlib import Path

from fo4_import.base.support_records import pack_avif, pack_gmst, pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.helpers_plugin import EDID_PREFIX, actor_value_form, form_id
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.level_up import SCRIPT as LEVEL_UP_SCRIPT, av_records, menu_properties as level_up_properties
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
INI_VERSION = 3
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
    state, level_up), the Pip-Boy's SKILLS tab and, for the game plugin only, LevelUpMenuEx's INI (a DLC's perks
    reach the game's list by its form list merge)."""
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
    perks = _list(builder, 'FNV_Perks', builder.perks.playable())
    level_up = ({'Perks': perks, 'Skills': skill_list, 'Specials': objects['SpecialStats']},
                level_up_properties(builder, avifs, special_forms + skill_forms, skills))
    quest = builder.new_id('QUST FNV_CharacterRules')
    builder.writer.add_record('QUST', pack_script_quest(quest, 'FNV_CharacterRules', quest_fragments(
        '', [], scripts=[(RULES_SCRIPT, objects, values), (LEVEL_UP_SCRIPT, *level_up)])))
    builder.scripts.used.extend((RULES_SCRIPT, LEVEL_UP_SCRIPT))
    builder.writer.add_record('GMST', pack_gmst(SPECIAL_POINTS_ID, SPECIAL_POINTS_SETTING, SPECIAL_POINTS))
    if not builder.built:
        write_ini(data_dir / 'PRKF' / f'{Path(plugin).stem}.ini', plugin, perks, skill_list)
    tab_quest(builder, 'SKILLS', skill_list)


def stage_properties(perks) -> dict:
    """The rules' StagePerks, StageQuests, StageIndexes and StageScripts (each quest's fragment script): `perks`'
    quest stage effects, one per index.
    See: docs/fork/fo4_pipeline.md#intense-training
    """
    ranks, quests, stages, scripts = zip(*perks.stage_effects) if perks.stage_effects else ((), (), (), ())
    return {'StagePerks': ('objects', list(ranks)), 'StageQuests': ('objects', list(quests)),
            'StageIndexes': ('ints', list(stages)), 'StageScripts': ('strings', list(scripts))}


def write_ini(path: Path, plugin: str, perks: int, skills: int) -> None:
    """LevelUpMenuEx's INI: our perk and skill lists, FO4's perk chart off, points per level left to the rules."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[Main]\nINIVersion={INI_VERSION}\ndisableVanillaPerks=1\noverrideMaxSkillsValue=100\n'
                    f'PerksList={plugin}|{perks & 0xFFFFFF:X}\nSkillsList={plugin}|{skills & 0xFFFFFF:X}\n'
                    'PPPerLevel=0\nSPPerLevel=0\n', encoding='ascii')
