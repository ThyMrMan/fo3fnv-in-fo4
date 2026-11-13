# Casino games and Caravan on Fallout 4 (plan)

**Status:** planned 2026-11-04; phases 0-2 built 2026-11-08, phase 3 (roulette) 2026-11-11 (see each
phase's "Built" note). Status lines live only in
[ROADMAP.md](ROADMAP.md#fo4-next). This plan replaces the design sketch in
[fo4_build_next.md item 13](fo4_build_next.md#casino); its findings are
folded in here and checked against the data.

**Scope:** blackjack, roulette and slots in the five Strip and Primm
casinos and the Sierra Madre, and Caravan, on a **flat 2D table screen**.
Full 3D tables (dealers, chips and cards on the felt) are a later phase;
[what that needs](#phase-3d) is noted at the end.

**Sources used:**
- `export/FalloutNV.esm`, `export/DeadMoney.esm`, `export/CaravanPack.esm`
  (scripts, refs, quests, dialogue);
- the binary ESMs, for the five record types the exporter cannot decode
  (read with a scratch parser against `wbDefinitionsFNV.pas` 8196-8360);
- the FNV decompile, `references/fnv_decomp/src/` (cited by file and
  `@fnv` address; read, never copied);
- xNVSE and JIP for menu IDs and field layouts;
- the Prima guide (`FNV_Guide/...Prima.Official.Guide_djvu.txt`, by line)
  and the wiki dump (`FalloutWiki/fallout_pages_current.xml`, by line).

## Contents

1. [Inventory](#inventory)
2. [What the Fallout 4 build does today](#today)
3. [How FNV's engine runs the games](#rules)
4. [The 2D design](#design)
5. [Phases, sizes, order, tests](#phases)
6. [The 3D phase (later)](#phase-3d)
7. [Drift from FNV](#drift)
8. [Open questions](#questions)
9. [Main decisions and biggest risks](#summary)

---

## <a id="inventory"></a>1. Inventory

### <a id="inv-records"></a>1.1 The five FNV-only record types

None of these has a Fallout 4 record type. The exporter prints each as
`# Unknown record type` with only subrecord sizes, so the values below come
from the binary ESMs.

| Type | FalloutNV | Dead Money | What it is |
|---|---|---|---|
| CSNO (casino) | 5 | 1 | House rules, chip, winnings quest, table art |
| CHIP (casino chip) | 5 | 1 | The chip item |
| CMNY (Caravan money) | 6 | 0 | NCR dollars and Legion coins as items with a cap value |
| CCRD (Caravan card) | 270 | 54 | One card: suit, value, face and back textures |
| CDCK (Caravan deck) | 13 | 0 | An opponent's deck: a list of cards |

**CSNO, every field** (`DATA` is 56 bytes: shuffle share, blackjack payout,
7 reel stops, decks, max winnings, chip, winnings quest, flags):

| EditorID | FormID | Name | Decks | Reshuffle at | BJ payout | Dealer on soft 17 | Max winnings | Chip | Winnings quest |
|---|---|---|---|---|---|---|---|---|---|
| AtomicWranglerCasinoData | 00144C42 | Atomic Wrangler | 1 | 35% | 1.2 (6:5) | stands | 5,000 | AtomicWranglerChip 00144C3E | vCasinoCompsAtomicWrangler 001614E9 |
| VikkiVanceCasinoData | 00144C41 | Vikki & Vance | 2 | 25% | 1.5 | hits | 2,500 | VikkiVanceChip 00144C3D | vCasinoCompsVikkiAndVance 00161E96 |
| UltraLuxeCasinoData | 00144C40 | Ultra-Luxe | 3 | 40% | 1.5 | stands | 15,000 | UltraLuxeChip 00144C3C | VCasinoCompsUltraLuxe 00160301 |
| TheTopsCasinoData | 00144C3F | The Tops | 4 | 35% | 1.5 | stands | 10,000 | TheTopsChip 00144C3B | vCasinoCompsTheTops 00145F88 |
| GomorrahCasinoData | 00140521 | Gommorah (sic) | 3 | 20% | 1.5 | hits | 9,000 | GomorrahChip 00139FE0 | vCasinoCompsGomorrah 001607FF |
| SierraMadreCasinoData (DM) | 0100C4D6 | Sierra Madre | 4 | 35% | 1.5 | stands | 10,000 | NVDLC01SierraMadreChip 01011236 | NVDLC01CasinoComps 0100C4D4 |

- **Reel stops** are `2,2,2,2,2,2,2` in all six (they must total 14; the
  7th is the wild).
- **Art paths** per casino: 6 chip NIFs and a roulette chip
  (`terminals\NV_Blackjack\NV_Blackjack-Chip_*.NIF`), the slot machine
  minigame NIF (`-Minigame`, `-Minigame-Gom`, `-Minigame-Generic`, DM's
  own), the blackjack table (`NV_Blackjack-Table{,A,G,U,V}.NIF`), the
  roulette table, 7 reel symbols (`NV_SlotMachine-Symbol1..7.dds`, the
  wild is Symbol5), and 4 card backs (`DeckB`, `DeckG`, `DeckT`, `DeckU`,
  `DeckS`).
- The soft-17 flag is named "Dealer Stay on Soft 17" in xEdit; the wiki
  agrees (Gomorrah and Vikki & Vance hit soft 17; W "Blackjack" L3071189).

**CHIP:** AtomicWranglerChip, VikkiVanceChip, UltraLuxeChip (all
`clutter\casino\PokerChip03.nif`), TheTopsChip (`PokerChip02`),
GomorrahChip (`PokerChip01`), NVDLC01SierraMadreChip (own NIF). Each has its
own Pip-Boy icon. No value field: a chip is worth 1 cap at the cashier.

**CMNY:** MoneyNCR100 (worth 40 caps), MoneyNCR20 (8), MoneyNCR5 (2),
MoneyLegion25 "Legion Aureus" (100), MoneyLegion1 "Legion Denarius" (4),
MoneyLegion1Mangled (2). These are FNV's paper money and coins; Caravan
counts them as funds, cashiers take them.

**CCRD:** six 54-card sets (52 + 2 jokers), every card value 2 caps and
script `CardAddToPlayerScript` 0015D7B0 (DM: `NVDLC01CardAddToPlayerScript`
0101544F):

| Set | EditorID suffix | Mesh | Face textures | Count |
|---|---|---|---|---|
| Standard (red back) | `b` (e.g. CardSpades10b) | `NV_Caravan-CardB.NIF` | `DeckT\cardT_*` (sic) | 54 |
| The Tops | `Tops` | `-CardT` | `DeckT` | 54 |
| Ultra-Luxe | `UltraLuxe` | `-CardU` | `DeckU` | 54 |
| Gomorrah | `Gomorrah` | `-CardG` | `DeckG` | 54 |
| Lucky 38 | `Lucky38` | `-CardL` | `DeckL` | 54 |
| Sierra Madre (DM) | `SM` | `NVDLC01_Caravan-CardS` | `DeckS` | 54 |

**CDCK** (card count read from the CARD list; the DATA count is wrong in 6):

| EditorID | FormID | Cards | Sets used | Opponent |
|---|---|---|---|---|
| CaravanDeckRingo | 0015D7A2 | 30 | Tops | GSRingo 00104C7C; also Cliff Briscoe 0008CD27 and Keith |
| CaravanDeckNobark | 0017B41B | 41 | Tops 30, UL 6, Gom 3, L38 2 | NobarkNoonan 0008CD23 |
| CaravanDeckMayes | 00165AC5 | 40 | Tops 33, std 7 | VCFHCarlMayes 00120DCE |
| CaravanDeckErwin | 00165AC4 | 40 | Tops 32, std 8 | VStreetJakeErwin 00112642 |
| CaravanDeckCrocker | 00165AC3 | 40 | Tops 34, std 6 | VStreetDennisCrocker 00112640 |
| CaravanDeckJules | 00169E23 | 54 | std | VOVNVJules 0013E307 |
| CaravanDeckLacey | 0016ACE9 | 60 | all five | vMOLacey |
| CaravanDeckNash | 001649D1 | 52 | Tops 38, std 14 | PrimmJohnsonNash 000DA729 |
| CaravanDeckLittleBuster | 00176988 | 50 | all five | 1ELittleBuster 000F56FC |
| CaravanDeckDaleBarton | 00163487 | 40 | Tops | FortDaleBarton 0011FBC3 |
| CaravanDeckIsaac | 0016348A | 50 | Tops | GunRunnerIsaac 000ED4E2 |
| CaravanDeckKlamathBob | 00163489 | 40 | Tops | none (cut player) |
| CaravanDeckMelissa | 00163488 | 35 | Tops | none (cut player) |

No deck lists the same card record twice, so each fits a FormList.

### <a id="inv-tables"></a>1.2 The tables and machines

All playable pieces are **ACTI** with an activation script. Models are
`clutter\casino\CardTable01.NIF` (every blackjack table) and
`RouletteTable01.NIF` (every roulette table) unless noted.

| Casino (cell) | Blackjack (base, refs) | Roulette | Slots |
|---|---|---|---|
| Atomic Wrangler (FreesideAtomicWrangler) | BlackjackTableAtomicWrangler 0016150D ×1 | RouletteTableAtomicWrangler 0016150B ×1 | vWranglerSlot01 0016150C ×10, vWranglerSlot02 0016150A ×4 |
| Vikki & Vance (VikkiAndVance) | BlackjackTableVikkiAndVance 0016206C ×3 | VikkiAndVanceRouletteTable 0016206F ×2 | vVikkiAndVanceSlot01 00162026 ×39, Slot02 00162028 ×23 |
| Gomorrah (Gomorrah01) | BlackjackTableGomorrah 00161E44 ×4 | GomorrahRouletteTable 00161E43 ×3 | vGomorrahSlot01 00139FE2 ×10 (`Slot_Machine01Gomorrah.NIF`) |
| The Tops (TOPSCasino) | BlackjackTableTheTops 00145C84 ×3 | RouletteTableTheTops 0014C136 ×1 | vTopsSlot01 0015CB95 ×8 (1 in TOPSRestaurant) |
| Ultra-Luxe (ULCasino) | BlackjackTableUltraLuxe 001614D2 ×6, 3 playable | RouletteTableUltraLuxe 001614D8 ×4, 1 playable | none |
| Sierra Madre (NVDLC01Casino) | NVDLC01BlackjackTable 0100D95A ×1 | NVDLC01RouletteTable 0100C4CF ×1 | NVDLC01Slot01 0100E1DE ×4 |

- Total playable placements: **19 blackjack, 12 roulette, 102 slots**
  in FNV (Ultra-Luxe's 3+3 "static" copies disabled at load by
  `SetDestroyed 1` on six refs), plus 1/1/4 in Dead Money.
- The Lucky 38's tables and slots, and every craps table, are props (STAT).
- Furniture: TheTopsBlackjackTable01Stool 00151DCA (15 refs),
  UltraLuxeBlackjackTable01Stool 001614DD (1), TopsSlotMachineStool01L
  0015AB8C (72), NVRouletteDealerMarker01 0011FC5D (9).
- Dealers (NPC_): vTopsBlackjackDealer01 00151DC8, VTopsDealer/02/03/04,
  VTopsRouletteDealer 00152617, VWranglerDealer2 00161509,
  vGOMVarDealersRoulette 0017153A, VMS18WhiteGloveCF 00118347; Dead Money
  uses holograms.

### <a id="inv-scripts"></a>1.3 Scripts

**Openers** (object scripts; `<cmd> <CSNO> <min bet> <max bet> <min winnings>`):

| Casino | Blackjack | Roulette | Slots |
|---|---|---|---|
| Atomic Wrangler | BlackjackTableAtomicWranglerScript 0016150F (1-200) | RouletteTableAtomicWranglerScript 0016150E (1-200) | SlotMachineWranglerScript 00161511 (1-40) |
| Vikki & Vance | vVikkiAndVanceBlackjackSCRIPT 0016206D (200) | VikkiAndVanceRouletteTableSCRIPT 0016206E (200) | vVikkiVanceSlotScript 0016318E (25) |
| Gomorrah | vGomorrahBlackjackSCRIPT 00161E41 (200) | GomorrahRouletteTableSCRIPT 00161E42 (200) | vGomorrahSlot01Script 00139FE1 (60) |
| The Tops | BlackjackTableTheTopsScript 00145C85 (200) | RouletteTableTheTopsScript 0014C137 (200) | SlotMachineTheTopsScript 00144F31 (75) |
| Ultra-Luxe | BlackjackTableUltraLuxeScript 001614D1 (200) | RouletteTableUltraLuxeScript 001614D7 (200) | none |
| Sierra Madre | NVDLC01BlackjackTableScript 0100D959 (200) | NVDLC01RouletteScript 0100C4CE (100) | NVDLC01SlotMachineScript 0100E1DD (25) |

Each one, for the player only, shows the casino's floor-manager message
while `<comps quest>.bFloorManagerIncoming` is set (Atomic Wrangler: while
`Banned`, `AtomicWranglerSlotsMsg`; Dead Money: while the power is off or
`bBanned`), and otherwise opens the game. `vVikkiVanceSlotScript` checks
**Gomorrah's** flag, an FNV bug kept as authored.

**Comps quests** (poll `GetCasinoWinningsLevel <CSNO>` for levels 1-4,
flags `SmallFry`, `BigWinner`, `Whale`, `Banned`):
- vCasinoCompsTheTopsScript 00145F89, vCasinoCompsUltraLuxeScript
  001614D4, vCasinoCompsGomorrahSCRIPT 001607FE,
  vCasinoCompsVikkiAndVanceSCRIPT 00161E90: each level gives the floor
  manager a dialogue package (`AddScriptPackage` + `evp`); level 4 at
  Tops, Ultra-Luxe or Gomorrah fires `AddAchievement 29` when the other
  two are already banned.
- vCasinoCompsAtomicWranglerScript 00161510: no floor manager; adds the
  comp items and plays a `GAMESlotsWin*`/`GAMESlotsLose` sound itself.
- NVDLC01CasinoCompsScript 0100C4CD (DM): messages, a note and
  `NVDLC01FinalCompVoucher` at level 3; `bBanned` at 4.
- Quest flags: vCasinoCompsGomorrah starts game-enabled (DATA flags 17);
  vCasinoCompsTheTops does not (flags 0). FNV's menu enables the CSNO's
  quest itself when a new level is reached ([5.](#rules-bank)), so the
  converted opener must start it.

**Others:** vDialogueCasinoCashierSCRIPT 0017B77D (chip and money counts
for the cashier topics); TopsPlayersSuiteTriggerSCRIPT 00151E7F; the stool
scripts 00151DCC, 001614DE; dealer scripts vTopsBlackjackDealer01Script
00151DCB, NVRouletteDealerScript 001210BF, NVRouletteDealerScript2
00127965, RouletteDealerMarkerScript 001210C1, VMS18RouletteDealerSCRIPT
0017B418; CasinoBaseLightScript 00177D69; DM NVDLC01ChipRewardSCRIPT
0101340E (100 chips every 3 days into Elijah's drop box),
NVDLC01CasinoSwitchScript 0100A59A.

**Caravan:** `CardAddToPlayerScript` (picked up or added → `AddCardToPlayer`,
then the item goes away), vCaravanQuestScript 00157F75 (`iMayes`, `iLacey`,
`iNashCaravanGames`: the per-merchant game counts), CaravanDeckScript
0015F8C4, ChallengeCaravanWinSCRIPT 0016577F, ChallengeCaravanMasterSCRIPT
0016BA4D.

**Challenges:** ChallengeBlackjackSCRIPT 0016577B, ChallengeRouletteSCRIPT
00165779, ChallengeSlotsSCRIPT 0016577A.

### <a id="inv-quests"></a>1.4 Quests, dialogue, items, messages

| Piece | Records |
|---|---|
| Winnings quests | the six in the CSNO table; none has stages (levels live in the engine) |
| Cashier quest | vDialogueCasinoCashier 00144F34, 34 INFOs; cashiers vCashierTheTops 00144F32, VMS18WhiteGloveCashier 001584D8, vGOMCashier 00160802, PrimmCashier 001629D3, VFSAtomicWranglerCashier 00158616 (faction VCasinoCashierDialogueFaction 001584D7). Buy 1/5/20/100/500/1000 chips; the chip given branches on the cashier's faction; topics 037-039 cash out. DM: NVDLC01HologramCashierCasino 0100C4D0 trades pre-war money. |
| Comps dialogue | floor-manager GREETING INFOs: Gomorrah 001607FD, 0016083F, 00160840, 00160841 (ban); Tops 00152325, 00152326, 00152327 (suite key), 00151E7B (ban); Ultra-Luxe 001602FB-FE; V&V 00163183-85. INFO counts: Tops 10, Ultra-Luxe 6, Gomorrah 4, DM 13. Other chip grants: Gomorrah bosses (vGomorrahBossChips, 50), Benny (0011985F, 00119D34; 250 Tops chips). |
| Caravan quest | vCaravanQuest 00157F76 (43 INFOs, faction CaravanPlayerFaction 00157F77). 17 INFOs make 23 `ShowCaravanMenu` calls for 11 opponents; Ringo's rules lesson is in VFreeformGoodsprings (0015D79F gives the CaravanDeck MISC 0015F8C3 and note CaravanRulesNote 00162C93). |
| Card sources | LVLI RandomCaravanBaseCards 00171CF2 (all 270) in 10 vendor chests, 5 loot sacks, 2CPoindexter, 1EKeith, 2 prospector corpses; CONT CaravanSpareDeck 0015D8B0 (54 Tops cards); DM: 21 placed SM cards. 342 card and money entries sit in NPC inventories. |
| Challenges (CHAL) | NVChallengeBlackjack 00165775 "Double Down", NVChallengeRoulette 00165776 "Little Wheel", NVChallengeBandit 00165774 "One Armed Bandit" (10 each); NVChallengeCaravanWin 00165777 (3), NVChallengeCaravanMaster 0016BA4E (27), NVChallengeCaravanLost 00165778 (5 losses); DM NVDLC01ChallengeDeadMansHand 010134FB |
| Messages (MESG) | HelpBlackjack 00172094, HelpRoulette 00172095, HelpSlots 00172096, HelpCaravanBetting/DeckBuilding/StartingCaravans/ContractWar 00000186-189; GomorrahFloorManagerMsg 00161E40, TheTopsFloorManagerMsg 00152330, UltraLuxeFloorManagerMsg 001614D3; AtomicWranglerSlotsMsg 001614E6; DM NVDLC01SlotsMsg 0100E208, NVDLC01CasinoCompsMessage 0100FE2F, NVDLC01CasinoCompsHugeMessage 0101025A, NVDLC01TableClosedMessage 0100EB95 |
| Comp items | Gambler outfits and hats (ARMO), suite keys VTopsPlayersSuiteKey, VUltraLuxePlayersSuiteKey; all ordinary records that already convert |
| Perks, effects, globals | none tied to gambling; Luck itself is the only input (Lucky shades +1, the Luck implant) |
| GMST | none of the casino settings is overridden by any plugin; all are engine defaults (names in [3.](#rules-gmst)) |
| Dead Money chips as money | 623 placed SM chip refs; 56 of 77 RCPE (vending machine) recipes take chips; RecipeNVDLC01FinalComp turns the voucher into 1,000 chips |
| CaravanPack.esm | the pre-order item pack only (14 records: armor, shotgun, ammo, kits); no Caravan content |

### <a id="inv-ui"></a>1.5 FNV's menus

From `Fallout - Misc.bsa\menus\`: `black_jack_menu.xml`, `roulette_menu.xml`,
`slot_machine_menu.xml`, `caravan_menu.xml` and its `caravan_bet_menu`,
`caravan_builddeck_menu`, `caravan_game_menu`, `caravan_results_menu`
(each also in `prefabs\`), and `prefabs\card_info.xml`.

- Menu IDs (`fallout\interface\interface.cpp`; xNVSE `GameUI.h`):
  SlotMachine 1080, BlackJack 1081, Roulette 1082, Caravan 1083.
- The XML holds only the buttons and text. The playing surface is a live 3D
  scene of `meshes\terminals\nv_*` NIFs (102 files: tables with their own
  camera and light, dealer, hands, chips, reels, Caravan tracks and money),
  lit in real time.
- Art for a 2D screen, all in the user's FNV archives: card faces (54 per
  set in `textures\terminals\nv_playingcards\deck{b,c,g,l,t,u}`, plus DM's
  `deckS`), card backs, 7 slot symbols, the blackjack felt
  (`NV_Blackjack-Table03*`, top-down), the Caravan table wood
  (`NV_Caravan-Table01..03`), and 41 `GAME*` sounds.

---

## <a id="today"></a>2. What the Fallout 4 build does today

**Nothing is playable.** Activating a table, roulette wheel or slot
machine does nothing (unless the floor manager is on his way, when his
message shows). Asking a Caravan player to play gives the dialogue line
and nothing more.

- **Records:** `fo4_import/record_routes.py:23-25` labels CCRD, CDCK,
  CMNY and CSNO `SYSTEM` ("rebuilt from quests, globals and scripts") and
  CHIP `('MISC', INTO)`. The labels are not acted on: the converter table
  (`fo4_import/pipeline/converters.py:12-18`) has none of the five, so
  **no record of any of them is written, chips included**. Tables and
  machines convert as ordinary ACTI (`fo4_import/spike/activators.py`).
- **Scripts:** the four openers (`ShowBlackjackMenuParams`,
  `ShowRouletteMenuParams`, `ShowSlotMachineMenuParams`,
  `ShowCaravanMenu`) have no command row and become `;NE: TODO:` markers
  (41 sites, [script_markers.md](script_markers.md) row 17). In the
  2026-10-31 script stage: 5 blackjack, 5 roulette, 4 slot markers, and
  Caravan markers in TIF fragments for 11 decks. `AddCardToPlayer` is a
  marker too. `GetCasinoWinningsLevel` emits `0`
  (`script_convert/constants_falloutnv.py:250-251`), so no comp ever
  comes.
- **Example** (`FALLOUTNV_vGomorrahSlot01Script.psc`): the CSNO property is
  `ObjectReference GomorrahCasinoData`, never filled; `OnActivate` shows
  `GomorrahFloorManagerMsg` or reaches the marker.
- **Empty properties** (`py -3.14 -m tools.validate.preflight --fo4
  ".../FalloutNV.esm" --audit properties --full`, run 2026-11-04): 76
  casino or Caravan property lines out of 1,172:
  - 19 `*CasinoData` (every opener and the five comps scripts);
  - 50 `*Chip` (cashier and boss TIF fragments);
  - 1 `RandomCaravanBaseCards` (its LVLI holds only cards, so it is empty);
  - 4 `GAMESlots*` sounds and 2 `RouletteDealerPackage1` (timer pass).
- <a id="items-built"></a>**Cards, money and chips as items (built
  2026-11-06, not played).** Phase 1's record rows for CCRD, CMNY and CHIP
  ([design](#design)): each is a MISC with FNV's name, model, bounds, script
  and value (a chip has none), carrying `F3NV_CaravanCard`,
  `F3NV_CaravanMoney` or `F3NV_CasinoChip` (`items.CASINO_ITEMS`). The export
  holds these types' field sizes only, so the build reads them from the
  plugin (`source_walk`). Before, they were the build's 281 `item skipped
  (not exported)`: FNV's inventories, lists and recipes name cards 324
  times (`RandomCaravanBaseCards` 270, `CaravanSpareDeck` 54) and money 116
  times (NCR dollars and Legion coins in loot lists, containers, 3 NPCs, a
  recipe). They place too (`converters.PLACED`): Dead Money's placed chips
  and cards. A form that is no item type is now counted by its type
  (`item skipped (not an item: <type>)`). `RandomCaravanBaseCards` lists
  270 cards, past FO4's 255 (LLCT is a byte), so a list that long becomes
  equal parts (two of 135, `FNV_<list>_Part<n>`, FNV's flags) the list
  names once each (`items._parts`): a pick-one list still picks every card
  alike. The decks (CDCK), casinos (CSNO)
  and the games are still to build.
- **Dead Money** (`F3NV - Dead Money`, built 2026-11-04): the Sierra Madre
  casino converts as a place, with its scripts; its games are the same
  markers, and no SM chip record exists, so the vending machines' chip
  recipes have no ingredient.
- **Already there to build on:** MESG conversion (`fo4_import/spike/attach.py:256`),
  caps as FO4's own `Caps001` (0x0000000F), the challenge system
  ([challenges](fo4_pipeline.md#challenges), 61 of 105 built), FNV
  skills as actor values ([Pip-Boy tabs](fo4_pipboy_tabs.md)), and
  F3NV.dll's Scaleform work on vanilla menus (`tes_runtime/fo4_condition/pages.cpp`,
  `pipboy.cpp`). The project has **never shipped a custom menu or an AS3
  movie**; the Python SWF writer (`tools/generators/gen_morrowind_menu_swf.py`)
  writes AS2 only.

---

## <a id="rules"></a>3. How FNV's engine runs the games

Everything here is the engine's (FalloutNV.exe), paraphrased from the
decompile; **[V]** read in code, **[I]** inferred. Guide and wiki figures
are noted where they agree or differ.

### <a id="rules-open"></a>3.1 Opening a game [V]

`fallout_shared\tesscriptfunctions.cpp`: the three casino commands take
(casino, min bet, max bet, min winnings) and open the menu
(blackjack `0x00733630`, roulette `0x007bbe20`, slots `0x007c0a40`;
blackjack drops the min-winnings argument). Before the menu opens:
1. find or make the player's record for this casino:
   {casino, net earnings, level} in a list on the player
   (`PlayerCharacter+0x610`), saved with the game;
2. **anti-cheat:** after a save is loaded, every game refuses for
   `iAntiCheatDuration` seconds (wiki: 60) with "the dealer is changing
   the deck" text (`0x00969b80`, `0x00969ac0`);
3. refuse if earnings ≥ the CSNO's max winnings (`sGamblingBannedText`);
4. refuse if the player has fewer of the casino's chip than the min bet
   (`sGamblingBrokeText`);
5. refuse if a min-winnings requirement is set and not met.

The screen shows the casino name, earnings, chip count and current bet.
Chips change in the menu; on exit the difference is added to or removed
from the player's inventory with the usual item messages.

### <a id="rules-bj"></a>3.2 Blackjack [V]

`blackjackmenu.cpp`, `blackjackmenu_ctx_variant.cpp`.
- **Shoe:** 52 × decks (4 at most). Reshuffle when fewer than
  decks × 52 × reshuffle share remain, or fewer than 5. Deck *j* uses the
  CSNO's card back *j*.
- **Dealer:** hits below 17; hits soft 17 unless the flag is set (the
  "soft" test is only "has an ace"). Stops at 7 cards.
- **Player:** hit, stay; double on the first action (one card, then
  stand); split once on two cards of equal rank (each hand gets one card,
  then they are played in turn); surrender before any hit for half the
  bet. No insurance. 7 cards auto-stand.
  - Guide/wiki: no split on queens or kings, and only the first split
    hand may double (W L3071189). The split check (`0x007395a0`) compares
    rank and allows queens and kings ([blackjack built](#blackjack-built)).
- **Payouts:** natural 21 pays bet × CSNO payout, rounded (3:2, 6:5 at
  the Atomic Wrangler); a win pays 1:1; push returns the bet; a split
  hand reaching 21 also pays as a natural.
- **Bets:** min/max from the opener, capped by chips held. Steps: +1
  below 10, +5 below 40, +10 below 100, +25 below 400, +100 below 1,500,
  then +500 ("Bet max" jumps to the cap).
- **Luck** (AV Luck, `BJDeck::DrawCard 0x00739090`): the first face-down
  cards are random. At Luck ≥ 6, each **player** draw looks at
  (Luck − 5) random candidates and takes the one that brings the hand
  nearest 21 without busting (or toward 11 on a low total), and the win
  text becomes `sLuckyWinText`. At Luck ≤ 4 the **dealer** gets the same
  help with (5 − Luck) candidates (`sUnluckyLoseText`). Luck 5 is fair.

### <a id="rules-roulette"></a>3.3 Roulette [V]

`roulettemenu*.cpp`: American wheel, 38 pockets (37 stands for 00), a
uniform draw; 159 bet spots; the max bet covers all bets on one spin.

| Bet | Pays |
|---|---|
| Straight (including 00) | 35:1 |
| Split | 17:1 |
| Street; 0/00 with a neighbor | 11:1 |
| Corner | 8:1 |
| Top line 0-00-1-2-3 | 6:1 |
| Six line | 5:1 |
| Dozens, columns | 2:1 |
| Red/black, odd/even, 1-18/19-36 | 1:1 |

- A winning bet returns (odds + 1) × stake.
- **Luck** changes only the win text, not the spin (wiki agrees; Prima
  says "slightly"). [V: phase 3 read the spin end to end.]
- **0 pays only straight up, on red, on even and in the third column; 00
  on black, odd and the first column** (FNV's bug; the wiki says "0 never
  pays"). Read in phase 3: [roulette built](#roulette-built).

### <a id="rules-slots"></a>3.4 Slots [V]

`Reels::InitReels 0x007c16b0`, `SlotMenu::Update 0x007c2c70`,
`SlotReelLogic::AdjustReels 0x007c58f0`.
- Three reels of 28 positions: for each of the 7 symbols, its CSNO stop
  count of (symbol, blank) pairs; the 7th symbol is the wild. Each reel
  stops at a random position.
- **Pays (multiple of the bet):** three wilds ×10; three of symbols
  1-6: ×10, ×20, ×30, ×40, ×60, ×100; two wilds ×5; one wild ×2; anything
  else loses. (Wiki names them cherry wild, bells, bars, sevens, lemons,
  grapes, oranges.)
- **Bets:** min/max from the opener; steps +1 below 10, +5 below 40, +10
  below 100, +25 below 500, then +100.
- **Luck:** with chance |Luck − 5| × 10%, a near miss is nudged into a win
  (Luck above 5) or a win is nudged off (below 5), and wilds become
  blanks.

### <a id="rules-bank"></a>3.5 Winnings, comps and the ban [V]

- Every round adds its net result to the casino record's earnings.
- After each round, levels 1-4 are reached at earnings ≥ max × 25%,
  50%, 75%, 100%. Reaching a new level **closes the menu** and, on exit,
  **enables the CSNO's winnings quest** (`TESQuest::SetEnabled`,
  `0x0060c9c0`); no stage is set.
- The condition function behind `GetCasinoWinningsLevel`
  (`tesconditionfunctions.cpp 0x005a6170`) returns that level.
- At level 4 the engine refuses every game in that casino; the scripts do
  the rest (floor manager, achievement 29). The ban only stops gambling;
  you can still cash out (W "Big Winner" L4655871).
- Wiki comp table (W L4655871; agrees with the CSNO maxima): e.g. Gomorrah
  2,250 / 4,500 / 6,750 / ban 9,000. A single big win can skip a level;
  that comp is lost.

### <a id="rules-caravan"></a>3.6 Caravan [V]

`tescaravan.cpp`, `caravanmenu.cpp`, `staging\blk_00740000_od.cpp`.
- **Opener:** `<opponent>.ShowCaravanMenu <CDCK> <mode> <ante share>`. The
  opponent's deck is only the CDCK; mode (0-3) is the AI's difficulty; the
  float sets the ante.
- **Collection:** the player's cards are **not inventory items**. Two lists
  on the player: owned cards (`+0x614`) and the active deck (`+0x618`).
  `AddCardToPlayer` adds a card unless it is already in either list, so a
  card from the same set never repeats.
- **Deck:** at least 30 cards, or the menu won't open (`sCardCountText`);
  the builder has Add, Remove and Randomize (a random size from 30 up).
- **Deal:** 8 cards each; the opening round puts a numbered card on each
  of your 3 caravans.
- **Turn:** play a card; discard a card from hand; or discard a whole
  caravan. Then draw.
- **Placement** (`CanPlaceCard 0x0074f6c0`): 6 tracks × 7 rows. Numbers go
  only on your own caravans, can't repeat the last value, and must follow
  the direction unless they match the suit. Face cards go on any track on
  a numbered card; a Queen only on the last card.
- **Values and effects:** Ace 1, 2-10 face value; a King doubles its card
  (stacking); a Queen changes suit and reverses direction; a Jack removes
  its card and that card's face cards; a Joker on an Ace removes every
  other card of that suit, on a number every other card of that value.
- **Win** (`CheckCaravanResult 0x00752e20`): a caravan sells at 21-26 and
  beats the opposite one if it is higher or the other hasn't sold; the
  side that wins 2 of 3 takes the pot. A side out of cards loses.
- **Bet:** funds = caps + the value of CMNY items held, for both sides.
  The opponent antes its funds × ante share; it matches a raise up to
  min(its funds, its funds × share × (1 + Barter / 100))
  ([Caravan built](#caravan-built)). The winner gets
  CMNY items first, then caps for the rest (`0x0074cc70`).
- **AI** (`0x0074fdc0`): scores every legal move (push a caravan toward
  21-26, face cards by lane advantage, Jack/Joker by the player's loss,
  discards) and plays the best. Mode changes the opening choice (mode ≥ 3
  opens nearest 6) and caravan-discard scoring.
- **Stats:** misc stats 37/38 (Caravan won/lost) and 40-42 (roulette,
  blackjack, slots games) feed the challenges.
- **Per-merchant limit** of 5 games (wiki) is dialogue conditions on
  `vCaravanQuest` counters, so it converts with the dialogue.

### <a id="rules-gmst"></a>3.7 Settings

Only one number: `iAntiCheatDuration`. Everything else is text (`sDealText`,
`sHitText`, `sStayText`, `sDoubleDownText`, `sSplitText`, `sSurrenderText`,
`sSpinText`, `sPlaceBetText`, `sGamblingBannedText`, `sGamblingBrokeText`,
`sLuckyWinText`, `sUnluckyLoseText`, `sCardCountText`, `sRSMRandomize`, the
Caravan bet and result strings and about 60 more). FNV's English values
are engine defaults; the menu takes them from a converted string table
(see [4.6](#design-text)).

---

## <a id="design"></a>4. The 2D design

### <a id="design-shape"></a>4.1 Shape in one paragraph

Each game is **one custom Scaleform menu of our own** (`F3NV_Casino.swf`),
opened through **F4SE's `UI.RegisterCustomMenu`/`UI.OpenMenu`**. **The game
rules run inside the menu, in ActionScript 3**, exactly as FNV's rules ran
inside its menus. **Papyrus is the bank**: it opens the menu with the
casino's data and the player's chips, Luck and Barter, takes the result
back through F4SE's external events, moves chips, caps and cards, keeps
earnings, levels and the ban in the save, and starts the comps quests.
**No new F3NV.dll feature is needed.** The art is the user's own FNV
textures, converted at build time and shown with F4SE's image mounting.

### <a id="design-ui"></a>4.2 UI approach

| Option | Verdict |
|---|---|
| **Custom Scaleform menu via F4SE** (`UI.RegisterCustomMenu`, `UI.OpenMenu`, `UI.Invoke`, `ScriptObject.RegisterForExternalEvent`; `references/fo4_scripts/F4SE/UI.psc`, `ScriptObject.psc:379`) | **Chosen.** F4SE is already required. A real menu: pauses the game, mouse cursor, gamepad, its own close. Card games need a free layout (cards, chips, a wheel, reels), which only a movie gives. |
| Message boxes (MESG with buttons) | Fallback for testing only. No cards on screen; blackjack is barely playable, roulette's 159 spots and Caravan are not. |
| Pip-Boy page or tab (the `pages.cpp` technique) | No: the Pip-Boy is the wrong place to sit at a table, has no room for a board, and the technique needs F3NV.dll code. |
| A vanilla menu re-skinned at run time (as `pipboy.cpp` does) | No: needs DLL code, and no vanilla menu has the input model. |
| An existing FO4 mod's menu | None exists for blackjack, roulette or Caravan; PipboyTabs and LevelUpMenuEx are tab and level-up menus. |

**Menu details:**
- One movie with five screens: slots, roulette, blackjack, Caravan deck
  builder, Caravan table (bet and results are panels on the table). One
  movie keeps one load path, one font setup and one input handler.
- Registered once per game load by the `F3NV_Casino` quest
  (`OnInit` and on load), with flags for pause, cursor, modal and gamepad
  (`UI.MenuData`).
- **Art at run time:** the converter copies the FNV card faces and backs,
  slot symbols, felt and Caravan wood to `Textures\F3NV\Casino\` (from the
  user's own archives, packed in the plugin's BA2 like every converted
  texture). The movie shows them with F4SE's `MountImage` and
  `img://` URLs. The movie itself holds no Bethesda art.
- **Look:** the felt and wood are top-down already (the felt stored
  flipped); cards, chips, symbols and the wheel are flat images on top.
  The wheel is drawn as a ring of pockets from the wheel order; the reels
  as three columns of symbol images. FO4's own fonts by name and the
  player's HUD color for text and buttons.
- **Input:** mouse on PC; gamepad and keyboard map to the same buttons
  (Deal, Hit, Stay, Double, Split, Surrender; Spin; bet up/down/max; Exit;
  for Caravan: select card, select track, discard, discard track).
- **Source:** our own AS3 in the repo, no decompiled `Shared.*` classes.
  The built `.swf` is never committed (the pre-push binary rule); it is
  built from source by a tool and ships with the converted output.

### <a id="design-logic"></a>4.3 Where the game logic lives

**In the menu (AS3), with Papyrus as the bank.** Reasons:
- FNV's own split is the same: the menu runs the round, the engine settles
  chips on exit. Following it means the converted scripts only ever see
  settled results, as in FNV.
- A round is many small steps (deal, hit, the AI's search over 8 cards ×
  6 tracks); Papyrus round trips per step would be slow and laggy; AS3 runs
  them in a frame.
- No DLL work, which CLAUDE.md asks for.

| Lives in | What |
|---|---|
| AS3 (`F3NV_Casino.swf`) | Shuffle and deal; blackjack, roulette, slot and Caravan rules; FNV's Luck bias; the Caravan AI; bet steps; showing results |
| Papyrus `F3NV_Casino` (quest + script) | Opening (the converted openers call it); the five FNV refusals (anti-cheat, ban, broke, min winnings, deck < 30); chip/caps/CMNY/card transfers; earnings, levels, ban per casino; starting the winnings quest on a new level; misc-stat counters for the challenges; the Caravan collection and deck |
| F3NV.dll | **Nothing new.** See [4.8](#design-dll) for the two cases where it would become the fallback. |

**One RNG**, a small seeded generator written the same way in AS3 and in a
Python reference model (see [tests](#phases-tests)), seeded from Papyrus
(`Utility.RandomInt`) at menu open so a run can be replayed exactly.

**The menu's contract with Papyrus** (all through `UI.Invoke` in and
`F4SE.SendExternalEvent` out):
- in: game, casino data (decks, reshuffle, payout, soft-17, reel stops,
  min/max bet), chips held, earnings, max winnings, Luck, Barter, seed;
  Caravan: the player's deck and collection (card ids), the opponent's
  deck, mode, ante share, both sides' funds;
- out, **after every round** (not only on exit): net chip change and the
  game counter; Caravan: the result and the pot. Papyrus applies it at
  once, so earnings and the ban are right even if the game is quit or
  crashes mid-session; on a new level Papyrus tells the menu to close, as
  FNV does.

### <a id="design-forms"></a>4.4 FNV records → Fallout 4 forms

All new records keep their FNV FormIDs, as other converted records do
(FormIDs are hashed from authored keys). Nothing existing moves; the build
gains records, so this is **no FormID drift** — but the
[determinism test](../../tests/test_formid_determinism.py) must be run and
the count of added ids reported.

| FNV | FO4 | Notes |
|---|---|---|
| CHIP (6) | **MISC**, FNV name, model, icon; value 0, weight 0; keyword `F3NV_CasinoChip` | Fills the 50 `*Chip` properties; cashier dialogue and DM vending recipes work unchanged |
| CMNY (6) | **MISC** with FNV's cap value (DATA), weight 0; keyword `F3NV_CaravanMoney` | Real items in 342 inventory entries; cashiers take them; Caravan counts them as funds. FO4 vendors only trade caps, so they barter as items at their value (drift) |
| CSNO (6) | **QUST** `FNV_<edid>`, never started, with script `F3NV_CasinoData`: properties from DATA (decks, reshuffle, payout, soft17, reel stops[7], max winnings, chip MISC, winnings Quest, name, art texture paths) and state variables (earnings, level) | A quest is the FO4 form that carries a script readable without a reference. Fills the 19 `*CasinoData` properties (typed `F3NV_CasinoData` instead of `ObjectReference`). Per-casino state lives on the casino's own form, so a new plugin's CSNO works without code |
| CCRD (324) | **MISC** (FNV name, model, icon, value 2), keyword `F3NV_CaravanCard`; its script converts with `AddCardToPlayer` → `F3NV_Casino.AddCard(GetBaseObject())` | Picked-up and vendor cards work through FO4's own inventory; fills `RandomCaravanBaseCards` |
| CCRD suit, value, set, face/back texture | A **card table** written by the converter: FormList `F3NV_CaravanCards` (all cards, ordered) plus a generated script `F3NV_CaravanCardTable` holding suit, value and texture index arrays (chunked under Papyrus's 128-element literal limit) | Pushed to the menu once per open |
| CDCK (13) | **FLST** `FNV_<edid>` of the card MISCs | `ShowCaravanMenu <CDCK>` → the FormList |
| `GAME*` sounds (41) | SNDR, the usual sound path | Fills the 4 `GAMESlots*` properties; the menu plays them by name |
| HelpBlackjack etc. (7 MESG) | converted already; the menu's Help button shows them | |

**Openers in `script_convert`** (one command row each):
- `ShowBlackjackMenuParams c min max w` → `F3NV_Casino.Open(1, c, min, max, w)`;
  likewise roulette (2) and slots (3);
- `<ref>.ShowCaravanMenu d mode share` → `F3NV_Casino.OpenCaravan(<ref>, d, mode, share)`;
- `GetCasinoWinningsLevel c` → `c.GetLevel()` (and in conditions, a
  `GetValue` on a per-casino global the data quest keeps, since FO4
  conditions can't call script functions; only scripts use it in FNV);
- `AddCardToPlayer` → `F3NV_Casino.AddCard(...)`.

### <a id="design-persist"></a>4.5 Saves, collection, ban

- **Earnings, level, ban:** script variables on each casino's
  `F3NV_CasinoData` quest. Quest script state is saved by the game. The ban
  is "level 4", as in FNV; the comps scripts' own `Banned` flags still run.
- **Anti-cheat:** `OnPlayerLoadGame` on the casino quest's player alias
  stores the time; openers refuse for 60 s (FNV's `iAntiCheatDuration`
  default; to be read from the exe in phase 1).
- **Caravan collection and deck:** two persistent, hidden containers in a
  holding cell (`F3NV_CaravanCollection`, `F3NV_CaravanDeck`), mirroring
  FNV's two lists. `AddCard` moves the card item from the player into the
  collection unless the same card is already in either, which keeps FNV's
  "no duplicate from the same set" rule. Containers are saved by the game
  and need no array limits. The deck builder reads both with
  `GetItemCount` over the card FormList and writes back by moving items.
- **FNV saves:** none carry over (a converted game starts fresh), so no
  migration.

### <a id="design-text"></a>4.6 Text

The menu's labels come from FNV's settings ([3.7](#rules-gmst)). The
converter writes them to the menu's translation file
(`Interface\Translations\F3NV_Casino_en.txt`, FO4's `$KEY` mechanism), so
other languages follow FNV's own string tables when present.

**Correction (2026-11-12):** F4SE loads a translation file only when it's
named after an active plugin, so `F3NV_Casino_en.txt` would never be read
([swf_framework.md](swf_framework.md#translations)). Today the labels reach
the menu through Papyrus instead. If they move to `$KEY`s, they go in a file
named after the converted plugin, written under the player's `sLanguage`.

### <a id="design-flow"></a>4.7 One round, end to end (slots)

1. Player activates `vGomorrahSlot01`; its converted script calls
   `F3NV_Casino.Open(3, GomorrahCasinoData, 1, 60, 0)`.
2. Papyrus checks anti-cheat, ban, chips; pushes the data; opens the menu.
3. The menu spins with the seed and Luck; after each spin it sends
   `F3NV_CasinoRound(net, played)`.
4. Papyrus moves Gomorrah chips, adds the net to earnings, raises the
   level if a threshold is crossed (and then starts
   `vCasinoCompsGomorrah` and closes the menu), and counts the game for
   "One Armed Bandit".
5. The comps quest's converted script sees `GetLevel()` = 1 and sends the
   floor manager, as in FNV.

### <a id="design-dll"></a>4.8 Where a DLL would be needed

**Nowhere in the plan as designed.** It becomes the fallback only if the
phase 0 spike shows one of these fails:
1. **Custom menu input:** if a menu registered through F4SE gets no
   gamepad or keyboard events, or locks input on close (the repair menu's
   `UI.OpenMenu` attempt locked input, [condition](fo4_condition.md);
   that was opening a *vanilla* menu from the console, a different case).
   Fix: register the menu from F3NV.dll with CommonLibF4's
   `UI::RegisterMenu` and its own input handling.
2. **Images:** if `MountImage` can't show a DDS from the BA2. Fix: the DLL
   loads the texture into the movie's image loader.

A DLL is **not** needed for the rules, the RNG, saves or transfers. The one
DLL call the menu makes is optional: the player's HUD color
([spike 2b](#hud-color)), white without F3NV.dll.

### <a id="design-toolchain"></a>4.9 Building the movie

The project has no AS3 compiler. Two routes, to settle in phase 0:
- **FFDec** (already at `tools_ext\FFDec`): build a skeleton AS3 SWF with
  the Python writer (header, file attributes, one empty class), then
  compile our `.as` sources into it with FFDec's command-line script
  import. Nothing to install; FFDec's AS3 compiler is less tested than
  Adobe's.
- **Apache Flex SDK** (`mxmlc`, Apache 2.0) or Harman's AIR SDK: the
  standard compiler; a download and a Java install.

Either way a new `tools/generators/gen_fo4_casino_swf.py` builds the movie
reproducibly from `fo4_import/casino/as3/` (or wherever the code layout
puts it) and the GUI ships the built file. It goes in
`docs/reference/python_tools.md`.

---

## <a id="phases"></a>5. Phases, sizes, order, tests

S ≈ a day, M ≈ a few days, L ≈ a week or more of focused work.

| # | Phase | Size | Depends on |
|---|---|---|---|
| 0 | Spike: toolchain and an empty menu | S-M | - |
| 1 | Records, export decode and the bank | M | - (parallel with 0) |
| 2 | Slots | S | 0, 1 |
| 3 | Roulette | M | 2 |
| 4 | Blackjack | M | 2 |
| 5 | Caravan | L | 1, 2 |
| 6 | Dead Money and polish | S | 2-5 |
| later | 3D tables | L+ | 6 |

**Order:** 0 and 1 together; then slots, the smallest game, proves the
whole loop (opener → menu → round → bank → comps quest). Roulette and
blackjack next (3 and 4 can run in either order). Caravan last: it is the
biggest and needs the collection and deck builder on top of the same
shell.

### <a id="phase-0"></a>Phase 0. Spike: toolchain and an empty menu (S-M)

- Pick the compiler ([4.9](#design-toolchain)); build a movie with one
  button and one image.
- `F3NV_CasinoSpike` quest registers it; a console-callable function opens
  it. Check: pause, cursor, mouse, keyboard, gamepad, close, input after
  close, `UI.Invoke` in, external event out, `MountImage` of one converted
  card DDS from the BA2, the HUD color.
- **Tests:** the generator builds the same bytes twice (reproducible); a
  unit test reads the movie's header and class list.
- **In game:** the user opens the test menu from the console, clicks the
  button, sees the card, closes it, and walks and activates normally after.

<a id="toolchain-found"></a>**Since 2026-11-11 the casino builds with
`mxmlc` on our shared `f3ui` library** (spike 1 of the
[menu framework](swf_framework.md#spikes); `fo4_import/base/mxmlc.py`,
count `casino menu movie missing (no Flex SDK)`). **Played 2026-11-11:
slots and roulette both work on it.** The movie is written uncompressed so
its bytes don't depend on the Python's zlib
([why](swf_framework.md#mxmlc-setup)). The FFDec route below is
how it was built until then; the dialogue menu used it until 2026-11-12,
when its code was deleted.

**Built 2026-11-08, not played.** The compiler
is **FFDec** (open question 1 taken as recommended; no Flex SDK needed).
- FFDec's `-importScript` only *replaces* classes already in a movie; it
  cannot add one, and has no option to. So `fo4_import/casino/movie.py`
  writes the skeleton itself: an uncompressed AS3 SWF (FileAttributes AS3,
  DoABC2, SymbolClass of the document class) whose ABC holds an empty
  `Object` subclass per `.as` file under `fo4_import/casino/as3/`
  (`abc_shells`, about 60 lines). FFDec then compiles the real sources over
  the shells, rebuilding each script initializer with the right scope chain
  (checked in its p-code: `MovieClip`'s seven ancestors pushed before
  `newclass`). Two builds give identical bytes.
- FFDec exits 0 even on a compile error; the error is a `SEVERE` log line,
  which the build turns into a failure. Its parser is lenient: `var x:int = ;`
  compiles without a word, so a test can't rely on every typo failing.
- The build compiles the movie once per source hash into
  `temp/fo4_casino/<hash>/` and copies it to `Interface/F3NV_Casino.swf`
  (`casino menu movie installed`); without FFDec it counts `casino menu
  movie missing (no FFDec)` and the rest of the build is unaffected. The
  app has no FFDec, so a release ships the built movie
  (`tools/generators/gen_fo4_casino_swf.py`).
- F4SE 0.7.9's source (`tools_ext/f4se_src`): `UI.RegisterCustomMenu`'s
  default `MenuData` is menu flags 0x801849D (pauses, cursor, menu context,
  modal, disables the pause menu, custom rendering), movie flags 3 and
  extended flags 3 (inherit the HUD color through the menu's shader, drop
  the cursor when a gamepad is in use). The movie gets `root.f4se` through
  `onF4SEObjCreated(codeObject)`; `MountImage(menu, path, name)` loads a
  DDS with the game's texture loader and serves it as `img://name`; mounted
  images are dropped when the menu closes. `MountImage` is AS3-only (not in
  `UI.psc`).
- **The spike screen** (`as3/F3NV_Casino.as`): title, status line, one
  image, Ping and Close buttons. Papyrus `F3NV_Casino.Spike()` on the bank
  quest `FNV_Casino` (no separate spike quest: the bank quest registers the
  menu anyway) opens it and passes a card face (`cardt_c01.dds`, staged at
  `Textures/fnv/terminals/nv_playingcards/deckt/`) under three path
  spellings; the screen shows which one mounted. Esc/Tab (stage keys) and
  FO4's `Cancel` control close it through Papyrus (`F3NV_CasinoClose` →
  `UI.CloseMenu`); Enter, `Accept` or the button pings. Every key and
  control seen is written to the Papyrus log (`F3NV_Casino: input ...`), so
  one session answers which input paths reach a custom menu.
- **Played 2026-11-08 (build 1108b):** the menu opened, the font rendered
  and the image mounted, but the screen drew only in a box around the
  cursor: the black backdrop showed as a square around the arrow, and the
  status text appeared only under the mouse. Cause: F4SE's default flags
  include Custom Rendering (0x8000) and Assign Cursor To Renderer
  (0x10000), which draw the menu through the game's shader target
  (`CustomMenu.cpp` pushes the stage's filter holder to `shaderFXObjects`)
  and that only redrew the cursor's area. `F3NV_Casino.Register` now passes
  menu flags 0x800049D (the default without those two) and extended flags 2.
  Cost: no HUD-color tint (it needs that shader); the menu is white on
  black. A changed registration needs a game restart, not a save reload
  (F4SE keeps the first registration for the session).
- **Played 2026-11-08 (build 1108c):** the screen drew whole, but no
  image showed, and the log had three faults. Fixed, not yet played:
  - **Every event five times.** F4SE keeps one registration per object and
    script (`EventRegistration::operator<`), so repeated `Register()`
    calls were not the cause. Five plugins each shipped a bank quest:
    FalloutNV, Dead Money, Gun Runners, Honest Hearts and Tribal Pack.
    `source_walk` also yields the master's CSNO and CDCK. A DLC's own
    ledger had kept ids from builds made before FalloutNV had the casino,
    and `derive_formid` reads the own ledger before the masters'. So
    Honest Hearts copied all 5 casinos, 13 decks and the bank.
    `Casino._forms` now gives a master's casino and deck the master's id
    (`LedgerWriter.from_master`). The bank is made only by the masterless
    build. A DLC writes only its own (Dead Money's Sierra Madre).
  - **"Type mismatch for argument 1".** F4SE turns an AS3 `int` into a
    Papyrus Int (`ConvertScaleformValue`), so `OnMenuPing(Float)` failed;
    `OnMenuRound(Float)` would too. Both now take Int.
  - **"[object Object]" and no image.** `UI.Invoke` passes each item of a
    `VarArrayToVar` array as `{__var__: value}`. The path became
    "[object Object]", and `MountImage` still returned true: the game's
    texture loader returns a stand-in for a missing file, so "mounted"
    does not prove the file was found. `Ui.plain` unwraps every array the
    movie gets: the spike's paths, slots' stops, symbols and texts, and the
    self-test's seeds. The spike now loads every path form side by side
    (`Textures/<path>`, `<path>`, `Data/Textures/<path>`). The log names
    which form loaded and at what size (`image img://F3NV_Spike0 shown WxH`).
- **Played 2026-11-08 (build 1108d):** the card image loaded only as the
  bare path under Textures (`fnv/terminals/nv_playingcards/deckt/cardt_c01.dds`).
  So `MountImage` takes the path without the `Textures/` folder. `MountAll`
  (slot symbols) and the spike now mount the bare path, as the records
  store it (`records.fo4_path`).
- <a id="hud-color"></a>**The HUD color without the shader (spike 2b, built
  2026-11-11, not played).** Spike 2a (F4SE's flags with the HUD color
  shader) failed: with them the slot menu would not open; the flags stay
  0x800049D / 2. Instead the menu colors its own text, outlines and button
  faces: `Ui.color` (white by default) is set in `newScreen()` from
  F3NV.dll's `HudColor()` native (`gfx.cpp`, registered with our
  other movie natives on every movie as `f4se.plugins.F3NV`), which
  returns `iHUDColorR/G/B:Interface` as 0xRRGGBB, read on every call. The
  reader `HudColor(prefix)` is shared with the Hardcore HUD fields
  (`hardcore.cpp`, declared in `condition.h`). Without F3NV.dll the menu
  stays white. The board's red, black and green cells and the chips' gold
  keep their own colors. The log says `F3NV_Casino: input hud color <hex>`
  on each screen. Menu Frameworks' design. **Played 2026-11-11:** text,
  outlines and reel frames follow the HUD color (pink); the symbols keep
  their own.
- <a id="hud-hidden"></a>**Two fixes from that play (built 2026-11-11,
  not played):**
  - **A thin yellow frame round the screen** was Flash's focus rectangle:
    the root takes the keyboard focus (`stage.focus = this`), and its
    bounds are the whole backdrop. The movie now sets
    `stage.stageFocusRect = false` and `focusRect = false`, as FO4's own
    `Shared.IMenu` does (its `stage.stageFocusRect = false`, read from the
    game's DialogueMenu.swf), so our dialogue menu, built on `IMenu`,
    never had it.
  - **The HUD showed through** (the activate prompt, compass, crosshair).
    FO4 has no menu flag that hides the HUD, and changing the flags kept
    the menu from opening (spike 2a). So the bank hides HUDMenu's root clip
    with F4SE's `UI.Set("HUDMenu", "root1.visible", False)` when the
    casino menu opens and shows it again when it closes, and on every load
    (`ShowHud`).
- **Level-up images (built 2026-11-12, not played):** the spike now shows
  the card face and three level-up images (DXT3, DXT5, and a name with a
  space) from the `SpikeImages` property, 300 pixels apart
  ([level-up](swf_framework.md#level-up)).
- **In-game check:** `cqf FNV_Casino Spike`; then click Ping, press Enter,
  Esc, and a gamepad's A/B if one is connected; read
  `F3NV_Casino:` lines in `Papyrus.0.log`.

### <a id="phase-1"></a>Phase 1. Records and the bank (M)

- **Export:** decode CSNO, CHIP, CMNY, CCRD and CDCK in
  `tes4_export/export_falloutnv.py` (pure dump of every field, per the
  xEdit layout), then re-export FalloutNV.esm and DeadMoney.esm.
- **Import:** the forms in [4.4](#design-forms) under `fo4_import/`
  (FNV-specific code in its own module); copy the card, symbol, felt and
  wood textures; the `GAME*` sounds.
- **Scripts:** the command rows in [4.4](#design-forms); static scripts
  `F3NV_Casino.psc` (bank, openers, collection) and `F3NV_CasinoData.psc`.
  Until a game's screen exists, its opener shows "not built yet" as a
  message, so nothing silently does nothing.
- **Tests:**
  - export test: counts 5/5/6/270/13 (DM 1/1/0/54/0) and the CSNO values
    in [1.1](#inv-records) (e.g. Atomic Wrangler payout 1.2, 1 deck, 5,000);
  - import test: each CSNO becomes a quest with the right properties; each
    CDCK a FormList with the right card count;
  - `script_convert` tests for the four openers, `GetCasinoWinningsLevel`
    and `AddCardToPlayer`;
  - `tests/test_formid_determinism.py`, and the added-id count;
  - Papyrus compile; the properties audit: the 69 `*CasinoData`/`*Chip`
    lines and `RandomCaravanBaseCards` gone (70 of the 76; this check
    leaves out the 4 `GAMESlots*` and 2 `RouletteDealerPackage1` lines).
- **In game:** buy Gomorrah chips from the cashier, see them in the
  Pip-Boy, cash out; pick up a Caravan card (it leaves the inventory);
  NCR dollars show their value.

<a id="records-built"></a>**Built 2026-11-08, not played** (`fo4_import/casino/records.py`,
`F3NV_Casino.psc`, `F3NV_CasinoData.psc`, `F3NV_CasinoPlayer.psc`):
- **No re-export.** CSNO, CDCK and CCRD are read from the plugin with
  `source_walk`, as the chip, money and card items already are
  ([items built](#items-built)); `tes4_export` stays a pure dump. Counts
  from FalloutNV.esm match [1.1](#inv-records): 5 CSNO, 13 CDCK, 270 CCRD
  (tests). DATA unpacks as `<ff7IIIIII` (56 bytes).
- **Per casino:** a start-game quest `FNV_<edid>` running `F3NV_CasinoData`
  (name, decks, reshuffle share, payout, soft-17 flag, reel stops, max
  winnings, chip MISC, winnings quest, slot symbol and deck back texture
  paths) and a global `FNV_<edid>Level`. The script keeps earnings and level;
  `AddResult(net)` raises the level at 25/50/75/100% of max winnings (never
  lowers it, a big win can skip one), sets the global and starts the comps
  quest if it isn't running (vCasinoCompsTheTops starts disabled).
- **Conditions:** `GetCasinoWinningStage <casino>` (the 37 floor-manager
  lines) is `GetGlobalValue` of that global (`say_topics._form_value`).
- **Decks:** each CDCK is a FormList `FNV_<edid>` of its card MISCs.
  **The player's cards are two FormLists, not containers** (drift from
  [4.5](#design-persist)): `F3NV_CaravanOwned` and `F3NV_CaravanDeck`, filled
  with `AddForm`, which the save keeps. They are FNV's two lists exactly;
  the card item leaves the inventory through FNV's own `RemoveMe`, so no
  hidden container or holding cell is needed.
- **Script rows** (`command_rows_fallout4`): `ShowBlackjackMenuParams`,
  `ShowRouletteMenuParams`, `ShowSlotMachineMenuParams` →
  `TES4Casino.Open(1|2|3, <casino>, min, max, min won)` with the casino
  property typed `F3NV_CasinoData`; `GetCasinoWinningsLevel <casino>` →
  `<casino>.GetLevel()`; `<ref>.ShowCaravanMenu <deck> <mode> <ante>` →
  `TES4Casino.OpenCaravan(ref, deck, mode, ante)`; `AddCardToPlayer` →
  `TES4Casino.AddCard(<ref>)`. FNV calls them 4/5/5 times (slots, roulette,
  blackjack openers), 20 times (comps polls), 23 Caravan calls in 17 INFOs,
  2 card scripts.
- **`GetContainer != <ref>` is real on Fallout 4** (`emit/expr._container`):
  FO4 has `ObjectReference.GetContainer()`, so on a reference script the
  comparison is kept instead of neutralized to `False`/`True`. Before, the
  card script's `if GetContainer != player return else AddCardToPlayer`
  read `If False`, so every container move (a vendor chest restocking)
  would have collected the card. Blast radius: 4 scripts, FalloutNV's and
  Dead Money's `CardAddToPlayerScript`, and Dead Money's
  `NVDLC01PassEntertainerSCRIPT`/`NVDLC01PassMaintenanceSCRIPT`, whose
  `GetContainer == Player` read always-true and now only fires for the
  player, as authored.
- **The bank's openers** run FNV's refusals in its order (blackjack
  `@fnv 0x00733630`): the anti-cheat wait after a load (per-game text and
  the seconds left), the ban (level 4), too few chips, too little won
  (`sGamblingMinWinText`; every FNV opener passes 0). Until a game's screen
  exists the opener shows the casino's name and "This game is not playable
  on Fallout 4 yet." Caravan refuses under 30 cards (`sCardCountText`), then
  shows the same. `Settle(casino, net)` moves chips and adds the earnings;
  a new level closes the menu.
- **Texts** are FalloutNV.exe's (GOG exe, `oblivion_engine_extract.py
  --settings`, run under Python 3.13): `sGamblingBannedText`,
  `sGamblingBrokeText`, `sGamblingMinWinText`, `sCardCountText`,
  `sAntiCheatTimeRemainingText`, `s{Blackjack,Roulette,Slot}AntiCheatText`,
  `iAntiCheatDuration` 60; a FalloutNV.esm GMST would override.
- **Art staged:** every texture the CSNOs (symbols, deck backs) and CCRDs
  (faces, backs) name, from the export, under `Textures/fnv/...` in the
  texture BA2. The felt and Caravan wood are named only by the minigame
  NIFs; they come with the blackjack and Caravan screens.
- **Not in phase 1:** the card table (suit, value, texture per card) comes
  with Caravan (phase 5), its only reader. Counting games for the
  challenges comes with each game's screen.
- **New records, no drift:** FalloutNV.esm gains 26 (5 data quests, 5
  globals, 13 deck lists, the bank quest, 2 card lists), Dead Money 2 (the
  Sierra Madre's quest and global); all on new keys, nothing existing moves.

### <a id="phase-2"></a>Phase 2. Slots (S)

- Screen: three reels, bet buttons, payout list, earnings, chips.
- Rules from [3.4](#rules-slots), Luck nudge included.
- **Tests:** the Python reference model (`tests/casino/`) for reel build
  and payout table; seeded traces compared with the AS3 version (the movie
  has a self-test mode that replays the trace seeds and writes results to
  the Papyrus log through an external event); a 100,000-spin simulation of
  the return at Luck 1, 5 and 10 against the decomp's numbers.
- **In game:** play Gomorrah's slots, win and lose, leave and see the chip
  count right; win past 2,250 and the floor manager comes; reload a save
  and get refused for a minute.

<a id="slots-built"></a>**Built 2026-11-08, not played** (`as3/f3nv/casino/Slots.as`,
`SlotsScreen.as`, `Rng.as`, `Ui.as`; `tests/casino/model.py`):
- **Rules, read again in the decompile** (`slotmachinemenu.cpp`), sharper
  than [3.4](#rules-slots):
  - A reel value is 2 × symbol, odd for the blank after it; 12 is the wild
    (the CSNO's 7th icon), 13 its blank. `InitReels` fills 28 stops round
    by round; a spin lands each reel on one of the first 2 × kinds stops
    (`0x007c56e0`), so with the authored stops (2 each) every reel is
    uniform over 7 symbols and 7 blanks.
  - Classes (`0x007c5760`): three equal non-blank values; else exactly two
    wilds; else one wild; else a pair (only feeds Luck); else nothing. A win
    adds bet × its multiple (the bet is not also taken), a loss takes the
    bet. Three wilds and three cherries pay ×10, then ×20, ×30, ×40, ×60,
    ×100 by symbol; two wilds ×5; one wild ×2.
  - **The house keeps 25.95% at Luck 5**: exactly (1479 − 2191) / 2744 of a
    bet a spin (the model's 60,000-spin run agrees within 3%).
  - **Luck** (`AdjustReels 0x007c58f0`): a nudge happens with chance
    |Luck − 5| × 10%. Above 5: nothing → spin again (and roll again); a
    pair or two wilds → the odd reel joins when (difference)² ≤ Luck; one
    wild → its neighbors equalized when within Luck (FNV's neighbor choice
    kept, quirks and all: it can't make three of a kind, only the lucky
    text). Below 5: three of a kind → all three moved to the next value up
    (a blank, or cherries from the high symbols); wilds → blanks. A nudge
    above 5 shows `sLuckyWinText`, below 5 `sUnluckyLoseText`.
  - Spinning adds misc stat 42 (`FUN_004d5c60(42)`), "One Armed Bandit"'s
    counter; **not counted yet** (the challenge system leaves FNV's casino
    misc stats out; see what's left below).
- **One RNG**, xorshift32 (shifts and xors only, so AS3's `uint` math and
  Python agree exactly), seeded from `Utility.RandomInt` per opening.
- **The screen:** three reel panels showing the casino's mounted symbols
  (`img://F3NV_Symbol<i>`; a blank shows an empty panel), a payout list
  with the symbols, chips, bet and earnings, and `-`, `+`, Bet Max, Spin,
  Exit. Keys: Enter or Space spin, Left/Right bet, Esc/Tab leave; FO4's
  `Accept`/`Left`/`Right`/`Cancel` controls the same. Labels are FNV's
  settings (`SLOT_TEXTS`, the screen's index order is checked by a test).
  No reel animation or sounds yet (phase 6).
- **The loop:** a converted opener → `Open(3, ...)` → refusals → the menu
  opens → `OpenSlots` hands it the casino name, chips held, bet range,
  earnings, Luck (`Game.GetLuckAV()`), a seed, the reel stops, symbol
  paths and texts → each spin sends `F3NV_CasinoRound(net)` → `Settle`
  moves the chips (silently; drift: FNV showed the total on leaving) and
  adds the earnings → a new level closes the menu and starts the comps
  quest.
- **Self-test:** `cqf FNV_Casino SelfTest 5` (or another Luck) logs
  `F3NV_Casino: selftest slots <luck> a,b,c ...` (seeds 1-3, 20 spins
  each). Pasting that text after `selftest ` into
  `tests/casino/selftest.txt` (one line per Luck; [roulette](#roulette-built) adds its own) makes
  `test_the_movies_spins_match_the_model` compare it with the model.
- **What's left in phase 2:** counting games for the challenges (misc stat
  42, and 40/41/37/38 later): FNV's casino misc stats are left out of
  `challenges.FO4_STATS`; they need a casino event in `F3NV_Challenges`.

### <a id="phase-3"></a>Phase 3. Roulette (M)

- Screen: the betting board's 159 spots (click to stack chips, right-click
  or a button to remove), the wheel ring, last results.
- **Tests:** reference model for every spot's numbers and payout; traces;
  the house edge over a long simulation is 5.26% (or as FNV's 0 bug makes
  it, see the open question).
- **In game:** bets on each kind, the 200 total limit (100 at the Sierra
  Madre).

<a id="roulette-built"></a>**Built 2026-11-11, not played** (`as3/f3nv/casino/Roulette.as`,
`RouletteScreen.as`; `tests/casino/roulette.py`):
- **Rules, read in the decompile** (`roulettemenu.cpp`), sharper than
  [3.3](#rules-roulette):
  - **The board** (`InitRouletteWheel 0x007b9c40`): six rows of 24 spots
    from the street edge (row A) to the 3s (row F), then 15 more. In the
    number rows (B, D, F: the 1s, 2s, 3s) odd places are the numbers and
    even places the splits between them; rows C and E (between) hold the
    vertical splits and the corners; row A the streets (11:1) and six lines
    (5:1). Place 0 of each row is the 0/00 edge: the top line 0-00-1-2-3
    (6:1), 0-1 and 00-3 (17:1), and the baskets 0-1-2, 0-00-2, 00-2-3
    (11:1). Spots 144-146 are 00, the 0/00 split and 0; 147-158 the
    dozens, 1-18, even, red, black, odd, 19-36 and the columns. 38
    straights, 60 splits, 15 streets and baskets, 22 corners, 11 lines.
  - **The spin** (`0x007bf670`): one draw of 38 pockets, 37 standing for
    00 (and one of 4 spin animations). **Luck** only picks the win text
    (`sLuckyWinText` above 5); no unlucky text. A Luck below 5 changes
    nothing at all: its flag (0x400e) is set and never read in
    `roulettemenu*.cpp`.
  - **The payout** (`0x007bd2a0`, state 3): every winning bet returns
    (odds + 1) × its chips; the net takes the table's total back. Spots up
    to 146 win when the result is in their number list; the outside spots
    test the result by rule.
  - **0 and 00, FNV's bug as it really is** (the wiki's "0 never pays" is
    half of it): the number lists are `BSSimpleList`s whose `AddHead`
    (`0x005ae3d0`) skips 0, so no split, basket or top line ever pays on 0,
    and the 0/00 split pays only on 00. Spot 146 (0 alone) gets an empty
    list whose head reads 0, so **a straight bet on 0 pays**. The outside
    rules let **0 win red** (it sits at an even place in FNV's wheel order,
    where red is "even place"), **even** and **the third column**
    (0 % 3 == 0); **00 wins black, odd and the first column**
    ((37 − 1) % 3 == 0). So red, black, odd and even are fair (no house
    edge), columns 1 and 3 return **+2.6%**, straights and the rest −5.26%
    as on a real wheel, and splits holding 0 lose about half
    (`test_each_bets_return_follows_from_fnvs_rules`). Kept as FNV plays.
  - **Placing** (`HandleRouletteInput 0x007bc870`, `0x007bed70`): one bet
    a spot, ten a spin; the chips placed are the current bet; the max
    bounds the table's total (the bet shrinks to what is left, and to the
    chips held). **Steps** up as slots; down −1 to 10, then to the step's
    multiple (5, 10, 25, 100), or a full step when already on one; the bet
    holds at the min while the max leaves room. After a spin the bet goes
    back to the min. With fewer chips than the min, FNV says
    `sGamblingBrokeText` and closes the table.
  - **Texts** are FalloutNV.exe's settings (named from their registrations
    in the GOG exe): `sPlaceBetText`, `sRemoveBetText`, `sFinsihBetText`
    (FNV's typo), `sIncreaseBetText`, `sDecreaseBetText`, `sBetText`,
    `sPayoutText`, `sYouWin`, `sLuckyWinText`, `sYouLose`,
    `sYouBreakEvenText`, `sPlural` "(s)", the dozen/even/red/black/odd and
    `sTwoToOneText` names (`records.ROULETTE_TEXTS`).
  - Spinning adds misc stat 40 (`FUN_004d5c60(40)`); not counted yet, as
    slots' 42.
- **The screen:** the board drawn flat (number cells red, black, green;
  dozens and even-money cells under it; columns at the right end), with a
  small marker on every split, corner, street and line where FNV's board
  puts it. **Click an empty spot to place the current bet on it, click a
  spot with chips to take them off** (FNV's Place and Remove Bet); hovering
  shows FNV's spot label ("Bet: 1,2 / Payout: 17:1"). `-`, `+`, Finish Bet
  (spin) and Exit; Enter/Space spin, Left/Right change the bet. The wheel is
  a ring of the 38 pockets in FNV's order with the result enlarged and
  named in the middle, and the last ten results under it. No spin
  animation or sounds yet (phase 6); no gamepad cursor over the board yet
  (phase 6's gamepad pass: with a gamepad the cursor is hidden).
- **The loop:** `Open(2, ...)` now opens the menu; `OpenRoulette` hands it
  the casino, chips, min and max, earnings, Luck, a seed and texts; each
  spin sends `F3NV_CasinoRound(net)` and `Settle` banks it as slots does
  (earnings, levels, comps, the ban). Under the min bet the bank shows
  the broke text and closes the menu.
- **Self-test:** `cqf FNV_Casino SelfTest 5` now logs two lines, `slots ...`
  and `roulette ...` (seeds 1-3, 20 draws each, then each spot's odds and
  the results it wins on). Paste each after `selftest ` into
  `tests/casino/selftest.txt` (renamed from `slots_selftest.txt`, never
  created); `test_the_movies_roulette_matches_the_model` checks the movie's
  whole spot table against the model.
- **In game:** at Gomorrah or the Tops, place bets on a number, a split, a
  corner, a street, a dozen, red; spin; check chips and earnings; try an
  eleventh bet (refused) and more than 200 in total (the bet shrinks);
  bet on 0 alone and on red and see what a 0 pays.

### <a id="phase-4"></a>Phase 4. Blackjack (M)

- Screen: dealer and player hands, the felt, buttons for each action.
- **Tests:** reference model for the shoe, reshuffle, dealer rule per
  casino flag, split and double, payouts (6:5 at the Atomic Wrangler);
  Luck's candidate draw; traces.
- **In game:** each action at the Tops; a hit-soft-17 table at Gomorrah;
  double and split with too few chips refused.

<a id="blackjack-built"></a>**Built 2026-11-12, not played** (`as3/f3nv/casino/Blackjack.as`,
`BlackjackScreen.as`; `tests/casino/blackjack.py`):
- **Rules, read in the decompile** (`blackjackmenu.cpp`), sharper than
  [3.2](#rules-bj):
  - **The shoe:** decks × 52 cards in load order; shuffling only puts the
    count back to full (`0x007399d0`), and drawn cards swap to the end. The
    deal reshuffles below decks × 52 × share, a draw below 5 cards.
  - **The draw** (`BJDeck::DrawCard 0x00739090`, read in the GOG exe too):
    a plain draw takes a random card of those left and **passes over the
    next one unseen** (the count drops twice). Luck draws |Luck − 5|
    candidates, and FNV's array holds 5, so **Luck above 10 helps no more
    than 10** (FNV would write past the array). From a total over 9 it takes
    the highest total of 21 or less; from 9 or less the nearest to 21 or
    to 11. The lucky (player) or unlucky (dealer) text shows only when Luck
    changed the card.
  - **The deal** (`0x007393f0`): dealer, player plain; dealer (Luck for
    the dealer), player (Luck). A player 21 is a natural; **the dealer
    peeks**: a dealer 21 loses the round at once, or pushes against a
    natural. Double needs chips for twice the bet and a total other than 11
    to also allow a split.
  - **Split** (`0x007395a0`) needs two cards of **one rank** (kings split,
    a jack and a queen don't; the wiki's "no split on queens or kings" is
    not in the code) and chips for twice the bet. Each hand gets a plain
    card. FNV tests the first hand's 21 twice, so **a first split hand of
    21 pays both hands as naturals** at once. After a split, Double Down
    doubles the **first** hand even while the split hand is in play
    (`0x00739650`). Kept as FNV plays.
  - **Hit** ends a hand at 21 or more, or 7 cards; **Stay** ends the whole
    turn, both hands; **Surrender** only before any action, losing half the
    bet rounded up (bet 5 loses 3), and pays nothing on a split hand.
  - **The dealer** plays unless every hand busted or surrendered, or a
    natural ended the deal: below 17, or 17 with **any ace** in hand at a
    casino without the soft-17 flag (so ace-six-king hits too); 7 cards at
    most.
  - **Payouts** (`0x00734db0`): win 1:1, natural bet × payout + 0.5
    truncated (5 pays 8 at 3:2, 6 at the Atomic Wrangler's 6:5); a doubled
    bet halves again after the round, and the bet never exceeds the chips.
    **Steps** as roulette up; down −1 to 10, then to the step's multiple
    (5, 10, 25, 100, 500); Bet Max is the max or the chips held.
  - **Texts** (`records.BLACKJACK_TEXTS`): `sDealText`, `sHitText`,
    `sStayText`, `sDoubleDownText`, `sSplitText`, `sSwitchHandsText`,
    `sSurrenderText`, `sBetMax`, `sExit`, the chip, bet and earnings labels,
    `sYouWin`/`sLuckyWinText`, `sYouLose`/`sUnluckyLoseText`,
    `sYouBreakEvenText`.
  - Rounds add misc stat 41; not counted yet, as slots' and roulette's.
- **Card faces** (`LoadCardDeckResources 0x00731d70`): from the casino's
  card back, the name up to its last `_`, then suit (`hcds`) and number
  (01 the ace, 13 the king): `cardT_Back.dds` → `cardT_h01.dds`.
  `records.face_textures` stages the 52 faces of every back a casino
  names; the menu mounts them per deck.
- **The screen:** a drawn felt; the dealer's row (first card face down
  while you play), your hand and the split hand beside it (the hand in
  play outlined), totals under each. Betting row: Deal, Increase and
  Decrease Bet, Bet Max, Exit; play row: Hit, Double Down, Split, Switch
  Hands, Surrender, Stay, the ones not allowed dimmed. Enter deals or
  hits, Left/Right change the bet. **Esc and Exit work only between
  rounds** (mid-round the bet is on the table, as FNV). No felt texture,
  dealing animation or sounds yet (phase 6); no gamepad cursor.
- **The loop:** `Open(1, ...)` now opens the menu; `OpenBlackjack` hands
  it the casino, chips, min and max, earnings, Luck, a seed, the casino's
  decks, reshuffle share, payout, soft-17 flag, card backs and texts; each
  round sends `F3NV_CasinoRound(net)` and `Settle` banks it. Under the min
  bet the bank shows the broke text and closes, as at roulette.
- **Self-test:** `cqf FNV_Casino SelfTest 5` logs a third line,
  `blackjack 5 ...`: the Tops' rules (soft 17 hit), seeds 1-3, 20 rounds
  each of a fixed play (split pairs, double on 10-11, hit below 17), each
  as `dealer/hand/split ranks=net`. Paste it after `selftest ` into
  `tests/casino/selftest.txt`; `test_the_movies_blackjack_matches_the_model`
  checks it. A long run of that play returns about −52% of the bet at
  Luck 1, −5% at Luck 5 and +74% at Luck 10.
- **In game:** at the Tops, play a few rounds with each action; split a
  pair of kings, double after a split, surrender a 16; at Gomorrah watch
  the dealer hit ace-six; with too few chips for twice the bet, Double
  Down and Split stay dimmed; Esc mid-round does nothing.

### <a id="phase-5"></a>Phase 5. Caravan (L)

- Collection and deck containers; `AddCard`; Ringo's lesson works.
- Screens: deck builder (owned cards by set, Add, Remove, Randomize, 30
  minimum), bet (ante, raise to the cap), table (3 tracks a side, hand of
  8, discard), results.
- Rules and AI from [3.6](#rules-caravan), the four modes.
- Pot: caps and CMNY items move between player and opponent.
- Counters for Know When to Hold 'Em I/II and Know When to Fold 'Em.
- **Tests:** reference model of every placement rule and effect (one test
  per rule, from the decomp's cases), the win check, the bet cap; AI vs AI
  simulations at each mode (win rates rise with mode); traces against the
  AS3 engine.
- **In game:** Ringo's lesson and a first game; No-bark and Johnson Nash
  (funds with NCR money); the 5-game merchant limit; a Joker on an Ace.

<a id="caravan-built"></a>**Built 2026-11-12, not played** (`as3/f3nv/casino/Caravan.as`,
`CaravanAi.as`, `CaravanScreen.as`; `tests/casino/caravan.py`, `caravan_ai.py`):
- **Rules, read in the decompile** (`caravanmenu.cpp`, the AI in
  `staging/blk_00740000_od.cpp`), sharper than [3.6](#rules-caravan):
  - **Cards** (CCRD's two INTVs): suit 1 hearts, 2 spades, 3 diamonds,
    4 clubs, 5 Joker; value 1 the ace to 10, 12 Jack, 13 Queen, 14 King,
    15 Joker (11 unused).
  - **Placement** (`CanPlaceCard 0x0074f6c0`): caravans 0-2 are the
    player's, 3-5 the opponent's, caravan k facing 5 - k. At the opening
    any number (10 or less) on an empty cell. A face card goes on any card,
    either side, with fewer than 3 faces on it; a Queen only on a caravan's
    last card. A number goes on its own side's next row, never the last
    card's value, and the caravan's way (up or down) unless it matches the
    caravan's suit.
  - **Points, way and suit** (`UpdateHandStats 0x0074ee70`): each King
    doubles its card (twice is x4); one card has no way; with more, the way
    is the last two cards', the suit the last card's, and each Queen on the
    last card sets its suit and turns the way.
  - **A Jack** takes its card and that card's faces; later cards move up.
    **A Joker** on a number takes every other card of that value, on an ace
    every other card of the ace's suit, on both sides; it stays. FNV's
    cascade (states 17-19) corrects later rows once, so with three targets
    in one caravan the third survives, and a seven-card caravan keeps a
    copy of its last card; kept as FNV plays.
  - **The deal** (`0x0073ea90`): eight cards each, one each in turn from a
    random place (the deck's last card fills it); after that each draw
    takes a random card to the end of the hand. The opponent always moves
    first. At the opening each side opens its caravans in order (the
    player's from 0, the opponent's from 5 down) with no draw; the player's
    discards there are free, the opponent's end its turn.
  - **A turn** is one action: play a card (the hand draws), discard a card
    (only with a card to draw, for the player), or discard a caravan (not
    at the opening, with a card on one of them). The result is checked
    after every action.
  - **The result** (`CheckCaravanResult 0x00752e20`): a caravan sells at
    21-26 and wins its pair if the other is unsold or lower; equal sold
    caravans wait. All three pairs decided: the majority wins. Else the
    player out of cards (hand and deck) loses, then the opponent.
  - **Money** (`0x0073d650`, `0x0073d020`, `0x0074a090`, `0x0074cc70`):
    funds are caps plus each Caravan money item's value held (NCR $100 40,
    $20 8, $5 2, Aureus 100, Denarius 4, mangled 2). The opponent antes its
    funds x share, truncated; it matches a raise up to its funds x share x
    (1 + Barter / 100), never past its funds. Each side risks the smaller
    bet (the pot is twice it). The loser pays each money item in turn, as
    many as fit in what is left, then caps for the rest.
  - **The deck builder:** 30 to 108 cards; Randomize picks 30 if the
    collection has 30 or fewer, else a random size from 30 to one under
    the whole collection. Play rewrites the player's two lists.
  - **Texts** (`records.CARAVAN_TEXTS`): FNV's settings (`sPlayCaravanText`,
    `sTotalFundsText`, `sCurrentAnteText`, `sAntePotText`, `sAutoMatchText`,
    `sRaiseText`, `sPlaceCardText`, `sDiscardCardText`, `sForfeitGameText`,
    `sQuitCaravanText`, the results' `sCaravan*Text`) and its menu XML's
    strings ("Your Current Ante: ", "Add", "Remove"); "Randomize" and
    "Discard Caravan" are ours.
- **Drift, our choices:**
  - The opening ends when all six caravans have a card. FNV ends it only
    after the player opens caravan 2 with caravan 3 open; after an opponent
    discard at the opening that never happens and FNV runs past its board.
    Where FNV's opening AI reads a card it never set (no such card in
    hand), its first number card opens.
  - Raise adds FNV's quantity menu's small step (a twentieth of the room,
    whole tens above 10) per press instead of a slider.
  - Money is paid in the money list's order (by FormID), not the
    inventory's.
  - The deck builder shows 60 card faces a page; a click adds or removes.
  - Caravan wins and losses don't count toward the challenges yet (misc
    stats 37 and 38), as the other games'; FNV's five totals (won, lost,
    games won and lost, the biggest pot) are kept by the bank and shown.
  - No tutorial message, dealing animation, sounds or gamepad cursor yet
    (phase 6).
- **The loop:** `OpenCaravan` checks FNV's 30 cards and opens the menu;
  `OpenCaravanMenu` hands it the opponent's name, both funds, the share,
  Barter, the mode, a seed, the card table (`CardTable`: each
  `F3NV_CaravanCardList` card's "suit,value,face,back", 30 to a string),
  the owned and deck cards as bit chunks, the opponent's deck as card
  places, the five totals and the texts. Play sends the deck back as
  `F3NV_CaravanDeck(chunk, bits)` events (each sets its 30 cards in or out
  of the deck); the end sends `F3NV_CaravanResult(won, stake)` and the
  bank pays (`Pay`) and counts.
- **Self-test:** `cqf FNV_Casino SelfTest 5` logs a fourth line,
  `caravan 3 ...`: one game per seed 1-3 between two standard 54-card
  decks, both sides by the AI's rules at mode 3, each as
  `W or L:moves:the six caravans' points`.
  `test_the_movies_caravan_matches_the_model` checks it.
- **Measured:** AI against AI, every pairing of modes wins about half its
  games (200 games each): FNV's modes change only the opening, a King's
  and a Joker's scores and the caravan discard, not the strength. A game
  takes about 39 moves.
- **In game:** Ringo's first game (a deck from his cards); bet, Auto-Match
  and Raise against No-bark or Johnson Nash with NCR money in hand;
  Randomize a deck; a Jack, a King, a Queen and a Joker on an ace;
  forfeit a game; check caps and NCR money after a win and a loss.

<a id="caravan-ai"></a>**The AI** (`CaravanOwner 0x0074fdc0`, checked
against the GOG exe): no randomness. At the opening it discards a face
card when it holds over five of the wrong cards (a Joker first), else mode
0 opens with its last number, 1-2 its first 6-10 or under-4 card (the kind
it holds more of), 3 the card nearest 6. In play it scores, caravan by
caravan: under 21, a number or King that keeps it at 26 or less (scored by
the total); sold but behind, a Jack, a Joker (mode 1 up) or a number that
catches up; sold, a number or King that stays sold; bust, a Jack that
fixes it; then a Jack or King against the player's caravans; with nothing,
a hand discard or a caravan discard. The list is sorted by the C runtime's
qsort (not stable, so equal scores come out in FNV's order) and the first
is played. FNV's quirks are kept: the scratch record keeps fields between
candidates (a number past 26 can be pushed with an old score), a Jack is
valued on the player's caravan but played on its own, the Joker's loss
counts aces or suits the wrong way round, a King on a sold caravan counts
twice its card, the Queen is never played, and a hand discard scores its
place in the hand.

### <a id="phase-6"></a>Phase 6. Dead Money and polish (S)

- The Sierra Madre's three games (power switch, holograms, 100 roulette
  max, 25 slots max), SM chips in the vending recipes, the voucher.
- Sounds, help screens, gamepad pass, text from the string table.
- **In game:** the Sierra Madre after Put the Beast Down.

### <a id="phases-tests"></a>How the rules are tested outside the game

AS3 can't run in the test suite, so each game has a **Python reference
model** in `tests/casino/` written from [section 3](#rules), with the same
small seeded RNG as the AS3 code. The model is the spec: its unit tests
pin every rule. The movie's self-test mode replays a set of seeds and
reports each result; a test compares those reports (captured once per
phase by the user opening the self-test from the console) with the model's.
A headless AS3 runner (Ruffle) would remove that game step and is worth
trying in phase 0.

---

## <a id="phase-3d"></a>6. The 3D phase (later)

What full tables need beyond the 2D version (rules, bank and data stay):
- **A 3D surface in the menu:** FNV renders the `terminals\nv_*` scenes
  inside its menus. FO4 does this for the Pip-Boy inventory and the
  workshop (its `Inventory3DManager`), but only for single items. Drawing
  a table scene with its own camera, light and animations needs F3NV.dll
  (load the converted NIFs, place them, drive the camera): a DLL feature.
- **Or the world as the table:** sit the player at the converted table
  furniture, with the dealer NPC and placed card and chip objects moved by
  script, and a fixed camera. FO4 has no script camera control beyond
  first/third person, so this too needs a DLL camera, plus animations for
  dealers (FNV's are clip-driven, see [idles](fo4_idles.md)).
- **Converted minigame NIFs:** 102 files with cameras, lights and
  `NiControllerSequence` animations; the NIF converter has not met
  cameras in a scene file.
- **Dealers:** the dealer NPCs and their packages (`NVRouletteDealerScript`,
  `RouletteDealerPackage0/1`) already convert; they would need idles that
  match the cards.
- Size: L or more; start only after 2D is played.

---

## <a id="drift"></a>7. Drift from FNV

To record in [fo4_drift.md](fo4_drift.md) as each piece is built:
- flat 2D tables instead of FNV's lit 3D scenes;
- Caravan money is a FO4 MISC item; FO4 vendors barter it as an item at
  its cap value instead of as currency;
- results are settled after each round, not on leaving the table (FNV's
  menu settled on exit; the net effect is the same unless the game crashes);
- the Caravan collection is a hidden container, so cards appear briefly in
  the inventory when picked up before moving there (FNV never showed them);
- the menu is a FO4 menu (FO4 fonts and HUD color, not FNV's amber
  layout).

---

## <a id="questions"></a>8. Open questions

1. **Compiler:** may phase 0 try FFDec first (nothing to install) and fall
   back to installing the Apache Flex SDK, or would you rather use Flex
   from the start?
2. **Rules in the menu (AS3), not F3NV.dll.** The earlier sketch in
   fo4_build_next put the rules in the DLL, which would make them testable
   in C++ but adds a DLL feature. This plan keeps the DLL out. Agreed?
3. **FNV's bugs:** keep them (roulette 0 never pays; the opening-round
   discard that gives an extra turn; Vikki & Vance's slots checking
   Gomorrah's floor manager) or fix them? The plan keeps the authored
   scripts as they are and suggests fixing the two engine bugs, since our
   menu re-implements the engine.
4. **Luck bias:** keep FNV's hidden Luck help in blackjack and slots
   exactly (Luck 10 makes them strongly profitable)? The plan keeps it.
5. **Caravan cards in the inventory:** hidden in a container, as FNV
   (planned), or kept visible as Pip-Boy MISC items so the player can see
   and drop them?
6. **NCR dollars and Legion coins** (CMNY) as MISC items with a cap value:
   is bartering them as items at FO4 vendors acceptable, or should vendors
   (through F3NV.dll's vendor code) count them as money?
7. **Gamepad:** is controller play required in the first release, or is
   mouse and keyboard enough until phase 6?
8. **Lucky Horseshoes** (Festus at Sunset Sarsaparilla) is not one of the
   engine's games; leave it out of this plan?

<a id="answers-taken"></a>**Taken for now (2026-11-08), until the user says otherwise:**
1. FFDec; it works ([toolchain](#toolchain-found)), no Flex SDK.
2. Rules in the menu's AS3, Papyrus the bank, no new F3NV.dll code.
3. Authored scripts kept as they are (Vikki & Vance's slots still check
   Gomorrah's floor manager); the engine bugs our menu re-implements get
   fixed when that game is built (roulette's 0, Caravan's opening discard).
4. FNV's Luck help kept exactly (slots built that way).
5. Hidden, as FNV: and as two FormLists rather than containers
   ([records](#records-built)); the card leaves the inventory when picked up.
6. Items at their cap value; vendors don't count them as money.
7. Mouse and keyboard first; FO4's own controls are wired (`Accept`,
   `Cancel`, `Left`, `Right`), so a gamepad may already work. The spike
   logs which inputs arrive.
8. Left out.

---

## <a id="summary"></a>9. Main decisions and biggest risks

**Decisions:**
- A custom Scaleform menu of our own, opened through F4SE; no Pip-Boy page,
  no message boxes.
- Rules in the menu (AS3), as in FNV; Papyrus is the bank and the save; no
  new F3NV.dll feature.
- CSNO → a data quest per casino carrying the rules and its earnings;
  CHIP, CMNY, CCRD → MISC; CDCK → FormList; the Caravan collection in
  hidden containers.
- Art from the user's FNV install at build time; nothing Bethesda's in the
  repo.
- Order: spike and records, then slots, roulette, blackjack, Caravan, Dead
  Money.

**Risks:**
1. **No AS3 compiler yet**, and the project has never shipped a custom FO4
   menu. Everything waits on phase 0.
2. **F4SE custom-menu input** (gamepad, keyboard, input after close) is
   unproven here; if it fails, the menu needs DLL registration
   ([4.8](#design-dll)).
3. **The Caravan AI and rules are the largest piece** and the decompile's
   AI was read in outline only; matching FNV's play exactly will take
   iteration (accept drift: a sensible greedy opponent is the goal).
4. **AS3 can't be unit-tested here**; the reference-model-plus-self-test
   scheme catches divergence but needs one in-game capture per phase.
5. **Converted scripts that touch these forms** (property types change from
   `ObjectReference` to the new types) must recompile cleanly across all
   ~13,500 scripts; a type mismatch shows only at compile.
