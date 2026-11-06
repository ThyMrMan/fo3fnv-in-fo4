ScriptName F3NV_TraceTopicInfo extends TopicInfo Hidden
{Traces a line with no converted script as it begins: a player's menu choice, a pad, or the Tab exit line (TES4Polyfill.TraceTopicInfo); nothing while tracing is off.
See: docs/fork/fo4_pipeline.md#dialogue-trace}

Function Fragment_Begin(ObjectReference akSpeakerRef)
  TES4Polyfill.TraceTopicInfo(Self, akSpeakerRef)
EndFunction
