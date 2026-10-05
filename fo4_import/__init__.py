"""FO3/FNV export text -> a binary Fallout 4 plugin.

Layout:

- base/   the writer and the tables every domain shares

Sits beside tes5_import and reuses its record framing; only the FO4 layouts
live here. Deliberately empty of imports, like tes5_import.

See: docs/fork/research/fo4_target.md#pipeline
"""
