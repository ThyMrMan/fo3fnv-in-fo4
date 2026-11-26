"""An own-rig entry (table.Rig) worked out from a creature's FNV files, for a skeleton folder no rule names: its clips
by animation group, its attacks, its body parts and pose bones from its skeleton's ragdoll and FNV body part data, and
a gun when its creatures carry one.

See: docs/fork/fo4_auto_rig_plan.md#derive
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from asset_convert.havok.kf_decode import ACCUM_ROOT_BONES
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import fnv_nif
from fo4_import.rig.table import Rig, rigs
from fo4_import.spike.creature_attacks import clip_groups, weapon_prefix

#: The hand entries' templates: the mole rat's (every rig), the securitron's for one that talks (ProtectronRace).
MOLE_RAT, TALKER = 'creatures\\nvgecko', 'creatures\\nvsecuritron'
#: Clip role -> the FNV animation groups that fill it, first found wins.
ROLES = (('Idle', ('idle',)), ('TurnLeft', ('turnleft',)), ('TurnRight', ('turnright',)),
         ('WalkForward', ('forward',)), ('RunForward', ('fastforward', 'forward')), ('WalkBackward', ('backward',)),
         ('CombatIdle', ('aim', 'idle')), ('AttackLeft', ('attackleft',)), ('AttackRight', ('attackright',)))
#: The roles an immobile rig (no Forward clip) plays its idle in.
MOVES = ('TurnLeft', 'TurnRight', 'WalkForward', 'RunForward')
#: FNV's power-attack groups, in the order the two power roles take them; the forward role takes its own first.
POWER_GROUPS = ('attackpower', 'attackleftpower', 'attackrightpower', 'attackbackpower', 'attackforwardpower')
FORWARD_POWER = 'attackforwardpower'
#: Each attack role's melee event, power flag and label (as every hand entry has them).
ATTACKS = {'AttackLeft': ('meleeStart_Left', False, 'Attack Left'),
           'AttackRight': ('meleeStart_Right', False, 'Attack Right'),
           'AttackPower': ('meleeStart_Power', True, 'Power Attack'),
           'AttackForwardPower': ('meleeStart_ForwardPower', True, 'Forward Power Attack')}
#: Hand-type prefixes of a melee or unarmed clip (KF_PREFIX); a gun's start with one of RANGED.
MELEE, RANGED = ('', 'h2h'), ('1hp', '2hr', '2ha', '2hh', '2hl')
#: The ranged rig's one gun: its clip role, equip slot (EQUP), and the FNV node name its fire node starts with.
GUN_ROLE, GUN_SLOT, FIRE_NODE = 'RangedAttack', 'RightHand', 'ProjectileNode'
#: FNV body part type Head1 (BPND, wbBodyLocationEnum).
HEAD = 1
#: The node under each accumulation root that the engine does not move (kf_decode.split_root_motion's spellings).
NON_ACCUM = frozenset(f'{b} NonAccum' for b in ACCUM_ROOT_BONES)
#: A limb root closer to the body's middle than this (units, along X) is a tail, not a side's limb.
MIDDLE = 0.5
#: World X sign of a left limb (FNV's `Bip01 L UpperArm` sits at -X).
LEFT = -1.0
#: A clip's hand-type prefix (weapon_prefix) by preference: none, then unarmed; any other (a gun's, swim, sneak) last.
PREFERRED = ('', 'h2h')


@dataclass(frozen=True)
class Tree:
    """An FNV skeleton: each node's parent and children (file order), depth-first order, ragdoll body nodes and world
    position."""
    parent: dict
    children: dict
    order: tuple
    bodied: frozenset
    pos: dict

    def ancestors(self, node: str) -> list:
        """`node`'s ancestors, nearest first."""
        out = []
        while self.parent.get(node):
            node = self.parent[node]
            out.append(node)
        return out


def read_tree(path: Path) -> Tree:
    """The Tree of FNV skeleton NIF `path`."""
    root = fnv_nif(path)
    parent, children, order, bodied, pos = {}, {}, [], set(), {}
    for node in root.tree():
        if isinstance(node, NifFormat.NiNode):
            name = node.name.decode('cp1252')
            order.append(name)
            pos[name] = np.array(node.get_transform(root).as_list()[3][:3], dtype=float)
            bodied.update({name} if node.collision_object else set())
            kids = [c.name.decode('cp1252') for c in node.children if isinstance(c, NifFormat.NiNode)]
            children[name] = kids
            parent.update({k: name for k in kids})
    return Tree(parent, children, tuple(order), frozenset(bodied), pos)


