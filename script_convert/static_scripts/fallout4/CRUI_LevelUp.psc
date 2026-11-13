ScriptName CRUI_LevelUp extends Quest
{Fallout 4 only. A level-up in place of the game's: the perk and skill points to spend (saved with the game as this
script's variables), taking a perk and raising a skill, the perk list, each perk's rank and eligibility, and our
level-up menu (Interface/CRUI_LevelUp.swf, registered with F4SE), also the tag skill and trait menus. Its partner
CRUI_LevelUpHolder (Holder) keeps the tagged skills, is where Get() finds it, and decides what opening each menu does.
What the menu shows is written as tables (the skills' here, each plugin's perks and traits on its
CRUI_LevelUpTable), so opening it asks the engine only for the ranks and traits held and the player's values.
TagsChosen is sent once the tag menu's picks are set.
See docs/fork/fo4_level_up_plan.md#prkf}

CustomEvent PerkTaken
CustomEvent TagsChosen
CustomEvent SkillRaised
CustomEvent SkillTagged
CustomEvent SkillUntagged
CustomEvent MenuClosed

String Property MenuName = "CRUI_LevelUp" AutoReadOnly Hidden
{The menu's name, also its movie's name under Interface.}
Int Property MenuFlags = 0x800049D AutoReadOnly Hidden
{The casino menu's flags (pauses, cursor, menu context, modal, no pause menu; no Custom Rendering, played 2026-11-08).}
Int Property ExtendedFlags = 2 AutoReadOnly Hidden
{F4SE extended flags: drop the cursor when a gamepad is in use.}
Int Property Chunks = 8 AutoReadOnly Hidden
{How many stacks ask the engine for ranks and values at once: each native call costs its stack a frame.}
Int Property LevelUpMode = 0 AutoReadOnly Hidden
{Open's modes: a level-up (skills, perks, taken), the tag skill menu, the trait menu.}
Int Property TagsMode = 1 AutoReadOnly Hidden
Int Property TraitsMode = 2 AutoReadOnly Hidden

CRUI_LevelUpHolder Property Events Auto Const
{The holder (Holder); None: the CRUI_LevelUpHolder on this quest.}
FormList Property Perks Auto Const
{The level-up list's perks, first ranks only (FNV_Perks).}
FormList Property Skills Auto Const
{The skills the menu raises (FNV_Skills).}
FormList Property Specials Auto Const
{The seven SPECIAL actor values; the menu's values are these, then Skills.}
Int Property SkillCap = 100 Auto
{The highest a skill's base can be raised with skill points; an MCM option (fo4_import/level_up/options.py).}
Bool Property ShowAllPerks = False Auto
{Whether the perk page opens with every perk shown, the ones the player can't take dimmed; an MCM option.}
String Property SkillNames Auto Const
{Skills' names, SEP between; SkillDescriptions and SkillImages alike.}
String Property SkillDescriptions Auto Const
String Property SkillImages Auto Const
FormList Property Tables Auto Const
{Every plugin's perk and trait table (CRUI_LevelUpTable), the game's beside this script on its own quest.}

Int PerkPoints
Int SkillPoints
String[] heldParts
String[] valueParts
String[] tagParts
String[] traitParts
Int pending
Int mode
Int wanted
Int bonus
CRUI_LevelUpTable[] shown
Int[] perkCounts
Int[] traitCounts
Int[] rowCounts
Int perkTotal
Int traitTotal
Int tablePerks
Int tableRows
Perk[] Added
Perk[] extra
String[] extraParts
String unlisted
Var[] ready

; ---------------------------------------------------------------------------
; For other mods (docs/fork/fo4_level_up_plan.md#api)
; ---------------------------------------------------------------------------

CRUI_LevelUp Function Get() Global
  {The running game's level-up, for other mods: CRUI_LevelUp.Get().AddPerkPoints(1). Cleanroom UI's shared holder
  (CRUI_LevelUpHolder.Shared) holds it, set as its owner starts and each time our menu opens; None without that
  plugin or before it is set.
  See docs/fork/fo4_level_up_plan.md#plugin}
  CRUI_LevelUpHolder holder = CRUI_LevelUpHolder.Shared()
  If !holder
    Return None
  EndIf
  Return holder.Running()
EndFunction

CRUI_LevelUpHolder Function Holder()
  {Events, else the holder on this quest.}
  If Events
    Return Events
  EndIf
  Return (Self as Quest) as CRUI_LevelUpHolder
EndFunction

Function Announce()
  {Be the level-up Get() finds: held by this host's holder and by Cleanroom UI's shared one.}
  CRUI_LevelUpHolder holder = Holder()
  If holder
    holder.Hold(Self)
  EndIf
  CRUI_LevelUpHolder shared = CRUI_LevelUpHolder.Shared()
  If shared && shared != holder
    shared.Hold(Self)
  EndIf
EndFunction

Bool Function AddPerk(Perk akPerk)
  {List perk akPerk (a first rank) in the level-up menu after the build's, kept by the save; False when already added.
  Its name, description, image, level and ranks are read from the perk as the menu opens, and whether it can be
  taken is the game's own test of its conditions. A perk a plugin's table lists already is shown once.}
  If !akPerk || (Added && Added.Find(akPerk) >= 0)
    Return False
  ElseIf !Added
    Added = new Perk[0]
  EndIf
  Added.Add(akPerk)
  Return True
EndFunction

Bool Function RemovePerk(Perk akPerk)
  {Take perk akPerk, added by AddPerk, out of the level-up menu; False when it was not added.}
  If !Added || Added.Find(akPerk) < 0
    Return False
  EndIf
  Added.Remove(Added.Find(akPerk))
  Return True
EndFunction

Function OpenLevelUpMenu()
  {Open the level-up menu (skills, perks, taken) once no menu is open, as the holder's OpenLevelUp decides (the
  FO3/FNV conversion gives the levels gained since the last time their points first). MenuClosed is sent when it
  closes.}
  Announce()
  Holder().OpenLevelUp()
EndFunction

Function OpenTagMenu(Int aiTags)
  {Open the tag skill menu for aiTags skills tagged in all (FNV: 3 at Doc Mitchell's; the tags held plus one for
  Tag!). Tags chosen before stay; TagsChosen is sent once the picks are set.}
  Announce()
  Holder().OpenTags(aiTags)
EndFunction

Function OpenTraitMenu(Int aiTraits = 0)
  {Open the trait menu for up to aiTraits traits (0: the holder's own count).}
  Announce()
  Holder().OpenTraits(aiTraits)
EndFunction

Int Function GetPerkPoints()
  Return PerkPoints
EndFunction

Int Function GetSkillPoints()
  Return SkillPoints
EndFunction

Int Function AddPerkPoints(Int aiPoints)
  {Adds aiPoints perk points (negative takes some away, never below 0); the points left.}
  PerkPoints += aiPoints
  If PerkPoints < 0
    PerkPoints = 0
  EndIf
  Return PerkPoints
EndFunction

Int Function AddSkillPoints(Int aiPoints)
  {Adds aiPoints skill points (negative takes some away, never below 0); the points left.}
  SkillPoints += aiPoints
  If SkillPoints < 0
    SkillPoints = 0
  EndIf
  Return SkillPoints
EndFunction

; ---------------------------------------------------------------------------
; Tag skills
; ---------------------------------------------------------------------------

Bool Function IsTagged(ActorValue akSkill)
  Return Holder().IsTagged(akSkill)
EndFunction

Bool Function Tag(ActorValue akSkill)
  {Tags akSkill (Holder) and sends SkillTagged; False when it already was. A tag bonus is the holder's owner's to
  give.}
  If !Holder().Tag(akSkill)
    Return False
  EndIf
  SendCustomEvent("SkillTagged", FormArgs(akSkill))
  Return True
EndFunction

Bool Function Untag(ActorValue akSkill)
  {Untags akSkill (Holder) and sends SkillUntagged; False when it was not tagged.}
  If !Holder().Untag(akSkill)
    Return False
  EndIf
  SendCustomEvent("SkillUntagged", FormArgs(akSkill))
  Return True
EndFunction

; ---------------------------------------------------------------------------
; Skills and perks
; ---------------------------------------------------------------------------

Int Function RaiseSkill(ActorValue akSkill, Int aiPoints)
  {Spends up to aiPoints skill points raising akSkill's base, no higher than SkillCap; the points spent.}
  Actor player = Game.GetPlayer()
  Float base = player.GetBaseValue(akSkill)
  Int spend = aiPoints
  If spend > SkillPoints
    spend = SkillPoints
  EndIf
  If base + spend > SkillCap
    spend = (SkillCap - base) as Int
  EndIf
  If spend <= 0
    Return 0
  EndIf
  player.SetValue(akSkill, base + spend)
  SkillPoints -= spend
  Var[] args = new Var[3]
  args[0] = akSkill
  args[1] = spend
  args[2] = base + spend
  SendCustomEvent("SkillRaised", args)
  Return spend
EndFunction

Perk Function NextRank(Perk akPerk)
  {The rank of akPerk (a first rank) the player would take next; None when they hold every rank.}
  Actor player = Game.GetPlayer()
  Perk rank = akPerk
  Int i = 0
  While rank && i < akPerk.GetNumRanks()
    If !player.HasPerk(rank)
      Return rank
    EndIf
    rank = rank.GetNextPerk()
    i += 1
  EndWhile
  Return None
EndFunction

Int Function Rank(Perk akPerk)
  {How many of akPerk's (a first rank) ranks the player holds.}
  Actor player = Game.GetPlayer()
  Perk rank = akPerk
  Int held = 0
  While rank && held < akPerk.GetNumRanks() && player.HasPerk(rank)
    held += 1
    rank = rank.GetNextPerk()
  EndWhile
  Return held
EndFunction

Bool Function Eligible(Perk akRank)
  {Whether the player meets akRank's level and conditions (the engine's own test of the converted requirements).}
  Actor player = Game.GetPlayer()
  Return akRank && player.GetLevel() >= akRank.GetLevel() && akRank.IsEligible(player)
EndFunction

Bool Function CanTake(Perk akPerk)
  {Whether the player can take akPerk's (a first rank) next rank now: a rank left, a perk point, and eligible.}
  Return PerkPoints > 0 && Eligible(NextRank(akPerk))
EndFunction

Bool Function TakePerk(Perk akPerk)
  {Takes akPerk's (a first rank) next rank for a perk point and sends PerkTaken with that rank; False when it can't.}
  If !CanTake(akPerk)
    Return False
  EndIf
  Perk rank = NextRank(akPerk)
  Game.GetPlayer().AddPerk(rank)
  PerkPoints -= 1
  SendCustomEvent("PerkTaken", FormArgs(rank))
  Return True
EndFunction

Perk[] Function PerkList(Int aiShow)
  {The level-up list's perks (first ranks) with a rank left: aiShow 0 all, 1 those the player is eligible for, 2 those
  they are not. Perk points are not counted.}
  Perk[] out = new Perk[0]
  Int i = 0
  While i < Perks.GetSize()
    Perk first = Perks.GetAt(i) as Perk
    Perk rank = NextRank(first)
    If rank && (aiShow == 0 || (aiShow == 1) == Eligible(rank))
      out.Add(first)
    EndIf
    i += 1
  EndWhile
  Return out
EndFunction

; ---------------------------------------------------------------------------
; The menu
; ---------------------------------------------------------------------------

Function Show(Int aiMode, Int aiCount, Int aiBonus)
  {Our menu in mode aiMode (Open) as soon as no menu is open: its data gathered first (Prepare), so the gathering
  overlaps the wait, without the settling a message box needs.
  See docs/fork/fo4_level_up_plan.md#open-delay}
  Prepare(aiMode, aiCount, aiBonus)
  While Utility.IsInMenuMode() || UI.IsMenuOpen("PipboyMenu") || UI.IsMenuOpen(MenuName)
    Utility.WaitMenuMode(0.25)
  EndWhile
  Open(aiMode, aiCount, aiBonus)
EndFunction

Function Open(Int aiMode = 0, Int aiCount = 0, Int aiBonus = 0)
  {Open our menu in mode aiMode (LevelUpMode, TagsMode for aiCount tags in all with aiBonus each, TraitsMode for up to
  aiCount traits): its data gathered first (Prepare) unless Prepare just did for this open; Send hands it over.}
  If !ready || mode != aiMode || wanted != aiCount || bonus != aiBonus
    Prepare(aiMode, aiCount, aiBonus)
  EndIf
  UI.OpenMenu(MenuName)
EndFunction

Function Prepare(Int aiMode, Int aiCount, Int aiBonus)
  {Gather what our menu shows in mode aiMode (Built) ahead of opening it, registered first. Show (or a holder's own
  opener) calls it while the Pip-Boy closes, so the gathering overlaps that wait. See docs/fork/fo4_level_up_plan.md#open-delay}
  mode = aiMode
  wanted = aiCount
  bonus = aiBonus
  Register()
  ready = Built()
EndFunction

Function Register()
  {Register the menu with F4SE (registrations do not last past a load) and its events, each once; be the level-up
  Get() finds.}
  Announce()
  If !UI.IsMenuRegistered(MenuName)
    UI:MenuData data = new UI:MenuData
    data.menuFlags = MenuFlags
    data.extendedFlags = ExtendedFlags
    UI.RegisterCustomMenu(MenuName, MenuName, "root1", data)
  EndIf
  UnregisterForMenuOpenCloseEvent(MenuName)
  RegisterForMenuOpenCloseEvent(MenuName)
  UnregisterForExternalEvent("CRUI_LevelUpTake")
  UnregisterForExternalEvent("CRUI_LevelUpRaise")
  UnregisterForExternalEvent("CRUI_LevelUpClose")
  UnregisterForExternalEvent("CRUI_LevelUpLog")
  UnregisterForExternalEvent("CRUI_LevelUpTags")
  UnregisterForExternalEvent("CRUI_LevelUpTraits")
  RegisterForExternalEvent("CRUI_LevelUpTake", "OnMenuTake")
  RegisterForExternalEvent("CRUI_LevelUpRaise", "OnMenuRaise")
  RegisterForExternalEvent("CRUI_LevelUpClose", "OnMenuClose")
  RegisterForExternalEvent("CRUI_LevelUpLog", "OnMenuLog")
  RegisterForExternalEvent("CRUI_LevelUpTags", "OnMenuTags")
  RegisterForExternalEvent("CRUI_LevelUpTraits", "OnMenuTraits")
EndFunction

Event OnMenuOpenCloseEvent(String asMenuName, Bool abOpening)
  {Our menu open: Send. Closed: MenuClosed (its mode, the perk and skill points left).}
  If asMenuName != MenuName
    Return
  ElseIf abOpening
    Send()
    Return
  EndIf
  Var[] args = new Var[3]
  args[0] = mode
  args[1] = PerkPoints
  args[2] = SkillPoints
  SendCustomEvent("MenuClosed", args)
EndEvent

Function Send()
  {Hand the open menu what Prepare gathered (root1.Open), once; gathered now when nothing waits.}
  Var[] args = ready
  ready = None
  If !args
    args = Built()
  EndIf
  UI.Invoke(MenuName, "root1.Open", args)
EndFunction

Var[] Function Built()
  {What the menu shows, in Character.as's order: every plugin's perk, trait and requirement tables joined (Collect,
  Merged), the player's points, level, sex and cap, the ranks held and values (asked in parallel, Gather), the tagged
  skills, the mode and the traits held, whether to show every perk at first, and each table's perk and row counts
  (the menu moves each table's row owners and perk targets by them).}
  Float started = Utility.GetCurrentRealTime()
  Actor player = Game.GetPlayer()
  Collect()
  Int specialCount = Specials.GetSize()
  Gather(specialCount, Skills.GetSize())
  Var[] args = new Var[35]
  args[0] = PerkPoints
  args[1] = SkillPoints
  args[2] = player.GetLevel()
  args[3] = player.GetLeveledActorBase().GetSex()
  args[4] = SkillCap
  args[5] = Merged(0, perkCounts)
  args[6] = Merged(1, perkCounts)
  args[7] = Merged(2, perkCounts)
  args[8] = Merged(3, perkCounts)
  args[9] = Merged(4, perkCounts)
  args[10] = JoinedParts(heldParts)
  args[11] = SkillNames
  args[12] = SkillDescriptions
  args[13] = SkillImages
  args[14] = JoinedParts(valueParts)
  args[15] = JoinedParts(tagParts)
  args[16] = specialCount
  args[17] = Merged(8, rowCounts)
  args[18] = Merged(9, rowCounts)
  args[19] = Merged(10, rowCounts)
  args[20] = Merged(11, rowCounts)
  args[21] = Merged(12, rowCounts)
  args[22] = Merged(13, rowCounts)
  args[23] = Merged(14, rowCounts)
  args[24] = unlisted
  args[25] = mode
  args[26] = wanted
  args[27] = bonus
  args[28] = Merged(5, traitCounts)
  args[29] = Merged(6, traitCounts)
  args[30] = Merged(7, traitCounts)
  args[31] = JoinedParts(traitParts)
  args[32] = ShowAllPerks
  args[33] = GroupCounts(perkCounts)
  args[34] = GroupCounts(rowCounts)
  Debug.Trace("CRUI_LevelUp: gathered in " + (Utility.GetCurrentRealTime() - started) + "s, mode " + mode + ", " \
              + shown.Length + " tables")
  Return args
EndFunction

String Function GroupCounts(Int[] aiCounts)
  {aiCounts, one per shown table, then the added perks' count when there are any (one each, as perks or rows), SEP
  between: the groups the menu moves indexes by.}
  String out = ""
  Int t = 0
  While t < aiCounts.Length
    out = CRUI_LevelUpTable.Joined(out, "" + aiCounts[t], t)
    t += 1
  EndWhile
  If extra.Length > 0
    out = CRUI_LevelUpTable.Joined(out, "" + extra.Length, t)
  EndIf
  Return out
EndFunction

Function Collect()
  {Into shown: this quest's table (the game's), then every other plugin's registered in Tables; and each one's perk,
  trait and row counts, of what the mode shows: perks and rows in a level-up, traits in the trait menu, neither in
  the tag menu (the rest count 0, so Send hands over and asks about none of them).}
  CRUI_LevelUpTable own = (Self as Quest) as CRUI_LevelUpTable
  shown = new CRUI_LevelUpTable[0]
  If own
    shown.Add(own)
  EndIf
  Int k = 0
  While Tables && k < Tables.GetSize()
    CRUI_LevelUpTable table = Tables.GetAt(k) as CRUI_LevelUpTable
    If table && shown.Find(table) < 0
      shown.Add(table)
    EndIf
    k += 1
  EndWhile
  perkCounts = new Int[shown.Length]
  traitCounts = new Int[shown.Length]
  rowCounts = new Int[shown.Length]
  tablePerks = 0
  tableRows = 0
  traitTotal = 0
  unlisted = ""
  Int t = 0
  While t < shown.Length
    If mode == LevelUpMode
      perkCounts[t] = shown[t].PerkCount()
      rowCounts[t] = shown[t].RowCount()
    ElseIf mode == TraitsMode
      traitCounts[t] = shown[t].TraitCount()
    EndIf
    tablePerks += perkCounts[t]
    tableRows += rowCounts[t]
    traitTotal += traitCounts[t]
    t += 1
  EndWhile
  extra = new Perk[0]
  extraParts = new String[16]
  If mode == LevelUpMode
    DescribeAdded()
  EndIf
  perkTotal = tablePerks + extra.Length
EndFunction

Function DescribeAdded()
  {Into extra and extraParts (CRUI_LevelUpTable.Text's order): the perks AddPerk listed that no shown table lists,
  each read from the perk, with one requirement row of kind 4, the game's own test of its next rank: the row's index,
  after every table's rows, goes in unlisted when the test passes. Owners count from 0, as a table's do.}
  Int i = 0
  While Added && i < Added.Length
    If Added[i] && extra.Find(Added[i]) < 0 && !Tabled(Added[i])
      extra.Add(Added[i])
    EndIf
    i += 1
  EndWhile
  Int j = 0
  While j < extra.Length
    Perk first = extra[j]
    AddPart(0, first.GetName(), j)
    AddPart(1, first.GetDescription(), j)
    AddPart(2, first.GetIconPath(), j)
    AddPart(3, "" + first.GetLevel(), j)
    AddPart(4, "" + first.GetNumRanks(), j)
    AddPart(8, "" + j, j)
    AddPart(9, "4", j)
    AddPart(10, "-1", j)
    AddPart(11, "0", j)
    AddPart(12, "1.0", j)
    AddPart(13, "0", j)
    AddPart(14, "", j)
    If Eligible(NextRank(first))
      unlisted = CRUI_LevelUpTable.Joined(unlisted, "" + (tableRows + j), (unlisted != "") as Int)
    EndIf
    j += 1
  EndWhile
EndFunction

Function AddPart(Int aiWhich, String asText, Int aiIndex)
  {asText, the added perk aiIndex's, onto extraParts[aiWhich] (a tab inside it would split the entry).}
  extraParts[aiWhich] = CRUI_LevelUpTable.Joined(extraParts[aiWhich], asText, aiIndex)
EndFunction

Bool Function Tabled(Perk akPerk)
  {Whether a shown table lists akPerk.}
  Int t = 0
  While t < shown.Length
    If shown[t].Lists(akPerk)
      Return True
    EndIf
    t += 1
  EndWhile
  Return False
EndFunction

String Function Merged(Int aiWhich, Int[] aiCounts)
  {Text aiWhich (CRUI_LevelUpTable.Text) of each shown table with entries (aiCounts, per table), then the added
  perks', SEP between.}
  String out = ""
  Int part = 0
  Int t = 0
  While t < shown.Length
    If aiCounts[t] > 0
      out = CRUI_LevelUpTable.Joined(out, shown[t].Text(aiWhich), part)
      part += 1
    EndIf
    t += 1
  EndWhile
  If extra.Length > 0 && (aiWhich < 5 || aiWhich > 7)
    out = CRUI_LevelUpTable.Joined(out, extraParts[aiWhich], part)
  EndIf
  Return out
EndFunction

Function Gather(Int aiSpecials, Int aiSkills)
  {Into heldParts, valueParts, tagParts and traitParts: the ranks held of each listed perk, the player's base value of
  each Specials and Skills entry and its tag (0 none, 1 a suggestion the tag menu may change, 2 tagged), then whether
  the player has each trait; asked by Chunks stacks at once (ScanChunk), so the frame each native call costs
  overlaps. In a level-up, one more stack asks for the perks the requirement rows test that no table lists
  (ScanUnlisted). Gives up after 10 seconds.}
  Int count = perkTotal + aiSpecials + aiSkills + traitTotal
  heldParts = new String[Chunks]
  valueParts = new String[Chunks]
  tagParts = new String[Chunks]
  traitParts = new String[Chunks]
  pending = Chunks
  If mode == LevelUpMode
    pending += 1
    CallFunctionNoWait("ScanUnlisted", new Var[0])
  EndIf
  Int k = 0
  While k < Chunks
    Var[] args = new Var[5]
    args[0] = k
    args[1] = k * count / Chunks
    args[2] = (k + 1) * count / Chunks
    args[3] = aiSpecials
    args[4] = aiSkills
    CallFunctionNoWait("ScanChunk", args)
    k += 1
  EndWhile
  Float waited = 0.0
  While pending > 0 && waited < 10.0
    Utility.WaitMenuMode(0.02)
    waited += 0.02
  EndWhile
EndFunction

Function ScanChunk(Int aiChunk, Int aiFirst, Int aiEnd, Int aiSpecials, Int aiSkills)
  {Gather's items aiFirst to aiEnd into its parts aiChunk: listed perks' ranks held, values and their tags (Specials,
  then Skills), traits held; the perks and traits asked of their tables (Over).}
  Actor player = Game.GetPlayer()
  Int traitsAt = perkTotal + aiSpecials + aiSkills
  heldParts[aiChunk] = Over(player, False, aiFirst, Least(aiEnd, perkTotal))
  traitParts[aiChunk] = Over(player, True, Most(aiFirst, traitsAt) - traitsAt, aiEnd - traitsAt)
  String values = ""
  String tags = ""
  Int i = Most(aiFirst, perkTotal)
  While i < Least(aiEnd, traitsAt)
    ActorValue value
    If i - perkTotal < aiSpecials
      value = Specials.GetAt(i - perkTotal) as ActorValue
    Else
      value = Skills.GetAt(i - perkTotal - aiSpecials) as ActorValue
    EndIf
    Int n = i - Most(aiFirst, perkTotal)
    values = CRUI_LevelUpTable.Joined(values, "" + player.GetBaseValue(value), n)
    tags = CRUI_LevelUpTable.Joined(tags, "" + TagState(value), n)
    i += 1
  EndWhile
  valueParts[aiChunk] = values
  tagParts[aiChunk] = tags
  pending -= 1
EndFunction

Function ScanUnlisted()
  {Gather's extra stack: onto unlisted, each table's rows testing a perk it does not list that the player has, moved
  to where the table's rows start (CRUI_LevelUpTable.UnlistedHeld).}
  Actor player = Game.GetPlayer()
  Int first = 0
  Int t = 0
  While t < shown.Length
    unlisted = shown[t].UnlistedHeld(player, first, unlisted)
    first += rowCounts[t]
    t += 1
  EndWhile
  pending -= 1
EndFunction

String Function Over(Actor akPlayer, Bool abTraits, Int aiFrom, Int aiTo)
  {The ranks akPlayer holds of the listed perks aiFrom to aiTo, counted across the shown tables, or whether they have
  each of those traits (abTraits); SEP between.}
  String out = ""
  Int start = 0
  Int part = 0
  Int t = 0
  While t < shown.Length && start < aiTo
    Int n = perkCounts[t]
    If abTraits
      n = traitCounts[t]
    EndIf
    Int from = Most(aiFrom - start, 0)
    Int upto = Least(aiTo - start, n)
    If from < upto
      String text
      If abTraits
        text = shown[t].TraitsHeld(akPlayer, from, upto)
      Else
        text = shown[t].RanksHeld(akPlayer, from, upto)
      EndIf
      out = CRUI_LevelUpTable.Joined(out, text, part)
      part += 1
    EndIf
    start += n
    t += 1
  EndWhile
  Int k = Most(aiFrom - tablePerks, 0)
  While !abTraits && k < Least(aiTo - tablePerks, extra.Length)
    out = CRUI_LevelUpTable.Joined(out, "" + Rank(extra[k]), part)
    part += 1
    k += 1
  EndWhile
  Return out
EndFunction

Int Function Least(Int aiA, Int aiB)
  If aiA < aiB
    Return aiA
  EndIf
  Return aiB
EndFunction

Int Function Most(Int aiA, Int aiB)
  If aiA > aiB
    Return aiA
  EndIf
  Return aiB
EndFunction

Int Function TagState(ActorValue akValue)
  {0 untagged, 1 tagged as SetPlayerTagSkill's suggestion (the tag menu may change it), 2 tagged.}
  CRUI_LevelUpHolder holder = Holder()
  If !holder.IsTagged(akValue)
    Return 0
  ElseIf holder.IsSuggested(akValue)
    Return 1
  EndIf
  Return 2
EndFunction

String Function JoinedParts(String[] asParts)
  {asParts' non-empty texts, SEP between.}
  String out = ""
  Int n = 0
  Int i = 0
  While i < asParts.Length
    If asParts[i] != ""
      out = CRUI_LevelUpTable.Joined(out, asParts[i], n)
      n += 1
    EndIf
    i += 1
  EndWhile
  Return out
EndFunction

Perk Function ListedPerk(Int aiIndex)
  {The first rank of listed perk aiIndex, counted across the shown tables; None outside them.}
  Int at = aiIndex
  Int t = 0
  While at >= 0 && t < shown.Length
    If at < perkCounts[t]
      Return shown[t].FirstRank(at)
    EndIf
    at -= perkCounts[t]
    t += 1
  EndWhile
  If at >= 0 && at < extra.Length
    Return extra[at]
  EndIf
  Return None
EndFunction

Function OnMenuTake(Int aiIndex)
  {The menu's pick of listed perk aiIndex: take its next rank (TakePerk, the engine's eligibility test), then tell
  the menu whether it was taken, the ranks now held and the perk points left (root1.Taken).}
  Perk first = ListedPerk(aiIndex)
  Bool taken = first && TakePerk(first)
  Var[] args = new Var[4]
  args[0] = aiIndex
  args[1] = taken
  args[2] = Rank(first)
  args[3] = PerkPoints
  UI.Invoke(MenuName, "root1.Taken", args)
EndFunction

Function OnMenuRaise(Int aiSkill, Int aiPoints)
  {The menu's aiPoints into skill aiSkill (of Skills): raise it (RaiseSkill), then tell the menu the points spent,
  the skill's base and the skill points left (root1.Raised).}
  ActorValue skill = Skills.GetAt(aiSkill) as ActorValue
  Int spent = RaiseSkill(skill, aiPoints)
  Var[] args = new Var[4]
  args[0] = aiSkill
  args[1] = spent
  args[2] = Game.GetPlayer().GetBaseValue(skill)
  args[3] = SkillPoints
  UI.Invoke(MenuName, "root1.Raised", args)
EndFunction

Function OnMenuTags(Int aiMask)
  {The tag menu's picks, bit i for Skills' entry i: each tagged or untagged, the suggestions done with, TagsChosen
  sent (the rules give the bonus), then the menu closed.}
  Int i = 0
  While i < Skills.GetSize()
    ActorValue skill = Skills.GetAt(i) as ActorValue
    If Math.LogicalAnd(aiMask, Math.LeftShift(1, i)) != 0
      Tag(skill)
    Else
      Untag(skill)
    EndIf
    i += 1
  EndWhile
  SendCustomEvent("TagsChosen", new Var[0])
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuTraits(Int aiMask, Int aiShown)
  {The trait menu's picks, bit i for trait i of the shown tables', of the first aiShown: each table adds the picked
  ones the player lacks and removes the others they have (CRUI_LevelUpTable.SetTraits); then the menu closed.}
  Actor player = Game.GetPlayer()
  Int first = 0
  Int t = 0
  While t < shown.Length
    shown[t].SetTraits(player, aiMask, first, aiShown)
    first += traitCounts[t]
    t += 1
  EndWhile
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuClose()
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuLog(String asText)
  Debug.Trace("CRUI_LevelUp: " + asText)
EndFunction

Var[] Function FormArgs(Form akForm)
  {A custom event's arguments: akForm alone.}
  Var[] args = new Var[1]
  args[0] = akForm
  Return args
EndFunction
