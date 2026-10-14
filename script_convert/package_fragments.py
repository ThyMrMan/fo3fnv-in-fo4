"""FO3/FNV package scripts written as a Skyrim package's fragment script.

Which sections exist is `tes5_import.packages.scripts_falloutnv`, the contract
the importer's VMAD reads too; this writes the `PF_` script those name, and
hands the importer the properties it declares.

See: docs/commentary/script_convert.md#package-fragments
"""

from script_convert.constants import script_prefix
from script_convert.converter import ScriptConverter
from script_convert.scro_refs import add_scro_ref, resolve_scro_aliases, scro_list
from script_convert.symbols import property_declarations
from script_convert.target import is_fallout4
from script_convert.trace_points import items, package
from tes5_import.packages.scripts_falloutnv import folds_change, package_sections, section_source


def package_fragment_name(formid: str) -> str:
    """The PF_ script name of the package with source FormID `formid`."""
    return f'{script_prefix("_PF__")}{formid.upper()}'


def _convert_package(rec: dict, xref) -> tuple:
    """(converter, fragment function lines) for one package's sections.

    Each body converts as a TopicInfo fragment, whose implicit subject is
    `akSpeakerRef`; here that is the actor running the package.
    """
    conv = ScriptConverter(xref)
    bodies = []
    for i, (section, _flag) in enumerate(package_sections(rec)):
        source = section_source(rec, section, xref.formid_to_edid)
        refs = scro_list(rec, f'{section}.')
        if section == 'OnEnd' and folds_change(rec):
            refs += scro_list(rec, 'OnChange.')
        for fid in refs:
            add_scro_ref(conv, fid, xref)
        conv.set_scro_aliases(resolve_scro_aliases(source, refs, xref))
        guard = _end_guard(section, i)
        bodies += [f'Function Fragment_{i}(Actor akActor)', *guard[:-1], '  ObjectReference akSpeakerRef = akActor']
        bodies += conv.convert_fragment(source, 'TopicInfo') + guard[-1:] + ['EndFunction', '']
    return conv, bodies


def package_psc(rec: dict, xref) -> str:
    """The Papyrus of one package's fragment script, one Fragment_N per section."""
    conv, bodies = _convert_package(rec, xref)
    head = [f'ScriptName {package_fragment_name(rec["FormID"])} extends Package Hidden', '']
    props = property_declarations(dict(conv.sc.property_refs), set())
    bodies = items(package(bodies, package_fragment_name(rec['FormID'])))
    return '\n'.join(head + props + _end_arrays(rec) + [''] + bodies + conv.get_cell_family_helpers())


def package_property_refs(rec: dict, xref) -> dict:
    """{property: Papyrus type} the package's fragment script declares."""
    return dict(_convert_package(rec, xref)[0].sc.property_refs)


def _end_call(i: int) -> str:
    """TES4Polyfill.PackageEndRepeats on fragment `i`'s actor arrays."""
    return f'TES4Polyfill.PackageEndRepeats(Self, akActor, TES4Ended_{i}, TES4EndedAt_{i})'


def _end_guard(section: str, i: int) -> list:
    """Fragment `i`'s FO4 end guard lines, then its closing restamp; [] for a begin or another target."""
    if section not in ('OnEnd', 'OnChange') or not is_fallout4():
        return []
    return [f'  If !TES4Ended_{i}', f'    TES4Ended_{i} = new Actor[1]', f'    TES4EndedAt_{i} = new Float[1]',
            '  EndIf', f'  If {_end_call(i)}', '    Return', '  EndIf', f'  {_end_call(i)}']


def _end_arrays(rec: dict) -> list:
    """The script variables of the package's guarded fragments."""
    return [line for i, (section, _flag) in enumerate(package_sections(rec)) if _end_guard(section, i)
            for line in (f'Actor[] TES4Ended_{i}', f'Float[] TES4EndedAt_{i}')]
