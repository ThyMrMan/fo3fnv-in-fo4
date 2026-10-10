"""FO3/FNV's character system on LevelUpMenuEx, for the cell spike.

LevelUpMenuEx (PRKF) reads `Data\\PRKF\\*.ini`: form lists of its skills and
perks (`Plugin.esp|<hex id>`, split at `|`), points per level, and whether
FO4's perk chart is off. The plugin gets those lists, the game's traits as
perks (no effects yet), the skills' FNV names and descriptions over the helper
plugin's actor values, and a quest running TES4_CharacterRules: it opens FO4's
SPECIAL menu and LevelUpMenuEx's tag and trait menus for the converted
scripts' CharacterMenu events, sets starting skills from SPECIAL and tops up
each level's points to the game's rates.

See: docs/fork/research/fo4_target.md#decisions
"""

from pathlib import Path

from fo4_import.base.support_records import pack_avif, pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.helpers_plugin import EDID_PREFIX, actor_value_form, form_id
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from script_convert.constants import FALLOUT4_ACTOR_VALUE_IDS, FALLOUT4_HELPER_QUESTS
from tes5_import.base.text_reader import parse_export_file

RULES_SCRIPT = 'TES4_CharacterRules'
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
#: FO3/FNV actor value FormIDs: index + this.
FNV_AVIF_BASE = 0x490
INI_VERSION = 3


def _settings(export_dir: Path) -> dict:
    """{GMST EditorID: value} of the game's settings."""
    return {r.get('EditorID'): r.get('DATA.Value') for r in parse_export_file(str(export_dir / 'GMST.txt'))}


def _skill_texts(builder, export_dir: Path, skills: list, helper_index: int) -> None:
    """Override the helper plugin's skill actor values with the game's name and description."""
    avifs = {int(r['FormID'], 16): r for r in parse_export_file(str(export_dir / 'AVIF.txt'))}
    for i, name in enumerate(C.FNV_AV_NAMES):
        if name.replace(' ', '') in skills and FNV_AVIF_BASE + i in avifs:
            rec = avifs[FNV_AVIF_BASE + i]
            fid = actor_value_form(name.replace(' ', ''), helper_index)
            builder.writer.add_record('AVIF', pack_avif(fid, EDID_PREFIX + name.replace(' ', ''), rec.get('FULL', name),
                                                        rec.get('DESC', '')))


def _list(builder, edid: str, forms: list) -> int:
    """Write a form list of `forms`; its FormID."""
    fid = builder.new_id(f'FLST {edid}')
    builder.writer.add_record('FLST', R.pack_flst(fid, edid, forms))
    return fid


def _traits(builder, export_dir: Path) -> list:
    """The game's traits as FO4 trait perks (name and description; their effects are a later step)."""
    out = []
    for rec in parse_export_file(str(export_dir / 'PERK.txt')):
        if rec.get('DATA.Trait') == '1' and rec.get('DATA.Playable') == '1':
            fid = builder.fnv_id(rec['FormID'])
            builder.writer.add_record('PERK', R.pack_perk(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''),
                                                          rec.get('DESC', ''), True))
            out.append(fid)
    builder.counts['trait perks'] = len(out)
    return out


def build(builder, export_dir: Path, data_dir: Path, plugin: str, helper_index: int) -> None:
    """Write the character-rule records into `builder`'s plugin `plugin` and LevelUpMenuEx's INI for it."""
    game = export_dir.name
    governing = GOVERNING[game]
    skills = sorted({s for group in governing for s in group}, key=lambda s: C.FNV_AV_NAMES.index(
        next(n for n in C.FNV_AV_NAMES if n.replace(' ', '') == s)))
    settings = _settings(export_dir)
    _skill_texts(builder, export_dir, skills, helper_index)
    skill_list = _list(builder, 'FNV_Skills', [actor_value_form(s, helper_index) for s in skills])
    governed = [_list(builder, f'FNV_GovernedBy{stat}', [actor_value_form(s, helper_index) for s in group])
                for stat, group in zip(SPECIAL, governing)]
    objects = {'TES4CharacterEvents': form_id(FALLOUT4_HELPER_QUESTS['TES4_CharacterEvents'], helper_index),
               'SpecialStats': _list(builder, 'FNV_SpecialStats', [FALLOUT4_ACTOR_VALUE_IDS[s] for s in SPECIAL]),
               'GovernedSkills': _list(builder, 'FNV_GovernedSkills', governed),
               'Traits': _list(builder, 'FNV_Traits', _traits(builder, export_dir))}
    per_int, per_perk = RATES[game]
    values = {'SkillPointsBase': ('int', SKILL_POINTS_BASE), 'SkillPointsPerIntelligence': ('float', per_int),
              'LevelsPerPerk': ('int', per_perk), 'TagBonus': ('int', int(float(settings['fAVDTagSkillBonus']))),
              'TraitCount': ('int', int(settings.get('iTraitMenuMaxNumTraits', 0))),
              'SkillBase': ('float', float(settings['fAVDSkillBarterBase']))}
    quest = builder.new_id('QUST FNV_CharacterRules')
    builder.writer.add_record('QUST', pack_script_quest(
        quest, 'FNV_CharacterRules', quest_fragments('', [], scripts=[(RULES_SCRIPT, objects, values)])))
    builder.scripts.used.append(RULES_SCRIPT)
    perks = _list(builder, 'FNV_Perks', [])
    write_ini(data_dir / 'PRKF' / f'{Path(plugin).stem}.ini', plugin, perks, skill_list)


def write_ini(path: Path, plugin: str, perks: int, skills: int) -> None:
    """LevelUpMenuEx's INI: our perk and skill lists, FO4's perk chart off, points per level left to the rules."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[Main]\nINIVersion={INI_VERSION}\ndisableVanillaPerks=1\noverrideMaxSkillsValue=100\n'
                    f'PerksList={plugin}|{perks & 0xFFFFFF:X}\nSkillsList={plugin}|{skills & 0xFFFFFF:X}\n'
                    'PPPerLevel=0\nSPPerLevel=0\n', encoding='ascii')
