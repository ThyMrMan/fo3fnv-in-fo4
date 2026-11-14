ScriptName F3NV_PipboyTab extends Quest Hidden
{A Pip-Boy STAT page tab (CRUI_Pipboy.SetTab), given to the plugin as the quest starts and each time the Pip-Boy opens, since the plugin forgets tabs each game start. See docs/fork/fo4_pipboy_tabs.md}

String Property TabName Auto Const
Int Property Order Auto Const
FormList Property Rows Auto Const
String[] Property Values Auto Const
{The string each row value picks; none: the number shows.}
FormList Property Shown Auto Const
{Each row's global showing it (at least 1); None: every row shows.}

Event OnQuestInit()
  RegisterForMenuOpenCloseEvent("PipboyMenu")
  Send()
EndEvent

Event OnMenuOpenCloseEvent(String asMenuName, Bool abOpening)
  If abOpening
    Send()
  EndIf
EndEvent

Function Send()
  {Give the plugin this tab.}
  CRUI_Pipboy.SetTab(TabName, Order, Rows, Values, Shown)
EndFunction
