"""The checks a gun built on its own mesh (weapon_routes step 3) must pass, measured before anything is written;
one failing puts it on its FO4 gun's own mesh instead:

- muzzle: its mesh has a ProjectileNode (FO4 fires from that node; without one the shots leave from where the
  template's muzzle sits, which may be inside or beside the FNV mesh);
- aim_hand: while a rifle aims, no more of FO4's right hand is in view (AIM_HAND_LIMIT) than in the rifle holds
  played and kept (gun_view.Arms.hand_share of its converted WPNIdleSighted, the camera lift applied). A pistol
  is aimed with its hand in view, so its share is reported only. A gun whose clips do not convert plays the
  template's own, so it has nothing of this to fail.

See: docs/fork/fo4_weapon_routes_plan.md#checks
"""

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.gun_view import Arms
from fo4_import.nif.gun import MUZZLE
from fo4_import.spike.gun_choice import STANCES
from fo4_import.spike.weapon_routes import anim_type

#: The most of a rifle's right hand in view while aiming: the played-and-kept rifle grips' 0-9% band's top.
AIM_HAND_LIMIT = 0.09
SIGHTED = 'WPNIdleSighted'


class WeaponChecks:
    """Runs the checks for one build's guns (`guns`: spike.guns.Guns), FO4's arms read once."""

    def __init__(self, guns):
        """Checks over `guns`; the first-person arms are read on first use."""
        self.guns, self.arms = guns, None

    def failed(self, rec: dict, chosen: tuple) -> tuple:
        """(why gun `rec` on choose()'s `chosen` fails, '' when it passes; {check: value})."""
        checks = {'muzzle': 'yes' if MUZZLE in chosen[2][3] else 'no'}
        if checks['muzzle'] == 'no':
            return 'no ProjectileNode in its mesh', checks
        kept = self.guns.preview(rec, chosen, SIGHTED)
        if kept is None or kept[0] is None or kept[1] is None:
            checks['clips'] = 'template'
            return '', checks
        share = self._arms().hand_share(kept[1], kept[0].lift or 0.0)
        checks['aim_hand'] = f'{share:.0%}' if share is not None else 'unread'
        if share is not None and share > AIM_HAND_LIMIT and STANCES.get(anim_type(rec)) == 'rifle':
            return f'{share:.0%} of the right hand in view while aiming', checks
        return '', checks

    def _arms(self) -> Arms:
        """FO4's first-person arms, read once."""
        if self.arms is None:
            self.arms = Arms(Archives(FALLOUT4_DIR / 'Data').read)
        return self.arms
