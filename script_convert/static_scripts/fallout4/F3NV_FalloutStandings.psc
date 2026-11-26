ScriptName F3NV_FalloutStandings extends Quest Hidden
{FO3/FNV karma and infamy from the player's kills and crimes on Fallout 4, as the game's engine scores them (character_rules' FalloutRules_Main, read from FalloutNV.exe): a kill's karma by the victim's alignment when a crime-tracking faction claims it; a theft's, unless its owner is evil; a reported murder's major infamy and a kill in a fight's minor one, with each reputation a victim's crime faction answers to; a reported theft or pickpocketing's minor infamy. It also keeps FO3/FNV's crime counts: a reported murder or a criminal assault is a major crime, a reported theft, pickpocketing or trespass a minor one, each counted against every crime-tracking faction of the victim (or the faction it was against); an NPC's MajorCrimes and MinorCrimes helper actor values hold the sums over its factions, as GetMajorCrimeCount and GetMinorCrimeCount read them, set for the NPCs near the player after each crime and each change of location. It keeps FO3's dispositions toward the player too, in each NPC's Disposition helper actor value, as GetDisposition reads it (ModDisposition). The Story Manager's kill, assault and crime-gold quests (F3NV_FalloutKillEvent, F3NV_FalloutAssaultEvent, F3NV_FalloutCrimeEvent) and the player alias (F3NV_FalloutStandingsPlayer) report here. See docs/fork/fo4_pipeline.md#standings}

GlobalVariable Property Karma Auto Const
{The converted game's karma (TES4Karma).}
FormList Property VeryEvilActors Auto Const
{Actor bases by the alignment their karma gives.}
FormList Property EvilActors Auto Const
FormList Property GoodActors Auto Const
FormList Property VeryGoodActors Auto Const
FormList Property CrimeFactions Auto Const
{Factions that track crime.}
FormList Property MajorCounts Auto Const
{Each crime-tracking faction's count of the player's major crimes against it (a global, in CrimeFactions' order).}
FormList Property MinorCounts Auto Const
{And of minor crimes.}
FormList Property EvilFactions Auto Const
{Stealing from these costs no karma.}
FormList[] Property Reputations Auto Const
{Each New Vegas reputation.}
FormList[] Property ReputationFactions Auto Const
{And the crime-tracking factions that answer to it.}
Keyword Property ActorTypeNPC Auto Const
{A person's murder reads the NPC amount, anything else the creature one.}
Float[] Property KillKarmaClaimed Auto Const
{A kill's karma by alignment (neutral, evil, very evil, good, very good) when a crime-tracking faction claims the victim.}
Float[] Property KillKarmaUnclaimed Auto Const
{And when none does.}
Int[] Property KillMurders Auto Const
{1: that alignment's kill is murder, the person or creature amount.}
Float Property KarmaMurderNPC Auto Const
Float Property KarmaMurderCreature Auto Const
Float Property KarmaTheft Auto Const
Float Property KarmaMin Auto Const
Float Property KarmaMax Auto Const
Float Property InfamyMajor Auto Const
{A reported murder.}
Float Property InfamyMinor Auto Const
{A reported theft or pickpocketing, or a kill in a fight.}
Float Property DispositionBase Auto Const
{The game's fDispActorCharBase: an NPC's disposition toward the player before Charisma.}
Float Property DispositionActorMult Auto Const
{fDispActorCharMult: per point of the NPC's Charisma.}
Float Property DispositionPlayerMult Auto Const
{fDispTargetCharMult: per point of the player's Charisma.}

Int Property NEUTRAL = 0 AutoReadOnly
Int Property EVIL = 1 AutoReadOnly
Int Property VERY_EVIL = 2 AutoReadOnly
Int Property GOOD = 3 AutoReadOnly
Int Property VERY_GOOD = 4 AutoReadOnly
Int Property CRIME_REPORTED = 2 AutoReadOnly
Int Property CRIME_STEAL = 0 AutoReadOnly
Int Property CRIME_PICKPOCKET = 1 AutoReadOnly
Int Property CRIME_TRESPASS = 2 AutoReadOnly
Int Property INFAMY = 0 AutoReadOnly
Float Property NEAR = 8192.0 AutoReadOnly
{How far from the player NPCs get their crime counts set: the loaded area.}

Int stolen = -1

Function NoteKill(Actor victim, Actor killer, Int crimeStatus)
  {A kill the Story Manager reported: the player's scores karma and infamy.}
  If !victim || killer != Game.GetPlayer()
    Return
  EndIf
  Int align = Alignment(victim)
  Float change = KillKarmaUnclaimed[align]
  If InAny(victim, CrimeFactions)
    change = KillKarmaClaimed[align]
    If KillMurders[align] == 1 && victim.HasKeyword(ActorTypeNPC)
      change = KarmaMurderNPC
    ElseIf KillMurders[align] == 1
      change = KarmaMurderCreature
    EndIf
  EndIf
  ModKarma(change)
  If crimeStatus == CRIME_REPORTED
    AddInfamy(victim, InfamyMajor)
    CountCrime(victim, None, MajorCounts)
  ElseIf Game.GetPlayer().IsInCombat()
    AddInfamy(victim, InfamyMinor)
  EndIf
EndFunction

Int Function Alignment(Actor victim)
  {The victim's alignment, by its base or, for a leveled actor, the base it was made from.}
  Form base = victim.GetLeveledActorBase()
  Form own = victim.GetActorBase()
  If EvilActors.HasForm(base) || EvilActors.HasForm(own)
    Return EVIL
  ElseIf VeryEvilActors.HasForm(base) || VeryEvilActors.HasForm(own)
    Return VERY_EVIL
  ElseIf GoodActors.HasForm(base) || GoodActors.HasForm(own)
    Return GOOD
  ElseIf VeryGoodActors.HasForm(base) || VeryGoodActors.HasForm(own)
    Return VERY_GOOD
  EndIf
  Return NEUTRAL
EndFunction

Function NoteCrime(Actor victim, Actor criminal, Form against, Int crime)
  {A reported crime the Story Manager heard of: a theft or pickpocketing costs the minor infamy; it, or a trespass, is a minor crime against the victim's factions or the faction.}
  If criminal != Game.GetPlayer()
    Return
  EndIf
  If victim && (crime == CRIME_STEAL || crime == CRIME_PICKPOCKET)
    AddInfamy(victim, InfamyMinor)
  EndIf
  If crime == CRIME_STEAL || crime == CRIME_PICKPOCKET || crime == CRIME_TRESPASS
    CountCrime(victim, against, MinorCounts)
  EndIf
EndFunction

Function NoteAssault(Actor victim, Actor attacker, Int crime)
  {An assault the Story Manager heard of: the player's, when a crime, is a major crime against the victim's factions.}
  If victim && attacker == Game.GetPlayer() && crime != 0
    CountCrime(victim, None, MajorCounts)
  EndIf
EndFunction

Function CountCrime(Actor victim, Form against, FormList counts)
  {One more crime in counts against each crime-tracking faction of the victim (with none, against the faction `against`), then the nearby NPCs' sums.}
  Int i = CrimeFactions.GetSize()
  While i > 0
    i -= 1
    Form tracked = CrimeFactions.GetAt(i)
    If victim && victim.IsInFaction(tracked as Faction) || !victim && tracked == against
      (counts.GetAt(i) as GlobalVariable).Mod(1.0)
    EndIf
  EndWhile
  Refresh()
EndFunction

Function Refresh()
  {Set the NPCs near the player's Disposition (ModDisposition by nothing) and, while any crime is counted, their MajorCrimes and MinorCrimes to the sums of their crime-tracking factions' counts.}
  Int[] hot = new Int[0]
  Int i = CrimeFactions.GetSize()
  While i > 0
    i -= 1
    If (MajorCounts.GetAt(i) as GlobalVariable).GetValue() > 0.0 || (MinorCounts.GetAt(i) as GlobalVariable).GetValue() > 0.0
      hot.Add(i)
    EndIf
  EndWhile
  ObjectReference[] nearby = Game.GetPlayer().FindAllReferencesWithKeyword(ActorTypeNPC, NEAR)
  Int n = nearby.Length
  While n > 0
    n -= 1
    Actor someone = nearby[n] as Actor
    If someone
      ModDisposition(someone, 0.0)
      If hot.Length > 0
        CountFor(someone, hot)
      EndIf
    EndIf
  EndWhile
EndFunction

Function CountFor(Actor someone, Int[] hot)
  {Set someone's MajorCrimes and MinorCrimes to the sums of the counts of its factions among hot (CrimeFactions indexes).}
  Float majors = 0.0
  Float minors = 0.0
  Int h = hot.Length
  While h > 0
    h -= 1
    If someone.IsInFaction(CrimeFactions.GetAt(hot[h]) as Faction)
      majors += (MajorCounts.GetAt(hot[h]) as GlobalVariable).GetValue()
      minors += (MinorCounts.GetAt(hot[h]) as GlobalVariable).GetValue()
    EndIf
  EndWhile
  someone.SetValue(TES4Polyfill.AV("majorcrimes"), majors)
  someone.SetValue(TES4Polyfill.AV("minorcrimes"), minors)
EndFunction

Function ModDisposition(Actor someone, Float by)
  {FO3's ModDisposition toward the player: someone's kept adjustment (DispositionMod) moves by `by`, no further than keeps its disposition within 0 to 100; its Disposition is then its base (the game's settings times its and the player's Charisma) plus the adjustment, within 0 to 100. See docs/fork/fo4_pipeline.md#disposition}
  If !someone || someone == Game.GetPlayer()
    Return
  EndIf
  ActorValue charisma = Game.GetCharismaAV()
  Float base = DispositionBase + DispositionActorMult * someone.GetValue(charisma) + DispositionPlayerMult * Game.GetPlayer().GetValue(charisma)
  ActorValue kept = TES4Polyfill.AV("dispositionmod")
  Float adjusted = someone.GetValue(kept)
  If by != 0.0
    adjusted = Within(adjusted + by, -base, 100.0 - base)
    someone.SetValue(kept, adjusted)
  EndIf
  someone.SetValue(TES4Polyfill.AV("disposition"), Within(base + adjusted, 0.0, 100.0))
EndFunction

Float Function Within(Float value, Float low, Float high) global
  {value, no lower than low nor higher than high (low wins when they cross).}
  If value > high
    value = high
  EndIf
  If value < low
    value = low
  EndIf
  Return value
EndFunction

Function NoteItem(ObjectReference source, ObjectReference item)
  {An item the player took: a theft, seen or not, when the game's Items Stolen rose; it costs karma unless its owner is evil.}
  Int now = Game.QueryStat("Items Stolen")
  Int before = stolen
  stolen = now
  If before < 0 || now <= before
    Return
  EndIf
  Form owner = OwnerOf(source, item)
  If EvilFactions.HasForm(owner) || EvilActors.HasForm(owner) || VeryEvilActors.HasForm(owner)
    Return
  EndIf
  ModKarma(KarmaTheft)
EndFunction

Function Loaded()
  {A game was loaded: the stolen count restarts from the game's own.}
  stolen = Game.QueryStat("Items Stolen")
EndFunction

Form Function OwnerOf(ObjectReference source, ObjectReference item)
  {The item's owner: its container's, else its own, else the cell's.}
  ObjectReference held = source
  If !held
    held = item
  EndIf
  If held && held.GetActorOwner()
    Return held.GetActorOwner()
  ElseIf held && held.GetFactionOwner()
    Return held.GetFactionOwner()
  EndIf
  Cell here = Game.GetPlayer().GetParentCell()
  If here && here.GetActorOwner()
    Return here.GetActorOwner()
  ElseIf here
    Return here.GetFactionOwner()
  EndIf
  Return None
EndFunction

Function ModKarma(Float change)
  {Karma moved by change, kept between KarmaMin and KarmaMax (traced as TES4Polyfill.SetKarma traces).}
  If change == 0.0 || !Karma
    Return
  EndIf
  Float value = Karma.GetValue() + change
  If value > KarmaMax
    value = KarmaMax
  ElseIf value < KarmaMin
    value = KarmaMin
  EndIf
  TES4Polyfill.SetKarma(Karma, value)
EndFunction

Bool Function InAny(Actor someone, FormList factions)
  {Whether someone is in any faction of factions.}
  Int i = factions.GetSize()
  While i > 0
    i -= 1
    If someone.IsInFaction(factions.GetAt(i) as Faction)
      Return True
    EndIf
  EndWhile
  Return False
EndFunction

Function AddInfamy(Actor victim, Float amount)
  {Infamy with each reputation one of the victim's crime-tracking factions answers to.}
  If amount <= 0.0 || !Reputations
    Return
  EndIf
  Int i = 0
  While i < Reputations.Length
    Int f = ReputationFactions[i].GetSize()
    While f > 0
      f -= 1
      If victim.IsInFaction(ReputationFactions[i].GetAt(f) as Faction)
        TES4_Reputation.AddExact(Reputations[i], INFAMY, amount)
      EndIf
    EndWhile
    i += 1
  EndWhile
EndFunction
