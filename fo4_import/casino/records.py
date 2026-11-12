"""The casino's records in a build: the bank quest, a data quest per FNV casino, Caravan's decks, the menu's art.

FNV's casino (CSNO) becomes a start-game quest running F3NV_CasinoData with
the casino's rules as properties and its earnings and level as script state,
plus a level global dialogue conditions read (GetCasinoWinningStage); an
opponent's Caravan deck (CDCK) becomes a FormList of its cards' MISCs; the
player's owned cards and deck are two empty FormLists the bank fills, as
FNV's two lists on the player. The bank quest (F3NV_Casino) belongs to the
first plugin that writes it; a DLC over it adds its own casinos and decks.
FO3 has no CSNO or CDCK, so nothing is made.

See: docs/fork/fo4_casino_plan.md#records-built
"""

import struct
from pathlib import Path

from fo4_import.base.install import source_walk
from fo4_import.base.support_records import pack_global, pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.casino import movie
from fo4_import.nif.convert_static import fo4_texture, texture_source
from fo4_import.pipeline.export_index import export_file, export_records
from fo4_import.spike import records as R
from fo4_import.spike.say_topics import CASINO_KEY
from fo4_import.spike.statics import copy_texture
from tes5_import.base.tes5_reader import subrecords

#: derive_formid site of the casino's records (key: EditorID).
SITE = 'FNV casino'
QUEST, SCRIPT, PLAYER_SCRIPT, DATA_SCRIPT = 'FNV_Casino', 'F3NV_Casino', 'F3NV_CasinoPlayer', 'F3NV_CasinoData'
#: The property converted scripts reach the bank quest through (command_rows_fallout4).
PROPERTY = 'TES4Casino'
#: The player's Caravan cards: owned (FNV's PlayerCharacter+0x614) and the active deck (+0x618).
OWNED, DECK = 'F3NV_CaravanOwned', 'F3NV_CaravanDeck'
PLAYER = 0x14
#: CSNO DATA: reshuffle share, blackjack payout, 7 reel stops, decks, max winnings, chip, winnings quest, flags.
CSNO_DATA = struct.Struct('<ff7IIIIII')
STAYS_ON_SOFT_17 = 0x1
#: FalloutNV.exe's texts (GOG exe, oblivion_engine_extract --settings), by the bank's property; a GMST overrides.
TEXTS = {
    'BannedText': ('sGamblingBannedText', 'You have been banned from gambling at this casino.'),
    'BrokeText': ('sGamblingBrokeText', 'You must purchase chips before you can play this game.'),
    'MinWinText': ('sGamblingMinWinText', 'You have not won enough at this casino to play this game.'),
    'CardCountText': ('sCardCountText', 'You must have at least 30 cards to play Caravan.'),
    'TimeLeftText': ('sAntiCheatTimeRemainingText', 'Time Remaining: '),
}
#: Per game (1 blackjack, 2 roulette, 3 slots): its anti-cheat text.
ANTI_CHEAT = (('sBlackjackAntiCheatText',
               'The dealer is taking a minute to swap out the decks as an anti-cheating measure.'),
              ('sRouletteAntiCheatText',
               'The croupier is taking a minute to check the wheel for bias as an anti-cheating measure.'),
              ('sSlotAntiCheatText',
               'This machine appears to be taking a minute to reset itself as an anti-cheating measure.'))
#: The slot screen's texts in SlotsScreen.as's order: (FNV setting, FalloutNV.exe's default).
SLOT_TEXTS = (('sSpinText', 'Spin'), ('sBetMax', 'Bet Max'), ('sChipCountText', 'Chips: '),
              ('sCurrentBetText', 'Current Bet: '), ('sCasinoEarningsText', 'Earnings: '),
              ('sPayoutListText', 'Payout List'), ('sExit', 'Exit'), ('sYouWin', 'You win'), ('sYouLose', 'You lose'),
              ('sLuckyWinText', 'You feel lucky. You win'), ('sUnluckyLoseText', 'You feel unlucky. You lose'),
              ('sCasinoChipText', 'chip'), ('sPluralPlain', 's'))
