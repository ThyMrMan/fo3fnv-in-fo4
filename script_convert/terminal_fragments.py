"""FO3/FNV terminal menu items as a Fallout 4 terminal's fragment script.

A Fallout 4 TERM runs `Fragment_Terminal_NN(akTerminalRef)` for the menu item
whose ID is NN; item i of the FNV terminal is ID i + 1, as vanilla numbers
from 1. Each item's script converts as a TopicInfo fragment whose implicit
subject is the terminal (`akSpeakerRef`, as package fragments do). An item
flagged Add Note gives the player the note's converted record, as AddNote
converts to AddItem.

See: docs/fork/fo4_pipeline.md#terminals
"""

from script_convert.converter import ScriptConverter
from script_convert.scro_refs import add_scro_ref, resolve_scro_aliases, scro_list
from script_convert.symbols import property_declarations
from script_convert.terminal_plan import item_count
from script_convert.terminal_scripts import ADD_NOTE, terminal_script_name
from script_convert.trace_points import items


def fragment_name(item: int) -> str:
    """The fragment function of FNV item index `item` (its FO4 item ID is item + 1)."""
    return f'Fragment_Terminal_{item + 1:02d}'


def _source(rec: dict, item: int) -> str:
    """An item's FNV script text ('' without one)."""
    return (rec.get(f'Item[{item}].Script') or '').strip()


def added_note(rec: dict, item: int) -> str:
    """FormID of the note an item adds to the player; '' when it adds none."""
    flags = int(rec.get(f'Item[{item}].Flags') or 0)
    return rec.get(f'Item[{item}].Note', '') if flags & ADD_NOTE else ''


def fragment_items(rec: dict) -> list:
    """Indexes of `rec`'s items that run a fragment: a script, or Add Note with a note."""
    return [i for i in range(item_count(rec)) if _source(rec, i) or added_note(rec, i)]


def _item_body(conv: ScriptConverter, rec: dict, item: int, xref) -> list:
    """One item's fragment body: its converted script, then the note it adds (a Form: paper or holotape)."""
    refs = scro_list(rec, f'Item[{item}].')
    for fid in refs:
        add_scro_ref(conv, fid, xref)
    source = _source(rec, item)
    conv.set_scro_aliases(resolve_scro_aliases(source, refs, xref))
    body = ['  ObjectReference akSpeakerRef = akTerminalRef']
    body += conv.convert_fragment(source, 'TopicInfo') if source else []
    note = xref.formid_to_edid.get(added_note(rec, item), '')
    if note:
        conv.sc.property_refs[note] = 'Form'
        body.append(f'  Game.GetPlayer().AddItem({note}, 1)')
    return items(body)


def terminal_fragments_psc(rec: dict, xref) -> str:
    """The Papyrus of one TERM's fragment script (extends Terminal), one fragment per fragment_items() item."""
    conv, bodies = ScriptConverter(xref), []
    for item in fragment_items(rec):
        body = _item_body(conv, rec, item, xref)
        bodies += [f'Function {fragment_name(item)}(ObjectReference akTerminalRef)', *body, 'EndFunction', '']
    head = [f'ScriptName {terminal_script_name(rec["FormID"])} extends Terminal Hidden', '']
    props = property_declarations(dict(conv.sc.property_refs), set())
    return '\n'.join(head + props + [''] + bodies + conv.get_cell_family_helpers())
