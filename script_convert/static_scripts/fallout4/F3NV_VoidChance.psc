ScriptName F3NV_VoidChance extends Actor Hidden
{A placed actor whose FNV leveled base could draw a void creature (FNV's chance of nothing): it rolls that chance when its script starts and on each reset, disabled on a hit. The void stays out of the lists, since Fallout 4 draws each template part from a list on its own.}

Float Property Chance Auto Const
{The share of the base's draws that were void in FNV.}

Event OnInit()
  Roll()
EndEvent

Event OnReset()
  Roll()
EndEvent

Function Roll()
  {Disable this actor at Chance.}
  If Utility.RandomFloat() < Chance
    Disable()
  EndIf
EndFunction
