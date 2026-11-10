ScriptName F3NV_RobotFrenzy extends ActiveMagicEffect Hidden
{FNV's robot frenzy on a converted robot (keyword F3NV_FalloutCreature): with its combat inhibitor (BrainCondition) crippled it attacks anyone near, as FNV robots do; Fallout 4's own robot script, whose self-destruct FNV lacks, is off for it. Frenzy at FO4's own robot rate. See docs/fork/fo4_creature_audit.md#race-abilities}

ActorValue Property BrainCondition Auto Const
EffectShader Property FrenzyShader Auto Const
VisualEffect Property FrenzyLight Auto Const

Event OnCripple(ActorValue akActorValue, Bool abCrippled)
  If abCrippled && akActorValue == BrainCondition
    Frenzy(GetTargetActor())
  EndIf
EndEvent

Event OnCombatStateChanged(Actor akTarget, Int aeCombatState)
  Actor robot = GetTargetActor()
  If aeCombatState == 1 && robot.GetValue(BrainCondition) == 0
    Frenzy(robot)
  EndIf
EndEvent

Function Frenzy(Actor akRobot)
  {Start akRobot's frenzy (a 10% chance to retarget every 5 seconds, FO4's robot values) and its frenzy look.}
  akRobot.StartFrenzyAttack(0.1, 5.0)
  FrenzyShader.Play(akRobot)
  FrenzyLight.Play(akRobot)
EndFunction
