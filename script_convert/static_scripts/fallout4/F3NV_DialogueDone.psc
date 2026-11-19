ScriptName F3NV_DialogueDone extends Package Hidden
{Fragment of an FNV Dialogue package's parked copy, which holds its actor once it has talked in the package's force greet, as FNV leaves a talked Dialogue package current on its done step. When another package takes over (OnChange), the actor's DialogueDone mark for this package clears, so the force greet runs again next time, as FNV restarts a package another one replaced; for a walk-up (WalkUp) its scene's own package does not count. See docs/fork/fo4_pipeline.md#greet-once}

Int Property Done Auto Const
{The number of the force greet this copy parks (GreetOnce), which DialogueDone holds while the actor is parked.}
Bool Property WalkUp = False Auto Const
{True when this copy parks a SayTo package's walk-up (TES4Polyfill.WalkUp): its scene's own package is not another package taking over.}

; Fragment_0: OnChange.
Function Fragment_0(Actor akActor)
  ActorValue mark = TES4Polyfill.AV("dialoguedone")
  If akActor && mark && akActor.GetValue(mark) == Done && !(WalkUp && akActor.GetCurrentScene())
    akActor.SetValue(mark, 0.0)
    If TES4Polyfill.Tracing()
      TES4Polyfill.TraceWrite("dialoguedone", TES4Polyfill.TraceName(akActor) + "|" + Done + "|cleared")
    EndIf
  EndIf
EndFunction
