ScriptName F3NV_RegionWatch extends Quest
{One plugin's FO3/FNV region tests, on a start-game quest of that plugin: Globals[r] is 1 while the player stands in worldspace Worlds[r] inside one of region r's polygons, else 0; conditions and converted scripts read the globals. Region r's polygons are PolyFirst[RegionFirst[r]] to PolyFirst[RegionFirst[r + 1] - 1]; polygon p's points are p's first point to PolyFirst[p + 1] - 1, in X0..X3 and Y0..Y3 (128 points each). MinX..MaxY bound each region. Tested every Interval seconds and on each location change. See docs/fork/fo4_regions.md#built}

GlobalVariable[] Property Globals Auto Const
WorldSpace[] Property Worlds Auto Const
Int[] Property RegionFirst Auto Const
Int[] Property PolyFirst Auto Const
Float[] Property MinX Auto Const
Float[] Property MaxX Auto Const
Float[] Property MinY Auto Const
Float[] Property MaxY Auto Const
Float[] Property X0 Auto Const
Float[] Property X1 Auto Const
Float[] Property X2 Auto Const
Float[] Property X3 Auto Const
Float[] Property Y0 Auto Const
Float[] Property Y1 Auto Const
Float[] Property Y2 Auto Const
Float[] Property Y3 Auto Const
Float Property Interval = 2.0 Auto Const
{Seconds between tests while nothing else asks for one.}

Event OnQuestInit()
  RegisterForRemoteEvent(Game.GetPlayer(), "OnLocationChange")
  StartTimer(0.1)
EndEvent

Event Actor.OnLocationChange(Actor akSender, Location akOldLoc, Location akNewLoc)
  Check()
EndEvent

Event OnTimer(Int aiTimerID)
  Check()
  StartTimer(Interval)
EndEvent

Function Check()
  {Set each region's global from where the player stands now.}
  Actor player = Game.GetPlayer()
  WorldSpace world = player.GetWorldSpace()
  Float x = player.GetPositionX()
  Float y = player.GetPositionY()
  Int r = 0
  While r < Globals.Length
    Float inside = 0.0
    If world && world == Worlds[r] && x >= MinX[r] && x <= MaxX[r] && y >= MinY[r] && y <= MaxY[r] && InRegion(r, x, y)
      inside = 1.0
    EndIf
    If Globals[r].GetValue() != inside
      Globals[r].SetValue(inside)
    EndIf
    r += 1
  EndWhile
EndFunction

Bool Function InRegion(Int r, Float x, Float y)
  {Whether (x, y) lies inside one of region r's polygons.}
  Int p = RegionFirst[r]
  While p < RegionFirst[r + 1]
    If InPolygon(PolyFirst[p], PolyFirst[p + 1], x, y)
      Return True
    EndIf
    p += 1
  EndWhile
  Return False
EndFunction

Bool Function InPolygon(Int first, Int last, Float x, Float y)
  {Whether (x, y) lies inside the polygon of points first to last - 1 (crossings of a ray toward +x, odd: inside).}
  Bool inside = False
  Int j = last - 1
  Int i = first
  While i < last
    Float yi = PY(i)
    Float yj = PY(j)
    If (yi > y) != (yj > y)
      Float xi = PX(i)
      If x < (PX(j) - xi) * (y - yi) / (yj - yi) + xi
        inside = !inside
      EndIf
    EndIf
    j = i
    i += 1
  EndWhile
  Return inside
EndFunction

Float Function PX(Int i)
  {Point i's x.}
  If i < 128
    Return X0[i]
  ElseIf i < 256
    Return X1[i - 128]
  ElseIf i < 384
    Return X2[i - 256]
  EndIf
  Return X3[i - 384]
EndFunction

Float Function PY(Int i)
  {Point i's y.}
  If i < 128
    Return Y0[i]
  ElseIf i < 256
    Return Y1[i - 128]
  ElseIf i < 384
    Return Y2[i - 256]
  EndIf
  Return Y3[i - 384]
EndFunction
