"""
FNV crafting records: recipes (RCPE) and their categories (RCCT).

A pure dump: a recipe's skill requirement, categories, conditions as hex,
and its ingredients and outputs, each an item and a quantity in the order
the record stores them (an RCIL or RCOD, then the RCQY it pairs with).

See: docs/commentary/tes4_export_falloutnv.md#recipes
"""

import struct

from ..tes4_reader import Record, get_formid_str, get_subrecord
from .common import emit_conditions, emit_string, emit_u8

#: The item subrecord that opens each part of a recipe, and the key prefix it is dumped under.
_PARTS = {"RCIL": "Ingredient", "RCOD": "Output"}


def export_RECIPE(rec: Record) -> list:
    """An RCPE: name, DATA (skill, level, category, sub-category), conditions, ingredients and outputs."""
    lines = []
    emit_string(lines, "FULL", get_subrecord(rec, "FULL"))
    data = get_subrecord(rec, "DATA")
    if data and len(data.data) >= 16:
        skill, level, category, sub = struct.unpack_from("<iIII", data.data)
        lines += [f"DATA.Skill={skill}", f"DATA.Level={level}",
                  f"DATA.Category={get_formid_str(category)}", f"DATA.SubCategory={get_formid_str(sub)}"]
    emit_conditions(lines, rec)
    counts, part = {"Ingredient": 0, "Output": 0}, None
    for sub in rec.subrecords:
        if sub.type in _PARTS and len(sub.data) >= 4:
            part = _PARTS[sub.type]
            lines.append(f"{part}[{counts[part]}].FormID={get_formid_str(struct.unpack_from('<I', sub.data)[0])}")
        elif sub.type == "RCQY" and part and len(sub.data) >= 4:
            lines.append(f"{part}[{counts[part]}].Count={struct.unpack_from('<I', sub.data)[0]}")
            counts[part] += 1
            part = None
    lines += [f"IngredientCount={counts['Ingredient']}", f"OutputCount={counts['Output']}"]
    return lines


def export_RECIPE_CATEGORY(rec: Record) -> list:
    """An RCCT: name and DATA's Subcategory flag."""
    lines = []
    emit_string(lines, "FULL", get_subrecord(rec, "FULL"))
    emit_u8(lines, "DATA.Subcategory", get_subrecord(rec, "DATA"))
    return lines


RECIPE_EXPORTERS = {
    "RCPE": export_RECIPE,
    "RCCT": export_RECIPE_CATEGORY,
}
