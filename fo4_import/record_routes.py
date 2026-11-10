"""Where each FO3/FNV record type goes in Fallout 4: the pipeline's dispatch table and the census checklist.

Kinds:
- SAME: the same signature in FO4, its fields converted.
- INTO: another FO4 type (CREA becomes NPC_; `target` names it). SCPT has none: it
  becomes Papyrus, attached by VMAD.
- OVERRIDE: an override of FO4's own singleton or settings records.
- SYSTEM: an FNV game system FO4 has no record for, rebuilt from quests,
  globals and scripts (caravan, casino, hardcore needs, reputation).
- ENGINE: data FO4's engine makes or holds elsewhere (skeleton ragdolls, interface icons).

See: docs/fork/fo4_pipeline.md#census
"""

SAME, INTO, OVERRIDE, SYSTEM, ENGINE = 'same', 'into', 'override', 'system', 'engine'

#: FO3/FNV signature -> (FO4 target signature, or '' for none; kind).
ROUTES = {
    'ACHR': ('ACHR', SAME), 'ACRE': ('ACHR', INTO), 'ACTI': ('ACTI', SAME), 'ADDN': ('ADDN', SAME),
    'ALCH': ('ALCH', SAME), 'ALOC': ('MUSC', INTO), 'AMEF': ('OMOD', INTO), 'AMMO': ('AMMO', SAME),
    'ANIO': ('ANIO', SAME), 'ARMA': ('ARMA', SAME), 'ARMO': ('ARMO', SAME), 'ASPC': ('ASPC', SAME),
    'AVIF': ('AVIF', SAME), 'BOOK': ('BOOK', SAME), 'BPTD': ('BPTD', SAME), 'CAMS': ('CAMS', SAME),
    'CCRD': ('MISC', INTO), 'CDCK': ('', SYSTEM), 'CELL': ('CELL', SAME), 'CHAL': ('', SYSTEM),
    'CHIP': ('MISC', INTO), 'CLAS': ('CLAS', SAME), 'CLMT': ('CLMT', SAME), 'CMNY': ('MISC', INTO),
    'CONT': ('CONT', SAME), 'CPTH': ('CPTH', SAME), 'CREA': ('NPC_', INTO), 'CSNO': ('', SYSTEM),
    'CSTY': ('CSTY', SAME), 'DEBR': ('DEBR', SAME), 'DEHY': ('', SYSTEM), 'DIAL': ('DIAL', SAME),
    'DOBJ': ('DOBJ', OVERRIDE), 'DOOR': ('DOOR', SAME), 'ECZN': ('ECZN', SAME), 'EFSH': ('EFSH', SAME),
    'ENCH': ('ENCH', SAME), 'EXPL': ('EXPL', SAME), 'EYES': ('HDPT', INTO), 'FACT': ('FACT', SAME),
    'FLST': ('FLST', SAME), 'FURN': ('FURN', SAME), 'GLOB': ('GLOB', SAME), 'GMST': ('GMST', OVERRIDE),
    'GRAS': ('GRAS', SAME), 'HAIR': ('HDPT', INTO), 'HDPT': ('HDPT', SAME), 'HUNG': ('', SYSTEM),
    'IDLE': ('IDLE', SAME), 'IDLM': ('IDLM', SAME), 'IMAD': ('IMAD', SAME), 'IMGS': ('IMGS', SAME),
    'IMOD': ('OMOD', INTO), 'INFO': ('INFO', SAME), 'INGR': ('INGR', SAME), 'IPCT': ('IPCT', SAME),
    'IPDS': ('IPDS', SAME), 'KEYM': ('KEYM', SAME), 'LAND': ('LAND', SAME), 'LGTM': ('LGTM', SAME),
    'LIGH': ('LIGH', SAME), 'LSCR': ('LSCR', SAME), 'LSCT': ('', ENGINE), 'LTEX': ('LTEX', SAME),
    'LVLC': ('LVLN', INTO), 'LVLI': ('LVLI', SAME), 'LVLN': ('LVLN', SAME), 'MESG': ('MESG', SAME),
    'MGEF': ('MGEF', SAME), 'MICN': ('', ENGINE), 'MISC': ('MISC', SAME), 'MSET': ('MUST', INTO),
    'MSTT': ('MSTT', SAME), 'MUSC': ('MUSC', SAME), 'NAVI': ('NAVI', OVERRIDE), 'NAVM': ('NAVM', SAME),
    'NOTE': ('BOOK', INTO), 'NPC_': ('NPC_', SAME), 'PACK': ('PACK', SAME), 'PERK': ('PERK', SAME),
    'PGRE': ('PGRE', SAME), 'PROJ': ('PROJ', SAME), 'PWAT': ('ACTI', INTO), 'QUST': ('QUST', SAME),
    'RACE': ('RACE', SAME), 'RADS': ('', ENGINE), 'RCCT': ('KYWD', INTO), 'RCPE': ('COBJ', INTO),
    'REFR': ('REFR', SAME), 'REGN': ('REGN', SAME), 'REPU': ('', SYSTEM), 'RGDL': ('', ENGINE),
    'SCOL': ('SCOL', SAME), 'SCPT': ('', INTO), 'SLPD': ('', SYSTEM), 'SOUN': ('SNDR', INTO),
    'SPEL': ('SPEL', SAME), 'STAT': ('STAT', SAME), 'TACT': ('TACT', SAME), 'TERM': ('TERM', SAME),
    'TREE': ('STAT', INTO), 'TXST': ('TXST', SAME), 'VTYP': ('VTYP', SAME), 'WATR': ('WATR', SAME),
    'WEAP': ('WEAP', SAME), 'WRLD': ('WRLD', SAME), 'WTHR': ('WTHR', SAME),
}
