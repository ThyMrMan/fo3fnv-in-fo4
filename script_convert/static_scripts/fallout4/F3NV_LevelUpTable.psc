ScriptName F3NV_LevelUpTable extends Quest Const
{Fallout 4 only. One plugin's part of our level-up menu, as its build wrote it: its own listed perks and traits (names,
descriptions and images SEP between, levels, rank chains) and its perks' requirement rows. The game's is on the
character rules quest beside F3NV_LevelUp; a DLC's on a start-game quest of its own, which adds itself to Tables as it
starts, so plugins stack in any load order. F3NV_LevelUp joins every table each time the menu opens.
See docs/fork/fo4_level_up_plan.md#tables}

FormList Property Tables Auto Const
{The game's registry of every plugin's table (FNV_LevelUpTables).}
String Property PerkNames Auto Const
{This plugin's listed perks' names, SEP between; PerkDescriptions and PerkImages (paths under Textures) alike.}
String Property PerkDescriptions Auto Const
String Property PerkImages Auto Const
Int[] Property PerkLevels Auto Const
Int[] Property PerkRanks Auto Const
{Each listed perk's rank count; its ranks are the next that many of RankForms.}
Perk[] Property RankForms Auto Const
Perk[] Property TraitForms Auto Const
{This plugin's traits; TraitNames, TraitDescriptions and TraitImages line up, SEP between.}
String Property TraitNames Auto Const
String Property TraitDescriptions Auto Const
String Property TraitImages Auto Const
Int[] Property RequirementKinds Auto Const
{One row per requirement of this plugin's perks: 0 an actor value, 1 the player's sex, 2 another perk, 3 the level. The
other Requirement arrays line up with it.}
Form[] Property RequirementForms Auto Const
{The actor value or perk a row tests; None for sex and level.}
Int[] Property RequirementCompares Auto Const
{0 ==, 1 !=, 2 >, 3 >=, 4 <, 5 <=.}
Float[] Property RequirementValues Auto Const
Int[] Property RequirementOr Auto Const
{1 when a row ORs with the next.}
Int[] Property RequirementOwners Auto Const
{The row's perk's index among this table's listed perks; -1 for one not listed (a trait).}
Int[] Property RequirementTargets Auto Const
{Where the menu finds the tested value: an index into its values (SPECIAL then skills), or for a perk into this table's
listed perks; -1 otherwise.}
String Property RequirementLabels Auto Const
{The tested actor value's or perk's name per row, SEP between ("" for sex and level).}

Event OnQuestInit()
  Register()
EndEvent

Function Register()
  {Be in Tables.}
  If Tables && Tables.Find(Self) < 0
    Tables.AddForm(Self)
  EndIf
EndFunction

Int Function PerkCount()
  Return CountOf(PerkRanks)
EndFunction

Int Function TraitCount()
  If !TraitForms
    Return 0
  EndIf
  Return TraitForms.Length
EndFunction

Int Function RowCount()
  Return CountOf(RequirementKinds)
EndFunction

String Function Text(Int aiWhich, Int aiFirstPerk)
  {Table aiWhich as the menu reads it, SEP between: 0 to 4 the perks' names, descriptions, images, levels and rank
  counts; 5 to 7 the traits' names, descriptions and images; 8 to 14 the rows' owners, kinds, targets, comparisons,
  values, OR flags and labels; 15 UnlistedHeld. A row's owner, and a perk row's target, are moved to aiFirstPerk,
  where this table's perks start among every table's.}
  If aiWhich == 0
    Return PerkNames
  ElseIf aiWhich == 1
    Return PerkDescriptions
  ElseIf aiWhich == 2
    Return PerkImages
  ElseIf aiWhich == 3
    Return IntsText(PerkLevels)
  ElseIf aiWhich == 4
    Return IntsText(PerkRanks)
  ElseIf aiWhich == 5
    Return TraitNames
  ElseIf aiWhich == 6
    Return TraitDescriptions
  ElseIf aiWhich == 7
    Return TraitImages
  ElseIf aiWhich == 8
    Return Moved(RequirementOwners, aiFirstPerk, -1)
  ElseIf aiWhich == 9
    Return IntsText(RequirementKinds)
  ElseIf aiWhich == 10
    Return Moved(RequirementTargets, aiFirstPerk, 2)
  ElseIf aiWhich == 11
    Return IntsText(RequirementCompares)
  ElseIf aiWhich == 12
    Return FloatsText(RequirementValues)
  ElseIf aiWhich == 13
    Return IntsText(RequirementOr)
  ElseIf aiWhich == 14
    Return RequirementLabels
  EndIf
  Return UnlistedHeld(Game.GetPlayer())
EndFunction

String Function Moved(Int[] aiIndexes, Int aiBy, Int aiKind)
  {aiIndexes, SEP between, each one 0 or more moved up by aiBy: every one when aiKind is -1, else a row of that kind.}
  String out = ""
  Int i = 0
  While aiIndexes && i < aiIndexes.Length
    Int at = aiIndexes[i]
    If at >= 0 && (aiKind < 0 || RequirementKinds[i] == aiKind)
      at += aiBy
    EndIf
    out = Joined(out, "" + at, i)
    i += 1
  EndWhile
  Return out
EndFunction

String Function RanksHeld(Actor akPlayer, Int aiFrom, Int aiTo)
  {The ranks akPlayer holds of this table's listed perks aiFrom to aiTo (walking RankForms), SEP between.}
  Int offset = 0
  Int i = 0
  While i < aiFrom
    offset += PerkRanks[i]
    i += 1
  EndWhile
  String out = ""
  While i < aiTo
    Int rank = 0
    While rank < PerkRanks[i] && akPlayer.HasPerk(RankForms[offset + rank])
      rank += 1
    EndWhile
    offset += PerkRanks[i]
    out = Joined(out, "" + rank, i - aiFrom)
    i += 1
  EndWhile
  Return out
EndFunction

String Function TraitsHeld(Actor akPlayer, Int aiFrom, Int aiTo)
  {1 or 0 for whether akPlayer has each of this table's traits aiFrom to aiTo, SEP between.}
  String out = ""
  Int i = aiFrom
  While i < aiTo
    out = Joined(out, "" + (akPlayer.HasPerk(TraitForms[i]) as Int), i - aiFrom)
    i += 1
  EndWhile
  Return out
EndFunction

String Function UnlistedHeld(Actor akPlayer)
  {Per requirement row: for a perk test whose perk this table does not list (target -1), 1 when akPlayer has it, else
  0; SEP between.}
  String out = ""
  Int i = 0
  While i < RowCount()
    Bool has = RequirementKinds[i] == 2 && RequirementTargets[i] < 0 && akPlayer.HasPerk(RequirementForms[i] as Perk)
    out = Joined(out, "" + (has as Int), i)
    i += 1
  EndWhile
  Return out
EndFunction

Bool Function Lists(Perk akPerk)
  {Whether akPerk is a rank of one of this table's listed perks.}
  Return RankForms && RankForms.Find(akPerk) >= 0
EndFunction

Perk Function FirstRank(Int aiPerk)
  {The first rank of this table's listed perk aiPerk.}
  Int offset = 0
  Int i = 0
  While i < aiPerk
    offset += PerkRanks[i]
    i += 1
  EndWhile
  Return RankForms[offset]
EndFunction

Function SetTraits(Actor akPlayer, Int aiMask, Int aiFirst, Int aiShown)
  {The trait menu's picks for this table's traits, bit aiFirst + i for trait i, of the first aiShown of every table's:
  each akPlayer has and isn't picked removed, each picked one they lack added. A trait past the mask is left.}
  Int i = 0
  While i < TraitCount() && aiFirst + i < aiShown && aiFirst + i < 31
    Perk trait = TraitForms[i]
    Bool picked = Math.LogicalAnd(aiMask, Math.LeftShift(1, aiFirst + i)) != 0
    If picked && !akPlayer.HasPerk(trait)
      akPlayer.AddPerk(trait)
    ElseIf !picked && akPlayer.HasPerk(trait)
      akPlayer.RemovePerk(trait)
    EndIf
    i += 1
  EndWhile
EndFunction

; ---------------------------------------------------------------------------
; Text helpers (SEP is a tab, as fo4_import/spike/level_up.py's)
; ---------------------------------------------------------------------------

Int Function CountOf(Int[] aiValues) Global
  If !aiValues
    Return 0
  EndIf
  Return aiValues.Length
EndFunction

String Function Joined(String asText, String asEntry, Int aiIndex) Global
  {asText with asEntry added, a tab before it unless it is entry 0.}
  If aiIndex == 0
    Return asEntry
  EndIf
  Return asText + "\t" + asEntry
EndFunction

String Function IntsText(Int[] aiValues) Global
  {aiValues, a tab between.}
  String out = ""
  Int i = 0
  While aiValues && i < aiValues.Length
    out = Joined(out, "" + aiValues[i], i)
    i += 1
  EndWhile
  Return out
EndFunction

String Function FloatsText(Float[] afValues) Global
  {afValues, a tab between.}
  String out = ""
  Int i = 0
  While afValues && i < afValues.Length
    out = Joined(out, "" + afValues[i], i)
    i += 1
  EndWhile
  Return out
EndFunction
