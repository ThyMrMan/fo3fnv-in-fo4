"""FNV crafting as Fallout 4's: workbench furniture, keywords and constructible objects.

FNV opens a crafting menu from an activator's script (`ShowRecipeMenu
<category>`) and lists the recipes (RCPE) of that category. FO4 crafts at
workbench furniture: a COBJ lists its components (FVPA), what it makes, the
workbench keyword (BNAM) whose furniture offers it and the recipe filter
keywords (FNAM) that make the menu's tabs. So:

- a recipe category with a station (STATIONS) becomes a workbench keyword;
- an FNV activator whose script opens that category's menu becomes a copy of
  the vanilla station furniture (its entry markers, workbench data and
  script) with FNV's name, model and bounds and the category's keyword in
  place of vanilla's, so the FNV recipes show at FNV stations only. The
  activator's script is not attached: its only work was opening the menu;
- each sub-category becomes a recipe filter keyword (the menu tab, FNV's name);
- each recipe of such a category becomes a COBJ on FNV's FormID: its
  ingredients as components, what it makes, and as conditions on the player
  FNV's skill requirement (the helper plugin's skill actor value) and its
  GetHasNote conditions (the note's book in inventory);
- a COBJ makes one item, so a recipe with several outputs makes a token (a
  misc item named for the recipe) instead, and its outputs become a leveled
  list giving every entry. One start-game quest's player alias runs
  F3NV_RecipeOutputs, which swaps each token as it arrives for its list:
  vanilla's player-alias inventory filter (BoS301PlayerAliasScript).
"""

import re
import struct
from pathlib import Path

from fo4_import.base.vmad import quest_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.conditions import FO4, fnv_av_name, parse
from fo4_import.spike.station_spot import cell_of, spot, triangles_by_cell
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV recipe category -> (vanilla workbench furniture it is built as, its workbench keyword); benches as chem stations.
STATIONS = {'CampfireRecipes': ('WorkbenchCookingFire', 0x102152),
            'WorkbenchRecipes': ('WorkbenchChemistryA', 0x102158),
            'ReloadingBenchRecipes': ('WorkbenchChemistryA', 0x102158)}
#: KYWD TNAM types: none (a workbench keyword), recipe filter (a crafting menu tab).
PLAIN, RECIPE_FILTER = 0, 9
#: Condition comparison >= and the function a skill requirement and a note test become.
AT_LEAST = 0x60
GET_VALUE, GET_ITEM_COUNT = FO4.index('GetValue'), FO4.index('GetItemCount')
#: FO4 HasPerk, and a CTDA's comparison bits.
HAS_PERK, COMPARE = FO4.index('HasPerk'), 0xE0
#: Template subrecords a station replaces with FNV's or drops (MODT names the vanilla model's textures).
REPLACED = frozenset({b'EDID', b'OBND', b'FULL', b'MODL', b'MODT', b'KWDA'})
_MENU = re.compile(r'showrecipemenu\s+(\w+)', re.IGNORECASE)
#: FormID sites: a recipe's token and outputs list (keyed by its FNV FormID), the quest and its lists (by name).
TOKEN_SITE, OUTPUTS_SITE, QUEST_SITE = 'FNV recipe token', 'FNV recipe outputs', 'FNV recipe outputs quest'
#: LVLF Use All: the list gives every entry. The player reference, and the script swapping tokens.
USE_ALL, PLAYER, OUTPUTS_SCRIPT = 0x04, 0x14, 'F3NV_RecipeOutputs'


