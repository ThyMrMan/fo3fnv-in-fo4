ScriptName F3NV_ImposterGate extends ActiveMagicEffect Hidden
{FNV's region imposters on Fallout 4: FNV shows a region imposter only while the player stands in a region whose imposter list names it. Each group of such references gets a player ability of two effects, active while the player is in one of its regions (Show) or in none (not Show); each enables or disables the group as it starts.}

ObjectReference[] Property Cards Auto Const
{The imposter references the effect shows or hides.}
Bool Property Show Auto Const
{True: enable them; false: disable them.}

Event OnEffectStart(Actor akTarget, Actor akCaster)
  int i = 0
  while i < Cards.Length
    if Show
      Cards[i].Enable()
    else
      Cards[i].Disable()
    endif
    i += 1
  endwhile
EndEvent
