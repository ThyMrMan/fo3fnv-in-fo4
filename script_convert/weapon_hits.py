"""FO3/FNV weapon scripts acting on what the weapon hits, on Fallout 4.

FNV runs a weapon's `OnHit` block when the weapon hits something, `GetOwnerLastTarget` naming what it hit (the
boxing gloves' and cattle prod's Fatigue damage, the Zap Gloves' flash). Fallout 4 sends a weapon no hit; it runs a
weapon's object effect (EITM) on what it hits. So on Fallout 4 a script attached only to weapons with an `OnHit`
block converts as an effect script: the block is its `ScriptEffectStart`, `GetOwnerLastTarget` its target; the build
gives the weapon an enchantment running it (equipment).

See: docs/fork/fo4_pipeline.md#weapon-hits
"""

import re

from script_convert.target import is_fallout4

#: A script's OnHit block opener; FNV's name for the hit target.
ON_HIT = re.compile(r'^(\s*begin\s+)onhit\b', re.I | re.M)
OWNER_TARGET = re.compile(r'\bGetOwnerLastTarget\b', re.I)
EFFECT = 'ActiveMagicEffect'


def as_effect(xref, formid: str, sctx: str, extends: str) -> tuple:
    """(extends, source) of script `formid`, as an effect for a weapon's OnHit."""
    if not is_fallout4() or xref.attached_signatures(formid) != {'WEAP'} or not ON_HIT.search(sctx):
        return extends, sctx
    return EFFECT, OWNER_TARGET.sub('GetSelf', ON_HIT.sub(r'\1ScriptEffectStart', sctx))
