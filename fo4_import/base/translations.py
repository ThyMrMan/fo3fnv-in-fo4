"""Our menus' translation files: the UTF-8 sources in translation_files/ written as the files F4SE loads.

F4SE loads `Interface/Translations/<plugin>_<sLanguage>.txt` only for each plugin active in plugins.txt, so ours
are named after FalloutHelpers.esl, which every converted FO3/FNV plugin masters. Each source `<language>.txt`
holds `$KEY<tab>text` lines; the installed file is UTF-16 LE with a BOM and CRLF lines, as F4SE requires.

See: docs/fork/swf_framework.md#translations
"""

from pathlib import Path

#: The UTF-8 sources, one `<language>.txt` per language.
SOURCES = Path(__file__).resolve().parent / 'translation_files'
#: The plugin the files are named after.
PLUGIN = 'FalloutHelpers'
#: F4SE's line buffer, in UTF-16 units: a longer line is cut.
LINE_LIMIT = 511


def entries(source: Path) -> dict:
    """{key: text} of the source file `source`; ValueError on a line that is not `$KEY<tab>text`, or too long."""
    out = {}
    for number, line in enumerate(Path(source).read_text(encoding='utf-8').splitlines(), 1):
        key, tab, text = line.partition('\t')
        if not (key.startswith('$') and len(key) > 1 and tab and text) or '\t' in text:
            raise ValueError(f'{source}:{number}: not a $KEY<tab>text line')
        if len(line.encode('utf-16-le')) // 2 > LINE_LIMIT:
            raise ValueError(f'{source}:{number}: longer than F4SE reads ({LINE_LIMIT} characters)')
        out[key] = text
    return out


def encoded(table: dict) -> bytes:
    """`table` as an F4SE file: BOM, UTF-16 LE, a CRLF line per key."""
    return ('﻿' + ''.join(f'{key}\t{text}\r\n' for key, text in table.items())).encode('utf-16-le')


def install(data_dir: Path) -> int:
    """Write each source as <data_dir>/Interface/Translations/<PLUGIN>_<language>.txt; how many were written."""
    folder = Path(data_dir) / 'Interface' / 'Translations'
    folder.mkdir(parents=True, exist_ok=True)
    sources = sorted(SOURCES.glob('*.txt'))
    for source in sources:
        (folder / f'{PLUGIN}_{source.stem}.txt').write_bytes(encoded(entries(source)))
    return len(sources)
