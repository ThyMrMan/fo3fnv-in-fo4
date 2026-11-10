"""Generate which FNV/FO3 subrecords hold FormIDs, and where, from xEdit's definitions.

Reads wbDefinitionsFNV.pas (or FO3's): every record's subrecords, each as `none` (no FormID), its FormID byte
offsets (`{"at": [...], "stride": n, "start": n}`: at those offsets once, or in every `stride`-byte entry after
`start`; with `select` and `cases`, more offsets when a selector field holds a listed value), a layout the reader
handles itself (`condition`, `alt_textures`, `owner_data`), or `complex` (a FormID after variable-length data or
behind an unknown decider). Unknown helper calls are `complex` when anything under them names a FormID.

    py -3.14 -m tools.generators.gen_fnv_subrecord_formids references/xEdit/Core/wbDefinitionsFNV.pas \
        -o fo4_import/data/fnv_subrecord_formids.json

See: docs/fork/fo4_plugin_layout.md#multi-master
"""

import argparse
import json
import re
from pathlib import Path

TOKEN = re.compile(r"\s+|//[^\n]*|\{[^}]*\}|\(\*.*?\*\)|'(?:[^']|'')*'|\$[0-9A-Fa-f]+|\d+(?:\.\d+)?|:=|[A-Za-z_]\w*|.",
                   re.S)
SIG = re.compile(r'^[A-Z0-9_]{4}$')
INT_SIZES = {'itU8': 1, 'itS8': 1, 'itU16': 2, 'itS16': 2, 'itU32': 4, 'itS32': 4, 'itU64': 8, 'itS64': 8}
#: Fixed-size FNV fields by helper name.
FIXED = {'wbFloat': 4, 'wbDouble': 8, 'wbByteColors': 4, 'wbFloatColors': 12, 'wbVec3': 12, 'wbVec3Pos': 12,
         'wbVec3Rot': 12, 'wbVec3PosRot': 24, 'wbVec3PosRotDegrees': 24, 'wbSizePosRot': 40, 'wbEmpty': 0}
#: xEdit's helper file every game's definitions use, and its named signatures.
COMMON, SIGNATURES = 'wbDefinitionsCommon.pas', 'wbDefinitionsSignatures.pas'
SIG_CONST = re.compile(r"(\w+)\s*:\s*TwbSignature\s*=\s*((?:#\$[0-9A-Fa-f]{2}|'[^']*')+)\s*;")
SIG_PART = re.compile(r"#\$([0-9A-Fa-f]{2})|'([^']*)'")
#: Helpers given FNV's layout by hand (their bodies branch on the game in code): Layouts.helper_call.
HELPER_CALLS = frozenset({'wbOwnership', 'wbLeveledListEntry', 'wbTexturedModel'})
#: Subrecords read by a layout of their own: condition, alternate textures (FO3/FNV; FO4's are material swap FormIDs).
SPECIAL = {'CTDA': 'condition', 'MODS': 'alt_textures', 'MO2S': 'alt_textures', 'MO3S': 'alt_textures',
           'MO4S': 'alt_textures', 'DMDS': 'alt_textures', 'COED': 'owner_data'}
#: Subrecords xEdit defines two ways, set by hand: DIAL's unused INFC copy, REFR TNAM (2-byte map marker or topic).
OVERRIDE = {'DIAL': {'INFC': {'at': [0]}}, 'REFR': {'TNAM': {'at': [0]}}}
#: Decider unions: the field picking a branch (same struct's `field`, or subrecord `sub`), values per branch.
DECIDERS = {'wbPxDTLocationDecider': {'select': {'field': "'Type'"}},
            'wbPerkDATADecider': {'select': {'sub': 'PRKE', 'at': 0, 'size': 1}},
            'wbEPFDDecider': {'select': {'sub': 'EPFT', 'at': 0, 'size': 1}},
            'wbNOTETNAMDecide': {'select': {'sub': 'DATA', 'at': 0, 'size': 1}, 'values': {1: [3]}}}
#: Subrecords FNV's plugins carry that xEdit's FNV definitions leave out, checked on FalloutNV.esm (fo4_plugin_layout.md).
EXTRA = {'ARMO': {'EITM': {'at': [0]}}, 'EXPL': {'EITM': {'at': [0]}}, 'WEAP': {'EITM': {'at': [0]}, 'EAMT': 'none'},
         'REGN': {'RDSD': {'at': [0], 'stride': 12, 'start': 0}}, 'DEBR': {'MODT': 'none'}}