def clips(root: Path, ranged: bool) -> dict:
    """{clip role: .kf under `root`} of the FNV clips filling each role (ROLES, then the power roles and, when
    `ranged`, GUN_ROLE); {} without an Idle clip. With no Forward clip the rig is immobile: MOVES play its idle.
    See: docs/fork/fo4_auto_rig_plan.md#groups
    """
    groups = clip_groups(Path(root))
    found = {}
    for role, wanted in ROLES:
        melee = role.startswith('Attack') or role == 'CombatIdle'
        kf = next((k for g in wanted for k in [_best(groups.get(g, ()), root, melee)] if k), None)
        found.update({role: kf} if kf else {})
    if 'Idle' not in found:
        return {}
    if 'forward' not in groups:
        found.update({role: found['Idle'] for role in MOVES})
    found.update({role: found['Idle'] for role in MOVES if role not in found})
    found.update(_powers(groups, root))
    shot = _best([k for g, ks in groups.items() if g.startswith('attack') for k in ks
                  if weapon_prefix(k.name).startswith(RANGED)], root, False) if ranged else None
    return {role: _rel(kf, root) for role, kf in {**found, **({GUN_ROLE: shot} if shot else {})}.items()}


def _powers(groups: dict, root: Path) -> dict:
    """{power role: .kf} from FNV's power groups (POWER_GROUPS), the forward role taking FORWARD_POWER first."""
    present = [g for g in POWER_GROUPS if _best(groups.get(g, ()), root, True)]
    if not present:
        return {}
    first = present[0] if present[0] != FORWARD_POWER or len(present) == 1 else present[1]
    rest = [g for g in present if g != first]
    second = FORWARD_POWER if FORWARD_POWER in rest else (rest[0] if rest else None)
    picks = {'AttackPower': first, **({'AttackForwardPower': second} if second else {})}
    return {role: _best(groups[g], root, True) for role, g in picks.items()}


def _best(kfs, root: Path, melee: bool) -> 'Path | None':
    """The clip of `kfs` a role takes (melee: unarmed only).
    See: docs/fork/fo4_auto_rig_plan.md#groups
    """
    kept = [k for k in kfs if not melee or weapon_prefix(k.name) in MELEE]
    rank = lambda k: (PREFERRED.index(p) if (p := weapon_prefix(k.name)) in PREFERRED else len(PREFERRED),
                      '_' in k.stem, len(k.relative_to(root).parts), str(k.relative_to(root)).lower())
    return min(kept, key=rank, default=None)


def _rel(kf: Path, root: Path) -> str:
    """`kf` under `root` as a table path (lower case, backslashes)."""
    return str(kf.relative_to(root)).replace('/', '\\').lower()


