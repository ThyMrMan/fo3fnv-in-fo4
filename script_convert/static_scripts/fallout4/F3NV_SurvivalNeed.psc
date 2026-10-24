ScriptName F3NV_SurvivalNeed extends ActiveMagicEffect Hidden
{An FNV Hardcore need effect fed to Survival mode's own manager, only while Rule is on. Need 0 (hunger) and 1 (thirst) change Survival's food or drink pool by Amount (raising the need when negative), eating or drinking adding Survival's disease risk as its own food and drink do; Need 2 (sleep) equips Caffeine, a hidden potion the manager handles as a caffeinated drink. See docs/fork/fo4_pipeline.md#survival-needs.}

Hardcore:HC_ManagerScript Property HC_Manager Auto Const Mandatory
GlobalVariable Property Rule Auto Const Mandatory
{HC_Rule_SustenanceEffects for hunger and thirst, HC_Rule_SleepEffects for sleep.}
Int Property Need Auto Const
Float Property Amount Auto Const
{Survival pool points, as vanilla's AddictionOddsScript carries its Magnitude: FO4 effects cannot read their own.}
Potion Property Caffeine Auto Const

Event OnEffectStart(Actor akTarget, Actor akCaster)
  If akTarget != Game.GetPlayer() || !HC_Manager.IsGlobalTrue(Rule)
    Return
  EndIf
  If Need == 0
    HC_Manager.ModFoodPoolAndUpdateHungerEffects(Amount)
    If Amount > 0
      HC_Manager.FillDiseaseRiskPool(HC_Manager.DiseaseRiskIncreaser_Food)
    EndIf
  ElseIf Need == 1
    HC_Manager.ModDrinkPoolAndUpdateThirstEffects(Amount as Int)
    If Amount > 0
      HC_Manager.FillDiseaseRiskPool(HC_Manager.DiseaseRiskIncreaser_Drink)
    EndIf
  ElseIf Caffeine
    akTarget.EquipItem(Caffeine, False, True)
  EndIf
EndEvent