OPERATORS = {'+', '-', '*', '/', 'or', 'and', 'not', '=', '<', '>', '@', '^', 'div', 'mod'}
COMPLEX = 'complex'
#: xEdit's game checks Is<Game>(a, b) whose first branch FNV takes (it counts as Fallout 3); FO3 takes all but IsFNV.
FIRST_BRANCH = {'fnv': {'IsFO3', 'IsTES4FO3', 'IsFNV'}, 'fo3': {'IsFO3', 'IsTES4FO3'}, 'fo4': set()}


class Call:
    """A parsed call: name and arguments."""

    def __init__(self, name: str, args: list):
        """`name`(`args`)."""
        self.name, self.args = name, args


class Parser:
    """Pascal expressions over the definition file's tokens: calls, lists, names, numbers, strings."""

    def __init__(self, text: str):
        """Tokenize `text`, comments dropped."""
        self.toks = [t for t in TOKEN.findall(text) if t.strip() and not t.startswith(('//', '{', '(*'))]
        self.pos = 0

    def peek(self, ahead: int = 0) -> str:
        """The token `ahead` of the cursor ('' past the end)."""
        i = self.pos + ahead
        return self.toks[i] if i < len(self.toks) else ''

    def expr(self):
        """One expression; operators and method chains are read and dropped."""
        first = self.primary()
        while self.peek() == '.' or self.peek().lower() in OPERATORS:
            self.pos += 1
            self.primary()
        return first

    def primary(self):
        """A name or call, a [list], a (group), a number or string."""
        tok = self.peek()
        self.pos += 1
        if tok == '[':
            return self.items(']')
        if tok == '(':
            inner = self.items(')')
            return inner[0] if inner else None
        if tok.lower() in OPERATORS:
            return self.primary()
        if re.match(r'[A-Za-z_]', tok) and self.peek() == '(':
            self.pos += 1
            return Call(tok, self.items(')'))
        return tok

    def items(self, close: str) -> list:
        """Comma-separated expressions up to `close`."""
        out = []
        while self.peek() and self.peek() != close:
            out.append(self.expr())
            if self.peek() == ',':
                self.pos += 1
        self.pos += 1
        return out

    def definitions(self) -> tuple:
        """({helper: expression} of `wbX := ...;`, [wbRecord calls])."""
        helpers, records = {}, []
        while self.pos < len(self.toks):
            tok = self.peek()
            if tok.startswith('wb') and self.peek(1) == ':=':
                self.pos += 2
                helpers[tok] = self.expr()
            elif tok == 'function' and self.peek(1).startswith('wb'):
                self.function(helpers)
            elif tok in ('wbRecord', 'wbRefRecord') and self.peek(1) == '(':
                records.append(self.expr())
            else:
                self.pos += 1
        return helpers, records

    def function(self, helpers: dict) -> None:
        """A helper function's first `Result := ...` body as its definition (a declaration has none)."""
        name = self.peek(1)
        self.pos += 2
        while self.peek() and self.peek() not in ('function', 'procedure'):
            if self.peek() == 'Result' and self.peek(1) == ':=':
                self.pos += 2
                helpers.setdefault(name, self.expr())
                return
            self.pos += 1


class Case:
    """A decider union's FormID: the selector field, the values that pick its branch, its offset."""

    def __init__(self, select: dict, values: list, offset: int):
        """At `offset` when the field `select` names holds one of `values`."""
        self.select, self.values, self.offset = select, values, offset

    def shifted(self, by: int, named: dict) -> 'Case':
        """This case `by` bytes on; a same-struct selector placed by `named` ({field label: (offset, size)})."""
        select = self.select
        if 'field' in select and select['field'] in named:
            at, size = named[select['field']]
            select = {'at': at, 'size': size}
        elif 'field' not in select and 'sub' not in select:
            select = {**select, 'at': select['at'] + by}
        return Case(select, self.values, self.offset + by)


