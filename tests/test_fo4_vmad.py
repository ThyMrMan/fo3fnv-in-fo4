"""Fallout 4 VMAD packers against real Fallout4.esm records, byte for byte.

The samples are the VMAD fields of three vanilla records; across the plugin,
520 of 521 INFO fragment VMADs and every form-bound quest fragment VMAD
re-pack identically.
See: docs/fork/fo4_spikes.md#spike-3-vmad
"""

from fo4_import.base import vmad as V

#: Fallout4.esm 0019CBEE: defaultRefOnDeath with a quest and an Int property.
OBJECT = bytes.fromhex('060002000100110064656661756c747265666f6e646561746800020007006d79517565737401010000ffff'
                       '18d219000a005374616765546f53657403015a000000')
#: Fallout4.esm INFO 00057089: an OnEnd fragment whose script has one object property.
INFO = bytes.fromhex('06000200000003022700467261676d656e74733a546f706963496e666f733a5449465f4d513230375f30303035'
                     '373038390001000900' + '4d555352657665616c01010000ffff1e220500012700467261676d656e74733a'
                     '546f706963496e666f733a5449465f4d513230375f30303035373038390c00467261676d656e745f456e64')
#: Fallout4.esm QUST 00022A03: one stage fragment, no properties, no aliases.
QUEST = bytes.fromhex('0600020000000301002100467261676d656e74733a5175657374733a51465f4d5331325f303030323241303300'
                      '00000a00000000000000012100467261676d656e74733a5175657374733a51465f4d5331325f303030323241'
                      '30330a00467261676d656e745f300000')


def test_object_script_with_form_and_int_properties():
    """Version 6, one script, its properties as Skyrim lays them out."""
    built = V.object_scripts([('defaultrefondeath', {'myQuest': 0x0019D218}, {'StageToSet': ('int', 90)})])
    assert built == OBJECT


def test_info_fragment_embeds_the_script_entry():
    """Bind data 3, OnEnd only, and the fragment script's own properties inside the block."""
    built = V.info_fragments('Fragments:TopicInfos:TIF_MQ207_00057089', {'MUSReveal': 0x0005221E},
                             begin=None, end='Fragment_End')
    assert built == INFO


def test_quest_stage_fragment():
    """Bind data 3, a 32-bit stage and index, then an empty alias list."""
    built = V.quest_fragments('Fragments:Quests:QF_MS12_00022A03', [(10, 0, 'Fragment_0')])
    assert built == QUEST


def test_read_entry_returns_what_object_scripts_packs():
    """The reader inverts the packer for the property kinds it writes."""
    entry, end = V.read_entry(OBJECT, 6)
    assert entry == ('defaultrefondeath', {'myQuest': 0x0019D218}, {'StageToSet': ('int', 90)})
    assert end == len(OBJECT)