class Crafting:
    """FNV crafting written through a cell builder: `station` for activators, `build` for the recipes."""

    def __init__(self, builder, export_dir: Path, helper_index: int, refs: list):
        """The export's recipes, categories, the scripts that open a station category's menu and the `refs`
        placing each station (where its player spot is measured, station_spot)."""
        self.builder, self.helper_index, self.keywords, self.tokens = builder, helper_index, {}, []
        self.categories = {int(r['FormID'], 16): r for r in export_records(export_dir, 'RCCT')}
        by_name = {r['EditorID'].lower(): fid for fid, r in self.categories.items()}
        self.recipes = list(export_records(export_dir, 'RCPE'))
        self.menus = {}
        for rec in export_records(export_dir, 'SCPT'):
            m = _MENU.search(str(rec.get('SCTX', '')))
            category = m and by_name.get(m[1].lower())
            if category and self.categories[category]['EditorID'] in STATIONS:
                self.menus[int(rec['FormID'], 16)] = category
        bases = {int(r['FormID'], 16) for r in export_records(export_dir, 'ACTI') if self.station_of(r)}
        self.placements, self.triangles, self.grid, self.export_dir = {}, None, {}, export_dir
        for ref in refs:
            if int(ref.get('NAME', '0'), 16) in bases:
                self.placements.setdefault(int(ref['NAME'], 16), []).append(ref)
        names = set(v[0] for v in STATIONS.values())
        self.templates = {_edid(r): list(subrecords(r.body)) for r, _ in walk(builder.fo4, b'FURN')
                          if _edid(r) in names}

    def station_of(self, rec: dict) -> 'int | None':
        """The station category whose menu `rec`'s script opens, else None."""
        return self.menus.get(int(rec.get('SCRI', '0'), 16))

    def station(self, fid: int, rec: dict, model: str, bounds: tuple) -> bytes:
        """FNV activator `rec` as a copy of its category's vanilla workbench furniture on `fid`."""
        category = self.station_of(rec)
        template, bench = STATIONS[self.categories[category]['EditorID']]
        subs = b''.join(self._part(tag, data, rec, (model, bounds), (category, bench))
                        for tag, data in self.templates[template])
        self.builder.counts['crafting stations'] += 1
        return pack_fo4_record('FURN', fid, 0, subs)

    def _part(self, tag: bytes, data: bytes, rec: dict, mesh: tuple, bench: tuple) -> bytes:
        """One template subrecord of station `rec` (mesh: model, bounds; bench: category, vanilla keyword)."""
        model, bounds = mesh
        if tag == b'EDID':
            return (pack_subrecord('EDID', f'FNV_{rec["EditorID"]}\0'.encode('cp1252'))
                    + pack_subrecord('OBND', struct.pack('<6h', *bounds))
                    + pack_subrecord('FULL', f'{rec.get("FULL", "")}\0'.encode('cp1252'))
                    + pack_subrecord('MODL', f'{model}\0'.encode('cp1252')))
        if tag == b'KWDA':
            ids = [self.keyword(bench[0]) if k == bench[1] else k for k in struct.unpack(f'<{len(data) // 4}I', data)]
            return pack_subrecord('KWDA', struct.pack(f'<{len(ids)}I', *ids))
        if tag == b'SNAM':
            return pack_subrecord('SNAM', self._spot(rec, bounds) or data)
        return b'' if tag in REPLACED else pack_subrecord(tag.decode(), data)

    def _spot(self, rec: dict, bounds: tuple) -> 'bytes | None':
        """The marker of station `rec` on its model's open side (station_spot); None if none measures."""
        if self.triangles is None:
            self.triangles, self.grid = self._navmesh()
        marker = spot(bounds, self.placements.get(int(rec['FormID'], 16), []), self.triangles, self.grid)
        self.builder.counts['station spots ' + ('on the open side' if marker else 'left at the origin')] += 1
        return marker

    def _navmesh(self) -> tuple:
        """({cell: navmesh triangles}, {(world, x, y): cell}) of the cells the stations stand in."""
        navmeshes = export_records(self.export_dir, 'NAVM')
        meshed = {n.get('DATA.Cell') for n in navmeshes}
        grid = {(c['ParentWRLD'], int(c['XCLC.X']), int(c['XCLC.Y'])): c['FormID']
                for c in export_records(self.export_dir, 'CELL') if c.get('ParentWRLD') and c['FormID'] in meshed}
        cells = {cell_of(ref, grid) for refs in self.placements.values() for ref in refs}
        return triangles_by_cell([n for n in navmeshes if n.get('DATA.Cell') in cells]), grid

    def keyword(self, category: int, kind: int = PLAIN) -> int:
        """The FO4 keyword of FNV recipe category `category` (written once, on FNV's FormID)."""
        if category not in self.keywords:
            rec = self.categories[category]
            fid = self.keywords[category] = self.builder.fnv_id(rec['FormID'])
            name = rec.get('FULL', '') if kind == RECIPE_FILTER else ''
            self.builder.writer.add_record('KYWD', R.pack_kywd(fid, f'FNV_{rec["EditorID"]}', kind, name))
        return self.keywords[category]

    def build(self) -> None:
        """Write a COBJ for every recipe of a category with a station, then the quest swapping tokens."""
        for rec in self.recipes:
            category = int(rec.get('DATA.Category', '0'), 16)
            if self.categories.get(category, {}).get('EditorID') in STATIONS:
                self._recipe(rec, category)
        if self.tokens:
            self._outputs_quest()

    def _recipe(self, rec: dict, category: int) -> None:
        """One recipe's COBJ; skipped (counted, with why) when a part or a condition does not convert."""
        parts, outputs = self._items(rec, 'Ingredient'), self._items(rec, 'Output')
        conditions = self._conditions(rec)
        missing = next((f'{kind.lower()} {rec[f"{kind}[{i}].FormID"]}' for kind, items in
                        (('Ingredient', parts), ('Output', outputs)) for i, (p, _) in enumerate(items) if p is None), '')
        if missing or not outputs or conditions is None:
            self.builder.counts[f'recipe skipped ({missing or ("no output" if not outputs else "condition")})'] += 1
            return
        made = outputs[0] if len(outputs) == 1 else (self._token(rec, outputs), 1)
        sub = int(rec.get('DATA.SubCategory', '0'), 16)
        filters = [self.keyword(sub, RECIPE_FILTER)] if sub in self.categories else []
        self.builder.writer.add_record('COBJ', R.pack_cobj(
            self.builder.fnv_id(rec['FormID']), f'FNV_{rec["EditorID"]}', parts, made, self.keyword(category),
            filters, conditions))
        self.builder.counts['COBJ'] += 1

    def _items(self, rec: dict, kind: str) -> list:
        """[(FO4 item or None, count)] of a recipe's Ingredient or Output parts."""
        return [(self.builder.items.item(int(rec[f'{kind}[{i}].FormID'], 16)), int(rec[f'{kind}[{i}].Count']))
                for i in range(int(rec.get(f'{kind}Count', 0)))]

    def _token(self, rec: dict, outputs: list) -> int:
        """The token recipe `rec` makes for its several `outputs`, and the leveled list giving them all."""
        writer, edid = self.builder.writer, f'FNV_{rec["EditorID"]}'
        token, listed = writer.derive_formid(TOKEN_SITE, rec['FormID']), writer.derive_formid(OUTPUTS_SITE, rec['FormID'])
        first = self.builder.items.records.get(int(rec['Output[0].FormID'], 16), (None, {}))[1]
        model, bounds = self.builder.mesh(first['Model.MODL']) if 'Model.MODL' in first else ('', None)
        writer.add_record('MISC', R.pack_misc(token, f'{edid}Token', rec.get('FULL', ''), model, bounds or (0,) * 6,
                                              0, 0.0))
        writer.add_record('LVLI', R.pack_leveled('LVLI', listed, f'{edid}Outputs', 0, USE_ALL,
                                                 [(1, item, count) for item, count in outputs]))
        self.tokens.append((token, listed))
        self.builder.counts['recipe tokens (several outputs)'] += 1
        return token

    def _outputs_quest(self) -> None:
        """The start-game quest whose player alias swaps each token for its outputs (F3NV_RecipeOutputs)."""
        writer = self.builder.writer
        quest, tokens, outputs = (writer.derive_formid(QUEST_SITE, key) for key in ('quest', 'tokens', 'outputs'))
        writer.add_record('FLST', R.pack_flst(tokens, 'FNV_RecipeTokens', [t for t, _ in self.tokens]))
        writer.add_record('FLST', R.pack_flst(outputs, 'FNV_RecipeOutputLists', [o for _, o in self.tokens]))
        vmad = quest_fragments('', [], aliases=[(0, quest, [(OUTPUTS_SCRIPT, {'Tokens': tokens, 'Outputs': outputs},
                                                             {})])])
        writer.add_record('QUST', R.pack_qust(quest, 'FNV_RecipeOutputs', '', 0, [], 'Player', PLAYER, vmad))
        self.builder.counts['QUST (recipe outputs)'] += 1

    def _conditions(self, rec: dict) -> 'bytes | None':
        """The recipe's conditions on the player: its skill requirement, notes and perks; None if one cannot convert."""
        out, skill = b'', int(rec.get('DATA.Skill', -1))
        if skill >= 0:
            av = actor_value_form(fnv_av_name(skill), self.helper_index)
            if av is None:
                return None
            out += R.pack_ctda(AT_LEAST, float(rec.get('DATA.Level', 0)), GET_VALUE, av)
        for i in range(int(rec.get('ConditionCount', 0))):
            ctda = self._condition(parse(rec[f'Condition[{i}].Raw']))
            if ctda is None:
                return None
            out += ctda
        return out

    def _condition(self, cond: dict) -> 'bytes | None':
        """One recipe condition: a note held (as its book counted) or a perk held; None for any other."""
        if cond['func'] == 'HasPerk':
            perk = self.builder.perks.form_map().get(cond['p1'])
            return None if perk is None else R.pack_ctda(cond['op_flags'] & COMPARE, cond['value'], HAS_PERK, perk)
        has = cond['func'] == 'GetHasNote' and cond['op_flags'] & COMPARE == 0 and cond['value'] == 1.0
        book = self.builder.items.item(cond['p1']) if has else None
        return None if book is None else R.pack_ctda(AT_LEAST, 1.0, GET_ITEM_COUNT, book)


def _edid(rec) -> str:
    """A vanilla record's EditorID."""
    return next((d.rstrip(b'\0').decode('latin1') for t, d in subrecords(rec.body) if t == b'EDID'), '')