class Layouts:
    """Subrecord FormID layouts of records, resolving helpers."""

    def __init__(self, helpers: dict, game: str, sigs: dict):
        """Definitions `helpers`, `game`'s branches (fnv, fo3), signature constants `sigs`."""
        self.helpers, self.first, self.sigs = helpers, FIRST_BRANCH[game], sigs
        self.special = {k: v for k, v in SPECIAL.items() if game != 'fo4' or v != 'alt_textures'}

    def resolve(self, node):
        """`node` with a helper (name or call) replaced by its definition, a game check by its branch."""
        seen = set()
        while id(node) not in seen:
            seen.add(id(node))
            node = self.named(node)
            if isinstance(node, Call) and node.name in self.helpers and node.name not in HELPER_CALLS:
                node = self.helpers[node.name]
        return node

    def names_formid(self, node, depth: int = 0) -> bool:
        """Whether anything under `node` names a FormID."""
        node = self.resolve(node)
        if depth > 12 or node is None:
            return False
        if isinstance(node, list):
            return any(self.names_formid(n, depth + 1) for n in node)
        if isinstance(node, Call):
            return 'FormID' in node.name or node.name in ('wbOwnership', 'wbLeveledListEntry') or any(
                self.names_formid(a, depth + 1) for a in node.args)
        return False

    def field(self, node):
        """(size or None, FormID offsets or Cases) of a field; COMPLEX when a FormID cannot be placed."""
        named = self.named(node)
        if isinstance(named, Call) and named.name in FIXED:
            return FIXED[named.name], []
        node = self.resolve(named)
        if not isinstance(node, Call):
            return (0, []) if node is None else (None, [])
        name, args = node.name, node.args
        if 'FormID' in name:
            return 4, [0]
        if name == 'wbInteger':
            kind = next((a for a in args if isinstance(a, str) and a in INT_SIZES), None)
            return INT_SIZES.get(kind), []
        if name in ('wbUnused', 'wbUnknown'):
            return _number(args[0]) if args else None, []
        if name in ('wbByteArray', 'wbString', 'wbStringKC', 'wbLenString'):
            size = next((_number(a) for a in args[1:] if _number(a) is not None), 0)
            return (size or None), []
        if name.startswith('wbStruct'):
            return self.struct(fields(args))
        if name.startswith('wbArray'):
            return self.array(args)
        if name == 'wbUnion':
            decider = next((a for a in args if isinstance(a, str) and a in DECIDERS), None)
            return self.union(next((a for a in args if isinstance(a, list)), []), decider)
        return (COMPLEX, []) if self.names_formid(node) else (None, [])

    def union(self, branches: list, decider: 'str | None' = None):
        """A union whose branches agree, as one; a known decider's as Cases; else COMPLEX or unsized."""
        shapes = [self.field(branch) for branch in branches]
        if len({(size, tuple(at)) for size, at in shapes}) == 1:
            return shapes[0]
        sizes = {size for size, _ in shapes}
        plain = all(isinstance(a, int) for _, at in shapes for a in at)
        if decider and COMPLEX not in sizes and plain:
            rule = DECIDERS[decider]
            cases = [Case(rule['select'], rule.get('values', {}).get(i, [i]), a)
                     for i, (_, at) in enumerate(shapes) for a in at]
            return (sizes.pop() if len(sizes) == 1 else None), cases
        return (COMPLEX, []) if any(at or size == COMPLEX for size, at in shapes) else (None, [])

    def struct(self, fields: list):
        """(size or None, FormID offsets or Cases) of consecutive `fields`."""
        size, offsets, named = 0, [], {}
        for item in fields:
            got, at = self.field(item)
            if got == COMPLEX or (got is None and self.names_formid(item)):
                return COMPLEX, []
            if at and size is None:
                return COMPLEX, []
            if size is not None:
                offsets += [a + size if isinstance(a, int) else a.shifted(size, named) for a in at]
                named[label(self.resolve(item))] = (size, got)
            size = None if got is None or size is None else size + got
        return size, offsets

    def array(self, args: list):
        """An array field: a fixed count's size and offsets; else None (variable), COMPLEX if it holds FormIDs."""
        element = next((a for a in args[1:] if not isinstance(a, str) or a in self.helpers), None)
        names = next((a for a in args[2:] if isinstance(a, list)), None)
        count = len(names) if names else next((_number(a) for a in args[2:] if _number(a) is not None), 0)
        size, at = self.field(element)
        if size == COMPLEX or not all(isinstance(a, int) for a in at):
            return COMPLEX, []
        if count and count > 0 and size is not None:
            return size * count, [i * size + a for i in range(count) for a in at]
        return (COMPLEX, []) if at else (None, [])

    def named(self, node):
        """`node` with helper names and game checks resolved, a helper call kept (it may carry a signature)."""
        seen = set()
        while id(node) not in seen:
            seen.add(id(node))
            if isinstance(node, str) and node in self.helpers:
                node = self.helpers[node]
            elif isinstance(node, Call) and re.fullmatch(r'Is[A-Z]\w*', node.name) and len(node.args) == 2:
                node = node.args[0 if node.name in self.first else 1]
        return node

    def sig_of(self, token) -> 'str | None':
        """The signature `token` names (literal or constant); None otherwise."""
        if isinstance(token, str) and SIG.match(token):
            return token
        return self.sigs.get(token) if isinstance(token, str) else None

    def subrecord(self, node) -> 'tuple | None':
        """(signature, layout) of a subrecord definition; None when `node` is not one."""
        node = self.named(node)
        sig = self.sig_of(node.args[0]) if isinstance(node, Call) and node.args else None
        if sig is None:
            return None
        name, args = node.name, node.args
        if sig in self.special:
            return sig, self.special[sig]
        if 'FormID' in name:
            return sig, {'at': [0]}
        if name.startswith('wbArray'):
            return sig, self.subrecord_array(args)
        if name.startswith('wbStruct'):
            return sig, layout(*self.struct(fields(args)))
        if name == 'wbUnion':
            return sig, layout(*self.field(node))
        return sig, COMPLEX if self.names_formid(node) else 'none'

    def subrecord_array(self, args: list):
        """A whole-subrecord array: its entries' stride and offsets after the count prefix."""
        element = next((a for a in args[2:] if not isinstance(a, str) or a in self.helpers), None)
        count = next((_number(a) for a in args[3:] if _number(a) is not None), 0)
        size, at = self.field(element)
        if not at:
            return COMPLEX if size == COMPLEX else 'none'
        if size in (None, COMPLEX) or not all(isinstance(a, int) for a in at):
            return COMPLEX
        if count > 0:
            return {'at': [i * size + a for i in range(count) for a in at]}
        return {'at': at, 'stride': size, 'start': {0: 0, -1: 4, -2: 2}.get(count, 0)}

    def members(self, node, out: dict) -> None:
        """Every subrecord under record member `node` into `out` (a sig defined two ways is COMPLEX)."""
        node = self.named(node)
        if isinstance(node, list):
            for item in node:
                self.members(item, out)
            return
        if not isinstance(node, Call):
            return
        found = self.helper_call(node) or self.signed(node)
        if found is None:
            body = self.resolve(node)
            for arg in [body] if body is not node else node.args:
                self.members(arg, out)
            return
        for sig, layout in found:
            out[sig] = merged(out.get(sig, layout), layout)

    def signed(self, node: Call) -> 'list | None':
        """[(sig, layout)] of a subrecord call; a helper function naming several signatures gives each one."""
        found = self.subrecord(node)
        if found is None:
            return None
        extra = [self.sig_of(a) for a in node.args[1:]] if node.name in self.helpers else []
        return [found, *((sig, found[1]) for sig in extra if sig)]

    def helper_call(self, node: Call) -> 'list | None':
        """FNV's shared helpers whose bodies are game-conditional code: [(sig, layout)]; None otherwise."""
        if node.name == 'wbOwnership':
            return [('XOWN', {'at': [0]}), ('XRNK', 'none')]
        if node.name == 'wbLeveledListEntry':
            return [('LVLO', {'at': [4]})]
        if node.name == 'wbTexturedModel' and len(node.args) > 1 and isinstance(node.args[1], list):
            sigs = node.args[1]
            out = [(sigs[0], 'none')] + ([(sigs[1], 'none')] if len(sigs) > 1 else [])
            textures = {}
            for item in node.args[2:]:
                self.members(item, textures)
            return out + list(textures.items())
        return None

    def record(self, call: Call) -> tuple:
        """(signature, {subrecord: layout}) of a wbRecord call."""
        out = {}
        for arg in call.args[1:]:
            if isinstance(arg, list):
                self.members(arg, out)
        return call.args[0], out


