"""FNV's engine-played topics as Fallout 4 bark subtypes.

FNV's engine plays its reserved topics (Attack, Hit, AlertIdle, the player
reactions such as PLAYERINIRONSITES) itself, from every running quest's lines.
FO4's engine plays a quest's topic of the matching subtype the same way: one
topic per subtype per quest, in no branch. The engine keys a topic on its
SNAM code; DATA holds the category and the subtype's number, both taken from
CreationKit.exe's dialogue subtype table.

See: docs/fork/fo4_pipeline.md#barks
"""

import struct

#: FNV engine topic (reserved DIAL FormID) -> (its FNV EditorID, FO4 SNAM, category, subtype number).
FNV_BARKS = {
    '000000C5': ('PLAYERLOCKEDOBJECT', 'LOOB', 7, 96),
    '000000C6': ('PLAYERPICKPOCKET', 'PICT', 7, 97),
    '000000C7': ('PLAYERSTANDONFURNITURE', 'STOF', 7, 95),
    '000000C9': ('PLAYERSWINGMELEEWEAPON', 'SWMW', 7, 89),
    '000000CB': ('PLAYERFIREWEAPON', 'FIWE', 7, 90),
    '000000CD': ('PLAYERZKEYOBJECT', 'ZKEY', 7, 91),
    '000000CE': ('PLAYERJUMP', 'JUMP', 7, 92),
    '000000CF': ('PLAYERKNOCKOVEROBJECTS', 'KNOO', 7, 93),
    '000000D0': ('PLAYERINIRONSITES', 'PIRN', 7, 109),
    '000000D1': ('PLAYERDESTROYOBJECT', 'DEOB', 7, 94),
    '000000D5': ('IdleChatter', 'IDLE', 7, 104),
    '000000DC': ('Attack', 'ATCK', 3, 25),
    '000000DD': ('Hit', 'HIT_', 3, 28),
    '000000DE': ('Flee', 'FLEE', 3, 29),
    '000000DF': ('Steal', 'STEA', 3, 46),
    '000000E1': ('Yield', 'YIEL', 3, 47),
    '000000E2': ('AcceptYield', 'ACYI', 3, 48),
    '000000E3': ('Pickpocket', 'PICC', 3, 49),
    '000000E4': ('Assault', 'ASSA', 3, 50),
    '000000E5': ('Murder', 'MURD', 3, 51),
    '000000E6': ('PowerAttack', 'POAT', 3, 26),
    '000000E7': ('AssaultNoCrime', 'ASNC', 3, 52),
    '000000E8': ('MurderNoCrime', 'MUNC', 3, 53),
    '000000E9': ('PickpocketNoCrime', 'PICN', 3, 54),
    '000000EA': ('StealNoCrime', 'STFN', 3, 55),
    '000000EB': ('TrespassNoCrime', 'TRAN', 3, 56),
    '000000EC': ('FireExplosive', 'THGR', 3, 35),
    '000000ED': ('AvoidThreat', 'AVTH', 3, 31),
    '000000EE': ('NormalToCombat', 'NOTC', 5, 66),
    '000000EF': ('Death', 'DETH', 3, 32),
    '000000F0': ('CombatIdleChatter', 'TAUT', 3, 34),
    '000000F2': ('GuardTrespass', 'TRES', 3, 57),
    '000000F3': ('AlertToCombat', 'ALTC', 5, 69),
    '000000F4': ('NormalToAlert', 'NOTA', 5, 65),
    '000000F5': ('AlertToNormal', 'ALTN', 5, 68),
    '000000F6': ('CombatToNormal', 'COTN', 5, 70),
    '000000F7': ('CombatToLost', 'COLO', 5, 71),
    '000000F8': ('LostToNormal', 'LOTN', 5, 72),
    '000000F9': ('LostToCombat', 'LOTC', 5, 73),
    '00000104': ('AlertIdle', 'ALIL', 5, 63),
    '00000107': ('LostIdle', 'LOIL', 5, 64),
    '0000010E': ('ServiceRefusal', 'SERU', 6, 75),
    '00000111': ('Repair', 'REPA', 6, 76),
    '00000112': ('Travel', 'TRAV', 6, 77),
    '00000113': ('Training', 'TRAI', 6, 78),
    '00000116': ('BarterExit', 'BAEX', 6, 79),
    '0000011A': ('ObserveCombat', 'OBCO', 7, 84),
    '0000011B': ('Corpse', 'NOTI', 7, 85),
    '0000011C': ('TimeToGo', 'TITG', 7, 86),
    '0000011D': ('RepairExit', 'REEX', 6, 80),
    '00000120': ('Recharge', 'RECH', 6, 81),
    '00000121': ('RechargeExit', 'RCEX', 6, 82),
    '00000124': ('TrainingExit', 'TREX', 6, 83),
}


def kind(snam: str, category: int, number: int) -> tuple:
    """(DATA, SNAM) of an FO4 topic of subtype `snam`, as records.pack_dial takes them."""
    return struct.pack('<BBH', 0, category, number), snam.encode('ascii')


#: FNV engine topic -> (DATA, SNAM) of the FO4 bark topic a quest's lines of it become.
ENGINE_BARKS = {fid: kind(*row[1:]) for fid, row in FNV_BARKS.items()}
