ScriptName TES4_FalloutLock extends ObjectReference Hidden
{An FNV lock or terminal FO4's lock tiers cannot hold: FO4's Novice tier opens FNV's Easy (25) at any skill, and a password note is no FO4 key. While locked, activation is held here: the player's password note unlocks it, and below the FNV skill its lock level names (0 to 100) the player is refused. Anything else goes on to the game's own lockpicking or hacking.
See: docs/fork/fo4_pipeline.md#lock-script}

ActorValue Property Skill Auto Const
Bool Property IsTerminal Auto Const
Form Property Password Auto Const

Event OnLoad()
  BlockActivation(IsLocked())
EndEvent

Event OnLockStateChanged()
  BlockActivation(IsLocked())
EndEvent

Event OnActivate(ObjectReference akActionRef)
  If !IsActivationBlocked()
    Return
  EndIf
  Actor player = Game.GetPlayer()
  If akActionRef == player && IsLocked()
    int level = GetLockLevel()
    If Password && player.GetItemCount(Password) > 0
      Unlock()
    ElseIf level <= 100 && player.GetValue(Skill) < level
      If IsTerminal
        Debug.Notification("Requires Science " + level)
      Else
        Debug.Notification("Requires Lockpick " + level)
      EndIf
      Return
    EndIf
  EndIf
  Activate(akActionRef, true)
EndEvent