def layout(size, at: list):
    """A subrecord's layout from its (size, offsets or Cases): `none`, {"at"}, with `select` and `cases`, or COMPLEX."""
    cases = [a for a in at if isinstance(a, Case)]
    if size == COMPLEX or len({json.dumps(c.select, sort_keys=True) for c in cases}) > 1:
        return COMPLEX
    if any('field' in c.select for c in cases):
        return COMPLEX
    if not at:
        return 'none'
    out, grouped = {'at': [a for a in at if isinstance(a, int)]}, {}
    for case in cases:
        grouped.setdefault(tuple(case.values), []).append(case.offset)
    if cases:
        out.update(select=cases[0].select, cases=[{'in': list(v), 'at': o} for v, o in grouped.items()])
    return out


def merged(old, new):
    """One subrecord defined twice: the same layout; a sub-selected one over `none` (it applies nothing before
    its selector subrecord, which follows the other's); else COMPLEX.
    See: docs/fork/fo4_plugin_layout.md#multi-master
    """
    if old == new:
        return old
    selected = [v for v in (old, new) if isinstance(v, dict) and 'sub' in v.get('select', {})]
    return selected[0] if len(selected) == 1 and 'none' in (old, new) else COMPLEX


def label(node) -> str:
    """A field call's name argument ('' for none)."""
    return node.args[0] if isinstance(node, Call) and node.args and isinstance(node.args[0], str) else ''


