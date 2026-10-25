"""fo4_import.app.matching and the Replacements screen's Show filter."""

from fo4_import.app import standins as SI
from fo4_import.app.catalog import Entry
from fo4_import.app.matching import BOTH, EDITOR_ID, NAME, Matcher, normalize
from fo4_import.app.replacements_view import shown
from fo4_import.spike.replacements import Replacement


def _entry(plugin: str, edid: str, name: str = '', owner: str = '') -> Entry:
    """A weapon catalog entry."""
    return Entry(plugin, 0x01000800, 'WEAP', edid, name, 'weapon', owner=owner)


def _form(edid: str, name: str = '') -> SI.SourceForm:
    """A weapon source form."""
    return SI.SourceForm('weapon', 'WEAP', 1, edid, name, '', 0, {})


def test_normalize():
    """Case, spaces and punctuation are ignored."""
    assert normalize('Hunting-Rifle ') == normalize('hunting rifle') == 'huntingrifle'


def test_name_and_port_editor_ids_match():
    """A same-named record matches; a port's EditorID (00DC, 00DCDLC04) matches; a word prefix (Rum) does not."""
    matcher = Matcher([_entry('Port.esp', '00DCWeapNukaCola', 'Something'), _entry('Port.esp', '00DCRumNukaCola'),
                       _entry('Lookout.esm', '00DCDLC04WeapGeckoLauncher')], ['Port.esp', 'Lookout.esm'])
    assert matcher.suggest(_form('WeapNukaCola')).entry.edid == '00DCWeapNukaCola'
    assert matcher.suggest(_form('NukaCola')) is None
    assert matcher.suggest(_form('WeapGeckoLauncher')).how == EDITOR_ID
    named = Matcher([_entry('Port.esp', 'PortGecko', 'Gecko')], ['Port.esp']).suggest(_form('CrGecko', 'gecko'))
    assert named.how == NAME and named.label == 'Gecko (Port.esp, by name)'


def test_preference_and_several():
    """Name and EditorID beat a name alone; a mod beats the base game at equal strength; others are kept."""
    entries = [_entry('Fallout4.esm', 'Knife', 'Knife'), _entry('Port.esp', '00DCWeapKnife', 'Knife'),
               _entry('Fallout4.esm', 'CompHancockKnife', 'Knife')]
    match = Matcher(entries, ['Port.esp', 'Fallout4.esm']).suggest(_form('WeapKnife', 'Knife'))
    assert (match.entry.plugin, match.how, match.count) == ('Port.esp', BOTH, 3)
    assert match.label == 'Knife (Port.esp, 1 of 3)'
    vanilla = Matcher([_entry('Fallout4.esm', 'NukaCola', 'Nuka-Cola'), _entry('Mod.esp', 'ModNuka', 'Nuka-Cola')],
                      ['Mod.esp', 'Fallout4.esm']).suggest(_form('NukaCola', 'Nuka-Cola'))
    assert vanilla.entry.plugin == 'Fallout4.esm'


def test_exact_editor_id_beats_a_prefixed_one():
    """Among base game records matched by EditorID alone, the one with no prefix wins."""
    entries = [_entry('DLCCoast.esm', 'DLC03_LvlFeralGhoul'), _entry('Fallout4.esm', 'LvlFeralGhoul')]
    assert Matcher(entries, ['DLCCoast.esm', 'Fallout4.esm']).suggest(_form('LvlFeralGhoul')).entry.plugin == \
        'Fallout4.esm'


def test_overrides_and_the_current_stand_in_are_left_out():
    """An override of another plugin's record is not suggested, nor the record already standing in."""
    entries = [_entry('Patch.esp', 'Beer', 'Beer', owner='Fallout4.esm'), _entry('Fallout4.esm', 'Beer', 'Beer')]
    matcher = Matcher(entries, ['Patch.esp', 'Fallout4.esm'])
    assert matcher.suggest(_form('Beer', 'Beer')).entry.plugin == 'Fallout4.esm'
    assert matcher.suggest(_form('Beer', 'Beer'), Replacement('Fallout4.esm', 'beer', 'item')) is None


def test_show_filter():
    """Mine, profile, rough and skipped come from the stand-in; suggested needs an unaccepted suggestion."""
    mine = SI.Current(Replacement('A.esp', 'X', 'item', origin='user'), 'table')
    rough = SI.Current(Replacement('Fallout4.esm', 'X', 'stats', origin='default'), 'table')
    assert (mine.kind, rough.kind, SI.Current(None, 'gun').kind, SI.Current(None, 'none').kind) == \
        ('mine', 'rough', 'rough', 'skipped')
    assert shown('mine', mine, None) and not shown('rough', mine, None) and shown('rough', rough, None)
    assert shown('suggested', rough, object()) and not shown('suggested', mine, object())
    assert not shown('suggested', rough, None) and shown('all', mine, None)
