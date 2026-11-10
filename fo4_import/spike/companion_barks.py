"""FNV's companion status barks on Fallout 4: a start-game quest whose script says them as a follower's state changes.

FNV's engine says its companion status topics (HealthHalf, NoAmmo, ...) itself; Fallout 4 has no subtype for them.
The ones with a state Fallout 4 reads (STATUS_BARKS) are built as custom topics of their quest (say_topics, as a
script's), and `F3NV_CompanionBarks` on this quest says them for each follower.

See: docs/fork/fo4_pipeline.md#companion-barks
"""


from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_script_quest
from fo4_import.base.vmad import quest_fragments

#: FNV companion status topics (EditorIDs) the watch script says, each its property of the same name.
STATUS_BARKS = ('HealthHalf', 'HealthQuarter', 'Wake', 'NoAmmo')
#: The watch script; derive_formid site of a plugin's watch quest (key: the plugin's stem).
SCRIPT, QUEST_SITE = 'F3NV_CompanionBarks', 'FNV companion barks'


def status_barks(dials: dict) -> set:
    """FNV FormIDs of the `dials` topics STATUS_BARKS names."""
    return {fid for fid, dial in dials.items() if dial.get('EditorID') in STATUS_BARKS}


def write(builder) -> None:
    """The watch quest, its properties the status topics `builder` built (scripts.named); none built, no quest."""
    topics = {name: builder.scripts.named[name] for name in STATUS_BARKS if name in builder.scripts.named}
    if not topics:
        return
    plugin = plugin_stem(builder.export_dir)
    fid = builder.writer.derive_formid(QUEST_SITE, plugin)
    vmad = quest_fragments('', [], scripts=[(SCRIPT, topics, {})])
    builder.writer.add_record('QUST', pack_script_quest(fid, f'FNV_CompanionBarks_{plugin}', vmad))
    builder.scripts.used.append(SCRIPT)
    builder.counts['companion status barks watched'] = len(topics)