#: The roulette screen's texts in RouletteScreen.as's order (RouletteMenu's buttons, spot names and results).
ROULETTE_TEXTS = (('sPlaceBetText', 'Place Bet'), ('sRemoveBetText', 'Remove Bet'), ('sFinsihBetText', 'Finish Bet'),
                  ('sIncreaseBetText', 'Increase Bet'), ('sDecreaseBetText', 'Decrease Bet'), ('sExit', 'Exit'),
                  ('sChipCountText', 'Chips: '), ('sCurrentBetText', 'Current Bet: '), ('sTotalBetText', 'Total Bet: '),
                  ('sCasinoEarningsText', 'Earnings: '), ('sBetText', 'Bet'), ('sPayoutText', 'Payout'),
                  ('sYouWin', 'You win'), ('sLuckyWinText', 'You feel lucky. You win'), ('sYouLose', 'You lose'),
                  ('sYouBreakEvenText', 'You break even'), ('sCasinoChipText', 'chip'), ('sPlural', '(s)'),
                  ('sFirstDozenText', 'First Dozen'), ('sSecondDozenText', '2nd Dozen'),
                  ('sThirdDozenText', '3rd Dozen'), ('sEvenText', 'Even'), ('sRedText', 'Red'),
                  ('sBlacktext', 'Black'), ('sOddtext', 'Odd'), ('sTwoToOneText', '2 to 1'))
#: FNV's anti-cheat wait after a load (iAntiCheatDuration, seconds).
ANTI_CHEAT_SECONDS = ('iAntiCheatDuration', 60)
#: Shown for a game whose screen is not built yet (ours, not FNV's).
NOT_BUILT = 'This game is not playable on Fallout 4 yet.'
#: Phase 0's test image: a card face the spike screen mounts (FNV path; staged under Textures/fnv).
SPIKE_TEXTURE = 'textures\\terminals\\nv_playingcards\\deckt\\cardt_c01.dds'


def _text(subs: list, tag: bytes) -> list:
    """Every `tag` subrecord's zero-terminated text."""
    return [data.rstrip(b'\0').decode('cp1252') for got, data in subs if got == tag]


def casino_fields(subs: list) -> dict:
    """An FNV CSNO's subrecords as its rules, chip and quest (FNV FormIDs), and art: slot symbols (ICON, wild
    last) and deck backs (ICO2)."""
    data = CSNO_DATA.unpack(dict(subs)[b'DATA'][:CSNO_DATA.size])
    return {'name': (_text(subs, b'FULL') or [''])[0], 'share': data[0], 'payout': data[1], 'stops': list(data[2:9]),
            'decks': data[9], 'max': data[10], 'chip': data[11], 'quest': data[12],
            'soft17_stays': bool(data[13] & STAYS_ON_SOFT_17), 'symbols': _text(subs, b'ICON'),
            'backs': _text(subs, b'ICO2')}


def deck_cards(subs: list) -> list:
    """An FNV CDCK's card FormIDs (CARD), in order (its DATA count is unreliable)."""
    return [struct.unpack('<I', data)[0] for got, data in subs if got == b'CARD']


def card_textures(subs: list) -> list:
    """An FNV CCRD's face and back textures (TX00, TX01)."""
    return _text(subs, b'TX00') + _text(subs, b'TX01')


def fo4_path(fnv_texture: str) -> str:
    """An FNV texture as the menu names it: its path under Textures, slashed."""
    return fo4_texture(fnv_texture).replace('\\', '/')