def body_plan(tree: Tree, parts: list) -> 'dict | None':
    """{role: bone} of the pelvis, spine, chest, head and limbs of `tree` (FNV body part data `parts`: (bone, name,
    type)). The trunk is the head's (_head) ancestors below the accumulation root; the pelvis its first ragdoll body
    but the NonAccum node and the head (else the first); the chest the last other body at or below where the front
    limb leaves the trunk (else the next); limbs are _legs. None without a ragdoll body.
    See: docs/fork/fo4_auto_rig_plan.md#derive
    """
    head = _head(tree, parts)
    if head is None:
        return None
    trunk = [n for n in reversed(tree.ancestors(head)) if n not in (tree.order[0], *ACCUM_ROOT_BONES)] + [head]
    bodies = [n for n in trunk if n in tree.bodied] or [head]
    pelvis = next((n for n in bodies if n not in NON_ACCUM and n != head), bodies[0])
    front, back, hanger = _legs(tree, trunk, pelvis)
    later = [n for n in trunk[trunk.index(pelvis) + 1:-1] if n in tree.bodied]
    chest = next((n for n in reversed(later) if trunk.index(n) <= trunk.index(hanger)), (later or [head])[0])
    spine = trunk[trunk.index(pelvis) + 1:trunk.index(chest)] or [pelvis]
    return {'pelvis': pelvis, 'spine1': spine[0], 'spine2': spine[len(spine) // 2], 'chest': chest, 'head': head,
            'front': front, 'back': back, 'bodies': [n for n in tree.order if n in tree.bodied]}


def _head(tree: Tree, parts: list) -> 'str | None':
    """`parts`' Head part's node, else _middle_end; None without bodies."""
    names = {n.lower(): n for n in tree.order}
    named = next((names[b] for b, _, kind in parts if kind == HEAD and b in names), None)
    return named or _middle_end(tree)


def _middle_end(tree: Tree) -> 'str | None':
    """The last ragdoll body reached from the root by taking, at each node, the child within MIDDLE of it on X whose
    subtree holds the most bodies (a hull with no such child: itself)."""
    count = {}
    for name in reversed(tree.order):
        count[name] = (name in tree.bodied) + sum(count[c] for c in tree.children.get(name, ()))
    node, last = tree.order[0], None
    while node:
        last = node if node in tree.bodied else last
        middle = [c for c in tree.children.get(node, ()) if count[c] and abs(tree.pos[c][0] - tree.pos[node][0]) < MIDDLE]
        node = max(middle, key=lambda c: count[c], default=None)
    return last


def _legs(tree: Tree, trunk: list, pelvis: str) -> tuple:
    """({side: chain} of the front limbs, {side: chain} of the back ones, the node the front right (else left) limb
    hangs from) of the limbs leaving `trunk` before its head (anywhere on a one-node trunk), several-body limbs
    first: each side's farthest toward the head is its front limb and, when it has another, its nearest its back
    one; sides by world X."""
    sided, hung = {}, {}
    ahead = tree.pos[trunk[-1]] - tree.pos[pelvis]
    for at in trunk[:-1] or trunk:
        for limb in (b for c in tree.children.get(at, ()) if c not in trunk for b in _first_bodies(tree, c)):
            offset = (tree.pos[limb][0] - tree.pos[at][0]) * LEFT
            hung[limb] = at
            if abs(offset) >= MIDDLE:
                reach = float(np.dot(tree.pos[limb] - tree.pos[pelvis], ahead))
                sided.setdefault('left' if offset > 0 else 'right', []).append((reach, limb))
    sided = {side: [(r, l) for r, l in limbs if len(_chain(tree, l)) > 1] or limbs for side, limbs in sided.items()}
    front = {side: _chain(tree, max(limbs)[1]) for side, limbs in sided.items()}
    back = {side: _chain(tree, min(limbs)[1]) for side, limbs in sided.items() if len(limbs) > 1}
    first = (front.get('right') or front.get('left') or [None])[0]
    return front, back, hung.get(first, pelvis)


def _first_bodies(tree: Tree, node: str) -> list:
    """The first ragdoll body down each branch from `node` (itself when it is one)."""
    if node in tree.bodied:
        return [node]
    return [b for c in tree.children.get(node, ()) for b in _first_bodies(tree, c)]


def _chain(tree: Tree, limb: str) -> list:
    """`limb` and the ragdoll bodies down its first branch."""
    out = [limb]
    while True:
        below = [b for c in tree.children.get(out[-1], ()) for b in _first_bodies(tree, c)]
        if not below:
            return out
        out.append(below[0])


def parts_of(plan: dict) -> dict:
    """The rig table's `parts` (the mole rat's body part nodes -> our bones) of body_plan `plan`; a missing limb is
    the chest's (front) or the pelvis's (back)."""
    out = {'Root': 'Root', 'Pelvis': plan['pelvis'], 'SPINE1': plan['spine1'], 'SPINE2': plan['spine2'],
           'Chest': plan['chest'], 'Head': plan['head']}
    for side, letter in (('left', 'L'), ('right', 'R')):
        front = plan['front'].get(side) or [plan['chest']]
        front = (front + front[-1:] * 2)[:3]
        out.update({f'Front_{letter}Leg1': front[0], f'Front_{letter}Leg2': front[1],
                    f'Front_{letter}LegAnkle': front[2],
                    f'Back_{letter}Leg1': (plan['back'].get(side) or [plan['pelvis']])[0]})
    return out


def pose_bones(plan: dict) -> 'tuple | None':
    """The pose matcher's three ragdoll bones (pelvis, chest, upper limb) of body_plan `plan`, each another body when
    one would repeat; None with fewer than three bodies.
    See: docs/fork/fo4_auto_rig_plan.md#derive
    """
    limbs = [plan['front'].get('right'), plan['front'].get('left'), plan['back'].get('right'),
             plan['back'].get('left'), [plan['head']]]
    wanted = [[plan['pelvis']], [plan['chest']], [chain[0] for chain in limbs if chain]]
    out = []
    for picks in wanted:
        out += [next((b for b in [*picks, *plan['bodies']] if b not in out and b in plan['bodies']), None)]
    return tuple(out) if None not in out else None


def project_name(folder: str) -> str:
    """The rig's project name: `FNV` and `folder`'s names."""
    return 'FNV' + ''.join(p[:1].upper() + p[1:] for p in folder.lower().split('\\') if p != 'creatures')


def derived(folder: str, root: Path, parts: list, people: tuple) -> tuple:
    """(Rig, '') of skeleton folder `folder` (its FNV files under `root`, FNV body part data `parts`), or (None,
    why not); `people` is (whether one of its creatures talks, whether one carries a ranged weapon).
    See: docs/fork/fo4_auto_rig_plan.md#derive
    """
    talks, armed = people
    if not (Path(root) / 'skeleton.nif').is_file():
        return None, 'no skeleton'
    tree = read_tree(Path(root) / 'skeleton.nif')
    plan, roles = body_plan(tree, parts), clips(root, armed)
    poses = pose_bones(plan) if plan else None
    if poses is None or not roles:
        return None, 'fewer than three ragdoll bodies' if poses is None else 'no Idle clip'
    node = min((n for n in tree.order if n.startswith(FIRE_NODE)), key=lambda n: (n != FIRE_NODE, n), default=None)
    guns = ((GUN_ROLE, GUN_SLOT, (), node),) if node and GUN_ROLE in roles else ()
    roles = {r: kf for r, kf in roles.items() if r != GUN_ROLE or guns}
    parts_map = parts_of(plan)
    return Rig(folder=folder, project=project_name(folder), template=rigs()[TALKER if talks else MOLE_RAT].template,
               clips=roles, attacks={r: list(a) for r, a in ATTACKS.items() if r in roles}, parts=parts_map,
               default_part=parts_map['SPINE2'], pose_bones=poses, guns=guns), ''
