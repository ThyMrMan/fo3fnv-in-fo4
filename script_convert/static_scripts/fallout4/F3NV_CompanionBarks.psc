ScriptName F3NV_CompanionBarks extends Quest
{FNV's companion status barks, on a start-game quest: each of the player's followers says HealthHalf or HealthQuarter as its health falls below half or a quarter in combat, Wake as it gets up from bleeding out, NoAmmo once a fight when its gun has no rounds left. The topics' lines pick the companion by their own conditions. Checked every Interval seconds. See docs/fork/fo4_pipeline.md#companion-barks}

Topic Property HealthHalf Auto Const
Topic Property HealthQuarter Auto Const
Topic Property Wake Auto Const
Topic Property NoAmmo Auto Const
Float Property Interval = 1.0 Auto Const
{Seconds between checks.}

Actor[] Tracked
Int[] Band
Bool[] Down
Bool[] Dry

Event OnQuestInit()
  StartTimer(Interval)
EndEvent

Event OnTimer(Int aiTimerID)
  Actor[] followers = Game.GetPlayerFollowers()
  Int i = 0
  While followers && i < followers.Length
    Check(followers[i])
    i += 1
  EndWhile
  StartTimer(Interval)
EndEvent

Function Check(Actor follower)
  {Say follower's status bark when its state has just crossed into one.}
  Int t = Slot(follower)
  Bool bleeding = follower.IsBleedingOut()
  If Down[t] && !bleeding
    Bark(follower, Wake)
  EndIf
  Down[t] = bleeding
  Bool fighting = follower.IsInCombat()
  Int now = HealthBand(follower)
  If now > Band[t] && fighting
    If now == 2
      Bark(follower, HealthQuarter)
    Else
      Bark(follower, HealthHalf)
    EndIf
  EndIf
  Band[t] = now
  Bool empty = fighting && OutOfAmmo(follower)
  If empty && !Dry[t]
    Bark(follower, NoAmmo)
  EndIf
  Dry[t] = empty
EndFunction

Int Function Slot(Actor follower)
  {follower's index in the state arrays, added on first sight.}
  If !Tracked
    Tracked = new Actor[0]
    Band = new Int[0]
    Down = new Bool[0]
    Dry = new Bool[0]
  EndIf
  Int t = Tracked.Find(follower)
  If t < 0
    Tracked.Add(follower)
    Band.Add(0)
    Down.Add(False)
    Dry.Add(False)
    t = Tracked.Length - 1
  EndIf
  Return t
EndFunction

Int Function HealthBand(Actor follower)
  {2 below a quarter of full health, 1 below half, else 0.}
  Float health = follower.GetValuePercentage(Game.GetHealthAV())
  If health < 0.25
    Return 2
  ElseIf health < 0.5
    Return 1
  EndIf
  Return 0
EndFunction

Bool Function OutOfAmmo(Actor follower)
  {Whether follower's equipped gun takes rounds it carries none of.}
  Weapon gun = follower.GetEquippedWeapon()
  Ammo rounds = None
  If gun
    rounds = gun.GetAmmo()
  EndIf
  Return rounds && follower.GetItemCount(rounds) == 0
EndFunction

Function Bark(Actor follower, Topic said)
  {follower says topic said, when the build has it.}
  If said
    follower.Say(said)
  EndIf
EndFunction
