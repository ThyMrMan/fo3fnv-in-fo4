ScriptName TES4_DebugMark extends ReferenceAlias Hidden
{Play-test marker: a key press writes what is around the player to the
Papyrus log as TES4MARK lines, which the bridge's flight recorder keeps as
`mark` events: the player's place and the game time, what the crosshair is
on, and each actor nearby with its current package. The session report
explains every mark against the source game's data. TES4MarkKey holds the
DirectInput scan code (65 = F7); after `set TES4MarkKey to <code>` in the
console, the new key takes effect on the next load.
See: docs/commentary/tools_live_session_report.md#mark-key}

GlobalVariable Property TES4MarkKey Auto

Int TES4Key
Int TES4Count

Event OnInit()
  TES4Listen()
EndEvent

Event OnPlayerLoadGame()
  TES4Listen()
EndEvent

Function TES4Listen()
  UnregisterForAllKeys()
  TES4Key = TES4MarkKey.GetValueInt()
  RegisterForKey(TES4Key)
EndFunction

Event OnKeyDown(Int keyCode)
  If keyCode == TES4Key && !UI.IsMenuOpen("Console")
    TES4Mark()
  EndIf
EndEvent

; A form's id as text, 0 for None (Papyrus prints ids at or above 0x80000000 as negatives).
String Function TES4Id(Form akForm)
  If akForm
    Return akForm.GetFormID() as String
  EndIf
  Return "0"
EndFunction

String Function TES4Pos(ObjectReference akRef)
  Return akRef.GetPositionX() + "," + akRef.GetPositionY() + "," + akRef.GetPositionZ()
EndFunction

Function TES4Mark()
  TES4Count += 1
  Int n = TES4Count
  String tag = "TES4MARK " + n + " "
  Actor player = Game.GetPlayer()
  Debug.Notification("Mark " + n)
  Debug.Trace(tag + "player pos=" + TES4Pos(player) + " angle=" + player.GetAngleZ() + " cell=" + TES4Id(player.GetParentCell()) + " world=" + TES4Id(player.GetWorldSpace()) + " days=" + Utility.GetCurrentGameTime() + " dialogue=" + (UI.IsMenuOpen("Dialogue Menu") as Int))
  ObjectReference aim = Game.GetCurrentCrosshairRef()
  If aim
    Debug.Trace(tag + "aim ref=" + TES4Id(aim) + " base=" + TES4Id(aim.GetBaseObject()) + " pos=" + TES4Pos(aim) + " disabled=" + (aim.IsDisabled() as Int) + " dist=" + aim.GetDistance(player))
  EndIf
  Actor[] seen = new Actor[64]
  Int count = 0
  Cell here = player.GetParentCell()
  If here
    Int total = here.GetNumRefs(62)
    Int i = 0
    While i < total && count < 64
      Actor someone = here.GetNthRef(i, 62) as Actor
      If someone && someone != player
        seen[count] = someone
        count += 1
      EndIf
      i += 1
    EndWhile
  EndIf
  ; An exterior's neighbours are outside the cell walk; random picks within reach cover them.
  Int tries = 0
  While tries < 40 && count < 64
    Actor someone = Game.FindRandomActorFromRef(player, 4096.0)
    If someone && someone != player && seen.Find(someone) < 0
      seen[count] = someone
      count += 1
    EndIf
    tries += 1
  EndWhile
  Int j = 0
  While j < count
    Actor a = seen[j]
    Debug.Trace(tag + "actor ref=" + TES4Id(a) + " base=" + TES4Id(a.GetActorBase()) + " pos=" + TES4Pos(a) + " cell=" + TES4Id(a.GetParentCell()) + " dist=" + a.GetDistance(player) + " package=" + TES4Id(a.GetCurrentPackage()) + " ai=" + (a.IsAIEnabled() as Int) + " dead=" + (a.IsDead() as Int) + " disabled=" + (a.IsDisabled() as Int) + " combat=" + (a.IsInCombat() as Int) + " sit=" + a.GetSitState() + " talking=" + (a.IsInDialogueWithPlayer() as Int))
    j += 1
  EndWhile
  Debug.Trace(tag + "end actors=" + count)
EndFunction
