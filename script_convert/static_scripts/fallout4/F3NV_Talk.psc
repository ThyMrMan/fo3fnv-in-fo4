ScriptName F3NV_Talk Native Hidden
{FNV Goodbye: the talk ends when the Goodbye line ends. Fallout 4 keeps a talk up for about 15 s after a scene of the NPC alone ends, and holds a quest a result script starts until then. The native comes from the F3NV F4SE plugin. See docs/fork/fo4_pipeline.md#goodbye-ends-talk}

Function EndTalk(ObjectReference akSpeaker) Global Native
{akSpeaker's Goodbye line has ended: end its talk with the player on the game's next frame, as the game's own end-of-talk does, unless the player is in another scene that still plays.}
