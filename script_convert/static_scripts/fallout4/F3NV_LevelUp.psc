ScriptName F3NV_LevelUp extends Quest
{Fallout 4 only. FO3/FNV's level-up in place of LevelUpMenuEx's PRKF.dll: the perk and skill points to spend (saved
with the game as this script's variables), taking a perk and raising a skill, the perk list, each perk's rank,
eligibility and requirement rows, and our level-up menu (Interface/F3NV_LevelUp.swf, registered with F4SE), which
F3NV_CharacterRules opens in place of LevelUpMenu, and as the tag skill and trait menus. The tagged skills are
F3NV_CharacterEvents'. The build writes what the menu shows as tables, so opening it asks the engine only for the
ranks and traits held and the player's values. TagsChosen is sent once the tag menu's picks are set. On the
character rules quest. See docs/fork/fo4_level_up_plan.md#prkf}

CustomEvent PerkTaken
CustomEvent TagsChosen

String Property MenuName = "F3NV_LevelUp" AutoReadOnly Hidden
{The menu's name, also its movie's name under Interface.}
Int Property MenuFlags = 0x800049D AutoReadOnly Hidden
{The casino menu's flags (pauses, cursor, menu context, modal, no pause menu; no Custom Rendering, played 2026-11-08).}
Int Property ExtendedFlags = 2 AutoReadOnly Hidden
{F4SE extended flags: drop the cursor when a gamepad is in use.}
Int Property Chunks = 8 AutoReadOnly Hidden
{How many stacks ask the engine for ranks and values at once: each native call costs its stack a frame.}
String Property SEP = "\t" AutoReadOnly Hidden
{Between a table's entries (fo4_import/spike/level_up.py's SEP).}
Int Property LevelUpMode = 0 AutoReadOnly Hidden
{Open's modes: a level-up (skills, perks, taken), the tag skill menu, the trait menu.}
Int Property TagsMode = 1 AutoReadOnly Hidden
Int Property TraitsMode = 2 AutoReadOnly Hidden

F3NV_CharacterEvents Property Events Auto Const
{The helper quest's character events, which hold the tagged skills.}
FormList Property Perks Auto Const
{The level-up list's perks, first ranks only (FNV_Perks).}
FormList Property Skills Auto Const
{The skills the menu raises (FNV_Skills).}
FormList Property Specials Auto Const
{The seven SPECIAL actor values; the menu's values are these, then Skills.}
Int Property SkillCap = 100 Auto Const
String Property PerkNames Auto Const
{The listed perks' names, SEP between; PerkDescriptions and PerkImages (paths under Textures) alike.}
String Property PerkDescriptions Auto Const
String Property PerkImages Auto Const
Int[] Property PerkLevels Auto Const
Int[] Property PerkRanks Auto Const
{Each listed perk's rank count; its ranks are the next that many of RankForms.}
Perk[] Property RankForms Auto Const
String Property SkillNames Auto Const
{Skills' names, SEP between; SkillDescriptions and SkillImages alike.}
String Property SkillDescriptions Auto Const
String Property SkillImages Auto Const
FormList Property Traits Auto Const
{The trait menu's traits (FNV_Traits); TraitNames, TraitDescriptions and TraitImages line up, SEP between.}
String Property TraitNames Auto Const
String Property TraitDescriptions Auto Const
String Property TraitImages Auto Const
Perk[] Property RequirementPerks Auto Const
{One row per requirement: the perk (first rank) it belongs to. The other Requirement arrays line up with it.}
Int[] Property RequirementKinds Auto Const
{0 an actor value, 1 the player's sex, 2 another perk, 3 the level.}
Form[] Property RequirementForms Auto Const
{The actor value or perk a row tests; None for sex and level.}
Int[] Property RequirementCompares Auto Const
{0 ==, 1 !=, 2 >, 3 >=, 4 <, 5 <=.}
Float[] Property RequirementValues Auto Const
Int[] Property RequirementOr Auto Const
{1 when a row ORs with the next.}
Int[] Property RequirementOwners Auto Const
{The row's perk's index in Perks; -1 for one not listed (a trait).}
Int[] Property RequirementTargets Auto Const
{Where the menu finds the tested value: an index into its values (Specials then Skills) or into Perks; -1 otherwise.}
String Property RequirementLabels Auto Const
{The tested actor value's or perk's name per row, SEP between ("" for sex and level).}

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
  Return Events.IsTagged(akSkill)
EndFunction

Bool Function Tag(ActorValue akSkill)
  {Tags akSkill (F3NV_CharacterEvents sends SkillTagged); False when it already was. The rules give the bonus.}
  Return Events.Tag(akSkill)
EndFunction

Bool Function Untag(ActorValue akSkill)
  {Untags akSkill (F3NV_CharacterEvents sends SkillUntagged); False when it was not tagged.}
  Return Events.Untag(akSkill)
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
; Requirement rows
; ---------------------------------------------------------------------------

Int[] Function RequirementRows(Perk akPerk)
  {The rows of akPerk's (a first rank) requirements, in the source perk's order.}
  Int[] out = new Int[0]
  If RequirementPerks == None
    Return out
  EndIf
  Int i = RequirementPerks.Find(akPerk)
  While i >= 0
    out.Add(i)
    i = RequirementPerks.Find(akPerk, i + 1)
  EndWhile
  Return out
EndFunction

Float Function PlayerValue(Int aiRow)
  {The player's value row aiRow tests: an actor value's base, sex (0 male, 1 female), 1 or 0 for a perk, the level.}
  Actor player = Game.GetPlayer()
  Int kind = RequirementKinds[aiRow]
  If kind == 0
    Return player.GetBaseValue(RequirementForms[aiRow] as ActorValue)
  ElseIf kind == 1
    Return player.GetLeveledActorBase().GetSex()
  ElseIf kind == 2 && player.HasPerk(RequirementForms[aiRow] as Perk)
    Return 1.0
  ElseIf kind == 3
    Return player.GetLevel()
  EndIf
  Return 0.0
EndFunction

Bool Function RequirementMet(Int aiRow)
  {Whether the player's value passes row aiRow's comparison.}
  Float have = PlayerValue(aiRow)
  Float need = RequirementValues[aiRow]
  Int compare = RequirementCompares[aiRow]
  If compare == 0
    Return have == need
  ElseIf compare == 1
    Return have != need
  ElseIf compare == 2
    Return have > need
  ElseIf compare == 3
    Return have >= need
  ElseIf compare == 4
    Return have < need
  EndIf
  Return have <= need
EndFunction

; ---------------------------------------------------------------------------
; The menu
; ---------------------------------------------------------------------------

Function Open(Int aiMode = 0, Int aiCount = 0, Int aiBonus = 0)
  {Open our menu in mode aiMode (LevelUpMode, TagsMode for aiCount tags in all with aiBonus each, TraitsMode for up to
  aiCount traits); it gets its data (Send) once open.}
  mode = aiMode
  wanted = aiCount
  bonus = aiBonus
  Register()
  UI.OpenMenu(MenuName)
EndFunction

Function Register()
  {Register the menu with F4SE (registrations do not last past a load) and its events, each once.}
  If !UI.IsMenuRegistered(MenuName)
    UI:MenuData data = new UI:MenuData
    data.menuFlags = MenuFlags
    data.extendedFlags = ExtendedFlags
    UI.RegisterCustomMenu(MenuName, MenuName, "root1", data)
  EndIf
  UnregisterForMenuOpenCloseEvent(MenuName)
  RegisterForMenuOpenCloseEvent(MenuName)
  UnregisterForExternalEvent("F3NV_LevelUpTake")
  UnregisterForExternalEvent("F3NV_LevelUpRaise")
  UnregisterForExternalEvent("F3NV_LevelUpClose")
  UnregisterForExternalEvent("F3NV_LevelUpLog")
  UnregisterForExternalEvent("F3NV_LevelUpTags")
  UnregisterForExternalEvent("F3NV_LevelUpTraits")
  RegisterForExternalEvent("F3NV_LevelUpTake", "OnMenuTake")
  RegisterForExternalEvent("F3NV_LevelUpRaise", "OnMenuRaise")
  RegisterForExternalEvent("F3NV_LevelUpClose", "OnMenuClose")
  RegisterForExternalEvent("F3NV_LevelUpLog", "OnMenuLog")
  RegisterForExternalEvent("F3NV_LevelUpTags", "OnMenuTags")
  RegisterForExternalEvent("F3NV_LevelUpTraits", "OnMenuTraits")
EndFunction

Event OnMenuOpenCloseEvent(String asMenuName, Bool abOpening)
  If asMenuName == MenuName && abOpening
    Send()
  EndIf
EndEvent

Function Send()
  {Hand the open menu its tables, the player's points, level, sex and cap, the ranks held and values (asked in
  parallel, Gather), the tagged skills, the requirement rows, the mode and the traits held (root1.Open, in
  Character.as's order).}
  Float started = Utility.GetCurrentRealTime()
  Actor player = Game.GetPlayer()
  Int specialCount = Specials.GetSize()
  Gather(specialCount, Skills.GetSize(), Traits.GetSize())
  Var[] args = new Var[32]
  args[0] = PerkPoints
  args[1] = SkillPoints
  args[2] = player.GetLevel()
  args[3] = player.GetLeveledActorBase().GetSex()
  args[4] = SkillCap
  args[5] = PerkNames
  args[6] = PerkDescriptions
  args[7] = PerkImages
  args[8] = IntsText(PerkLevels)
  args[9] = IntsText(PerkRanks)
  args[10] = JoinedParts(heldParts)
  args[11] = SkillNames
  args[12] = SkillDescriptions
  args[13] = SkillImages
  args[14] = JoinedParts(valueParts)
  args[15] = JoinedParts(tagParts)
  args[16] = specialCount
  args[17] = IntsText(RequirementOwners)
  args[18] = IntsText(RequirementKinds)
  args[19] = IntsText(RequirementTargets)
  args[20] = IntsText(RequirementCompares)
  args[21] = FloatsText(RequirementValues)
  args[22] = IntsText(RequirementOr)
  args[23] = RequirementLabels
  args[24] = UnlistedPerksHeld()
  args[25] = mode
  args[26] = wanted
  args[27] = bonus
  args[28] = TraitNames
  args[29] = TraitDescriptions
  args[30] = TraitImages
  args[31] = JoinedParts(traitParts)
  UI.Invoke(MenuName, "root1.Open", args)
  Debug.Trace("F3NV_LevelUp: sent in " + (Utility.GetCurrentRealTime() - started) + "s")
EndFunction

Function Gather(Int aiSpecials, Int aiSkills, Int aiTraits)
  {Into heldParts, valueParts, tagParts and traitParts: the ranks held of each listed perk, the player's base value of
  each Specials and Skills entry and its tag (0 none, 1 a suggestion the tag menu may change, 2 tagged), then whether
  the player has each trait; asked by Chunks stacks at once (ScanChunk), so the frame each native call costs
  overlaps. Gives up after 10 seconds.}
  Int count = PerkRanks.Length + aiSpecials + aiSkills + aiTraits
  heldParts = new String[Chunks]
  valueParts = new String[Chunks]
  tagParts = new String[Chunks]
  traitParts = new String[Chunks]
  pending = Chunks
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
  {Gather's items aiFirst to aiEnd into its parts aiChunk: a listed perk's ranks held (walking RankForms), a value and
  its tag (Specials, then Skills), or a trait held.}
  Actor player = Game.GetPlayer()
  Int listed = PerkRanks.Length
  Int traitsAt = listed + aiSpecials + aiSkills
  Int offset = 0
  Int i = 0
  While i < aiFirst && i < listed
    offset += PerkRanks[i]
    i += 1
  EndWhile
  String held = ""
  String values = ""
  String tags = ""
  String had = ""
  i = aiFirst
  While i < aiEnd
    If i < listed
      Int rank = 0
      While rank < PerkRanks[i] && player.HasPerk(RankForms[offset + rank])
        rank += 1
      EndWhile
      offset += PerkRanks[i]
      held = Joined(held, "" + rank)
    ElseIf i >= traitsAt
      had = Joined(had, "" + (player.HasPerk(Traits.GetAt(i - traitsAt) as Perk) as Int))
    Else
      ActorValue value
      If i - listed < aiSpecials
        value = Specials.GetAt(i - listed) as ActorValue
      Else
        value = Skills.GetAt(i - listed - aiSpecials) as ActorValue
      EndIf
      values = Joined(values, "" + player.GetBaseValue(value))
      tags = Joined(tags, "" + TagState(value))
    EndIf
    i += 1
  EndWhile
  heldParts[aiChunk] = held
  valueParts[aiChunk] = values
  tagParts[aiChunk] = tags
  traitParts[aiChunk] = had
  pending -= 1
EndFunction

Int Function TagState(ActorValue akValue)
  {0 untagged, 1 tagged as SetPlayerTagSkill's suggestion (the tag menu may change it), 2 tagged.}
  If !Events.IsTagged(akValue)
    Return 0
  ElseIf Events.IsSuggested(akValue)
    Return 1
  EndIf
  Return 2
EndFunction

String Function Joined(String asText, String asEntry)
  {asText with asEntry added, SEP between.}
  If asText == ""
    Return asEntry
  EndIf
  Return asText + SEP + asEntry
EndFunction

String Function JoinedParts(String[] asParts)
  {asParts' non-empty texts, SEP between.}
  String out = ""
  Int i = 0
  While i < asParts.Length
    If asParts[i] != ""
      out = Joined(out, asParts[i])
    EndIf
    i += 1
  EndWhile
  Return out
EndFunction

String Function IntsText(Int[] aiValues)
  {aiValues, SEP between.}
  String out = ""
  Int i = 0
  While aiValues && i < aiValues.Length
    out = Joined(out, "" + aiValues[i])
    i += 1
  EndWhile
  Return out
EndFunction

String Function FloatsText(Float[] afValues)
  {afValues, SEP between.}
  String out = ""
  Int i = 0
  While afValues && i < afValues.Length
    out = Joined(out, "" + afValues[i])
    i += 1
  EndWhile
  Return out
EndFunction

String Function UnlistedPerksHeld()
  {Per requirement row: for a perk test whose perk is not listed (target -1), 1 when the player has it, else 0.}
  Actor player = Game.GetPlayer()
  String out = ""
  Int i = 0
  While RequirementKinds && i < RequirementKinds.Length
    Bool has = RequirementKinds[i] == 2 && RequirementTargets[i] < 0 && player.HasPerk(RequirementForms[i] as Perk)
    out = Joined(out, "" + (has as Int))
    i += 1
  EndWhile
  Return out
EndFunction

Function OnMenuTake(Int aiIndex)
  {The menu's pick of listed perk aiIndex: take its next rank (TakePerk, the engine's eligibility test), then tell
  the menu whether it was taken, the ranks now held and the perk points left (root1.Taken).}
  Perk first = Perks.GetAt(aiIndex) as Perk
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
      Events.Tag(skill)
    Else
      Events.Untag(skill)
    EndIf
    i += 1
  EndWhile
  SendCustomEvent("TagsChosen", new Var[0])
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuTraits(Int aiMask, Int aiShown)
  {The trait menu's picks, bit i for Traits' entry i, of the first aiShown (those the menu's tables name; a DLC's
  joined by the list merge are left as they are): each the player has and isn't picked is removed, each picked one
  they don't have added; then the menu closed.}
  Actor player = Game.GetPlayer()
  Int i = 0
  While i < aiShown && i < Traits.GetSize()
    Perk trait = Traits.GetAt(i) as Perk
    Bool picked = Math.LogicalAnd(aiMask, Math.LeftShift(1, i)) != 0
    If picked && !player.HasPerk(trait)
      player.AddPerk(trait)
    ElseIf !picked && player.HasPerk(trait)
      player.RemovePerk(trait)
    EndIf
    i += 1
  EndWhile
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuClose()
  UI.CloseMenu(MenuName)
EndFunction

Function OnMenuLog(String asText)
  Debug.Trace("F3NV_LevelUp: " + asText)
EndFunction

Var[] Function FormArgs(Form akForm)
  {A custom event's arguments: akForm alone.}
  Var[] args = new Var[1]
  args[0] = akForm
  Return args
EndFunction