def texts(export_dir: Path) -> dict:
    """The bank's text and number properties: TEXTS, the anti-cheat texts and wait, the slot and roulette screens'
    texts; FalloutNV.esm's GMST over the engine's default."""
    gmst = {r.get('EditorID'): r.get('DATA.Value') for r in export_records(export_dir, 'GMST')}
    values = {prop: ('string', gmst.get(name) or default) for prop, (name, default) in TEXTS.items()}
    for prop, table in (('AntiCheatTexts', ANTI_CHEAT), ('SlotTexts', SLOT_TEXTS), ('RouletteTexts', ROULETTE_TEXTS)):
        values[prop] = ('strings', [gmst.get(name) or default for name, default in table])
    values['AntiCheatSeconds'] = ('float', float(gmst.get(ANTI_CHEAT_SECONDS[0]) or ANTI_CHEAT_SECONDS[1]))
    return {**values, 'NotBuiltText': ('string', NOT_BUILT)}


class Casino:
    """The build's casino: `quest` is the bank quest's FormID, None without casino or Caravan records."""

    def __init__(self, builder, export_dir: Path):
        """Read the source's CSNO, CDCK and CCRD; derive every FormID the casino writes."""
        self.builder, self.export_dir = builder, export_dir
        self.records = {sig: [(rec.form_id, subrecords(rec.body)) for rec, _ in source_walk(sig)]
                        for sig in (b'CSNO', b'CDCK', b'CCRD')}
        self.edids = {fid: (_text(subs, b'EDID') or [f'{fid:08X}'])[0]
                      for sig in (b'CSNO', b'CDCK') for fid, subs in self.records[sig]}
        self.quests = self._forms(b'CSNO', '')
        self.levels = self._forms(b'CSNO', 'Level')
        self.decks = self._forms(b'CDCK', '')
        self.quest = self._form(not builder.built, QUEST) if self.quests or self.decks else None

    def _form(self, owned: bool, key: str) -> 'int | None':
        """`key`'s FormID: derived if `owned`, else the master's (None: no master's)."""
        writer = self.builder.writer
        return writer.derive_formid(SITE, key) if owned else writer.from_master(SITE, key)

    def _forms(self, sig: bytes, suffix: str) -> dict:
        """{source FormID: form} of `sig` records' EditorID + `suffix` (_form).
        See: docs/fork/fo4_casino_plan.md#records-built
        """
        own = self.builder.ids.is_own
        found = {fid: self._form(own(fid), self.edids[fid] + suffix) for fid, _ in self.records[sig]}
        return {fid: form for fid, form in found.items() if form is not None}

    def named(self) -> dict:
        """{property: form} for converted scripts: PROPERTY the bank quest, each casino's and deck's FNV EditorID
        its data quest or FormList; {} without a casino."""
        if self.quest is None:
            return {}
        forms = {**self.quests, **self.decks}
        return {PROPERTY: self.quest, **{self.edids[fid]: form for fid, form in forms.items()}}

    def form_map(self) -> dict:
        """FNV casinos and decks to their forms; (CASINO_KEY, casino) to its level."""
        return {**self.quests, **self.decks, **{(CASINO_KEY, fid): glob for fid, glob in self.levels.items()}}

    def mine(self, fid: 'int | None') -> bool:
        """Whether FormID `fid` is this plugin's to write (no master already has it)."""
        return fid is not None and fid >> 24 == self.builder.writer.own_index

    def write(self, data_dir: Path) -> None:
        """Write the bank quest, the casinos' data quests and globals, the decks, and stage the art and movie."""
        if self.quest is None:
            return
        for fid, subs in self.records[b'CSNO']:
            if self.mine(self.quests.get(fid)):
                self._casino(fid, casino_fields(subs))
        for fid, subs in self.records[b'CDCK']:
            if self.mine(self.decks.get(fid)):
                self._deck(fid, deck_cards(subs))
        self.builder.scripts.used += [DATA_SCRIPT] if DATA_SCRIPT not in self.builder.scripts.used else []
        self.builder.counts['casino textures staged'] = self._textures(data_dir)
        if self.mine(self.quest):
            self._bank(data_dir)

    def _casino(self, fid: int, fields: dict) -> None:
        """Casino `fid`'s data quest running DATA_SCRIPT, and its level global (both its own plugin's)."""
        quest, level, edid = self.quests[fid], self.levels[fid], self.edids[fid]
        chip, winnings = self.builder.items.item(fields['chip']), self.builder.forms.get(fields['quest'])
        objects = {k: v for k, v in (('Chip', chip), ('WinningsQuest', winnings), ('LevelGlobal', level)) if v}
        values = {'CasinoName': ('string', fields['name']), 'Decks': ('int', fields['decks']),
                  'ReshuffleShare': ('float', fields['share']), 'Payout': ('float', fields['payout']),
                  'DealerStaysOnSoft17': ('bool', fields['soft17_stays']), 'ReelStops': ('ints', fields['stops']),
                  'MaxWinnings': ('int', fields['max']), 'Symbols': ('strings', [fo4_path(t) for t in fields['symbols']]),
                  'CardBacks': ('strings', [fo4_path(t) for t in fields['backs']])}
        self.builder.writer.add_record('GLOB', pack_global(level, f'FNV_{edid}Level'))
        vmad = quest_fragments('', [], scripts=[(DATA_SCRIPT, objects, values)])
        self.builder.writer.add_record('QUST', pack_script_quest(quest, f'FNV_{edid}', vmad))
        self.builder.counts['casino data quests'] += 1
        self.builder.counts['casino without its chip or winnings quest'] += len(objects) < 3

    def _deck(self, fid: int, cards: list) -> None:
        """Deck `fid` as a FormList of its cards' MISCs (its own plugin's)."""
        made = [self.builder.items.item(card) for card in cards]
        self.builder.writer.add_record('FLST', R.pack_flst(self.decks[fid], f'FNV_{self.edids[fid]}',
                                                           [m for m in made if m]))
        self.builder.counts['Caravan decks'] += 1
        self.builder.counts['Caravan deck cards left out'] += made.count(None)

    def _bank(self, data_dir: Path) -> None:
        """The bank quest: F3NV_Casino with the texts and the player's two card lists, its player alias; the
        spike's card face, the menu movie and our menus' translation files."""
        writer, own = self.builder.writer, self.builder.writer.derive_formid
        lists = {'Owned': own(SITE, OWNED), 'Deck': own(SITE, DECK)}
        for name, fid in zip((OWNED, DECK), lists.values()):
            writer.add_record('FLST', R.pack_flst(fid, name, []))
        values = {**texts(self.export_dir), 'SpikeImage': ('string', fo4_path(SPIKE_TEXTURE))}
        vmad = quest_fragments('', [], aliases=[(0, self.quest, [(PLAYER_SCRIPT, {}, {})])],
                               scripts=[(SCRIPT, lists, values)])
        writer.add_record('QUST', R.pack_qust(self.quest, QUEST, '', 0, [], 'Player', PLAYER, vmad))
        self.builder.scripts.used += [s for s in (SCRIPT, PLAYER_SCRIPT) if s not in self.builder.scripts.used]
        installed = movie.install(data_dir)
        self.builder.counts['casino menu movie installed'] = installed
        self.builder.counts['casino menu movie missing (no Flex SDK)'] = 1 - installed

    def _textures(self, data_dir: Path) -> int:
        """Stage every texture the casinos and cards name (slot symbols, deck backs, card faces), and the
        spike's; how many the export has (one missing is counted)."""
        paths = {SPIKE_TEXTURE} | {texture_source(t) for _, subs in self.records[b'CSNO']
                                   for t in _text(subs, b'ICON') + _text(subs, b'ICO2')}
        paths |= {texture_source(t) for _, subs in self.records[b'CCRD'] for t in card_textures(subs)}
        found = [p for p in sorted(paths) if export_file(self.export_dir, p.replace('\\', '/')).is_file()]
        for path in found:
            copy_texture(self.export_dir, data_dir, path)
        self.builder.counts['casino texture missing from the export'] = len(paths) - len(found)
        return len(found)
