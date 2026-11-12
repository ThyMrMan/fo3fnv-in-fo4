ScriptName F3NV_LevelUp extends Quest
{Fallout 4 only. FO3/FNV's level-up state for our own level-up menu, in place of LevelUpMenuEx's PRKF.dll: the perk
and skill points to spend and the tagged skills (saved with the game as this script's variables), taking a perk and
raising a skill, the perk list, and each perk's rank, eligibility and requirement rows. On the character rules quest;
not used yet, as the rules keep LevelUpMenuEx until our menu replaces it. See docs/fork/fo4_level_up_plan.md#prkf}

CustomEvent PerkTaken
CustomEvent SkillTagged
CustomEvent SkillUntagged

FormList Property Perks Auto Const
{The level-up list's perks, first ranks only (FNV_Perks).}
Int Property SkillCap = 100 Auto Const
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

Int PerkPoints
Int SkillPoints
ActorValue[] Tagged

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
  Return Tagged != None && Tagged.Find(akSkill) >= 0
EndFunction

Bool Function Tag(ActorValue akSkill)
  {Tags akSkill and sends SkillTagged; False when it already was. The tag bonus is the caller's to give.}
  If !akSkill || IsTagged(akSkill)
    Return False
  EndIf
  If Tagged == None
    Tagged = new ActorValue[0]
  EndIf
  Tagged.Add(akSkill)
  SendCustomEvent("SkillTagged", FormArgs(akSkill))
  Return True
EndFunction

Bool Function Untag(ActorValue akSkill)
  {Untags akSkill and sends SkillUntagged; False when it was not tagged.}
  If !IsTagged(akSkill)
    Return False
  EndIf
  Tagged.Remove(Tagged.Find(akSkill))
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

Var[] Function FormArgs(Form akForm)
  {A custom event's arguments: akForm alone.}
  Var[] args = new Var[1]
  args[0] = akForm
  Return args
EndFunction