def signatures(path: Path) -> dict:
    """{constant: signature} of xEdit's named signatures (`_0E_IAD : TwbSignature = #/usr/bin/bashE'IAD';`)."""
    out = {}
    for name, value in SIG_CONST.findall(path.read_text(encoding='utf-8', errors='replace')):
        out[name] = ''.join(chr(int(h, 16)) if h else text for h, text in SIG_PART.findall(value))
    return out


def fields(args: list) -> list:
    """A struct call's field list (its list of definitions, not sort-key indexes)."""
    return next((a for a in args if isinstance(a, list) and any(not _is_index(x) for x in a)), [])


def _is_index(item) -> bool:
    """Whether `item` is a bare integer (a sort-key index)."""
    return _number(item) is not None


def _number(token) -> 'int | None':
    """An integer token's value (a negative one parses as its operator then its digits); None otherwise."""
    if isinstance(token, str) and re.fullmatch(r'-?\d+', token):
        return int(token)
    if isinstance(token, str) and token.startswith('$'):
        return int(token[1:], 16)
    return None


def build(pas: Path, game: str = 'fnv') -> dict:
    """{record: {subrecord: layout}} of definitions file `pas`, wbDefinitionsCommon.pas's helpers behind it."""
    common, _ = Parser((pas.parent / COMMON).read_text(encoding='utf-8', errors='replace')).definitions()
    helpers, records = Parser(pas.read_text(encoding='utf-8', errors='replace')).definitions()
    layouts = Layouts({**common, **helpers}, game, signatures(pas.parent / SIGNATURES))
    out = {}
    for call in records:
        if isinstance(call, Call) and call.args and layouts.sig_of(call.args[0]):
            sig, subs = layouts.record(call)
            out.setdefault(sig, {}).update(subs)
    for sig, subs in EXTRA.items():
        out.setdefault(sig, {}).update({k: v for k, v in subs.items() if k not in out[sig]})
    for sig, subs in OVERRIDE.items():
        out.setdefault(sig, {}).update(subs)
    return dict(sorted(out.items()))


def main() -> None:
    """Write the table and print how many subrecords are complex."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pas', type=Path)
    ap.add_argument('-o', '--out', type=Path, required=True)
    ap.add_argument('--game', choices=sorted(FIRST_BRANCH), default='fnv')
    args = ap.parse_args()
    table = build(args.pas, args.game)
    args.out.write_text(json.dumps(table, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    complex_ = sorted(f'{r}.{s}' for r, subs in table.items() for s, v in subs.items() if v == COMPLEX)
    print(f'{len(table)} records, {sum(map(len, table.values()))} subrecords, {len(complex_)} complex: {complex_}')


if __name__ == '__main__':
    main()
