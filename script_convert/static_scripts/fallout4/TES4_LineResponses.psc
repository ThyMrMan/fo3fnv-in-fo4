ScriptName TES4_LineResponses extends Quest
{Fallout 4 only. Each playing line's response count and the real time its last response began, for converted
lines with several responses (script_convert/info_responses_fallout4.py). Fallout 4 runs a line's Begin fragment
once per response in a scene's Dialogue action, once per line as a menu answer, and a topic info fragment's own
variables do not last from one call to the next, so the count lives here.}

Float Property Gap = 30.0 Auto
{Seconds between two responses' Begin past which the line is playing again.}
Float Property EndWait = 2.0 Auto
{Seconds an End fragment waits for another response's Begin before taking the line as over.}

Form[] Lines
Int[] Counts
Float[] Times

Int Function Began(Form akLine, Int aiResponses)
  {A response of akLine (aiResponses of them) began: its number in this play, 1 for the first.}
  Float now = Utility.GetCurrentRealTime()
  Int i = Slot(akLine, now)
  If Counts[i] >= aiResponses || Stale(i, now)
    Counts[i] = 0
  EndIf
  Counts[i] = Counts[i] + 1
  Times[i] = now
  Return Counts[i]
EndFunction

Bool Function Over(Form akLine, Int aiResponses)
  {akLine's End ran: true once its last response has begun, or when no other response begins within EndWait.}
  Int i = -1
  If Lines
    i = Lines.Find(akLine)
  EndIf
  If i < 0 || Counts[i] >= aiResponses
    Return True
  EndIf
  Float began = Times[i]
  Utility.Wait(EndWait)
  Return Times[i] == began
EndFunction

Bool Function Stale(Int i, Float afNow)
  {Slot i's line last began over Gap ago, or in an earlier session (real time restarts with the game).}
  Return afNow - Times[i] > Gap || afNow < Times[i]
EndFunction

Int Function Slot(Form akLine, Float afNow)
  {akLine's slot: its own, else a stale one reused, else a new one.}
  If !Lines
    Lines = new Form[0]
    Counts = new Int[0]
    Times = new Float[0]
  EndIf
  Int i = Lines.Find(akLine)
  If i >= 0
    Return i
  EndIf
  i = 0
  While i < Lines.Length && !Stale(i, afNow)
    i += 1
  EndWhile
  If i == Lines.Length
    Lines.Add(akLine)
    Counts.Add(0)
    Times.Add(0.0)
  Else
    Lines[i] = akLine
    Counts[i] = 0
  EndIf
  Return i
EndFunction
