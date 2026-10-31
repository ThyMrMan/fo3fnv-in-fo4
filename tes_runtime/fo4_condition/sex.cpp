// F3NV: FO3/FNV SexChange on Fallout 4 (docs/fork/fo4_pipeline.md#sex-change).
//
// FO4 Papyrus has no sex setter. The game's own SexChange script command (Fallout4.exe 1.11.240: opcode 0x11E6,
// handler 0x5C5B00) takes an optional sex and an optional integer; given no arguments it toggles the actor's sex
// (the base's female flag, the head rebuilt, the 3D reset), which is what the console's `sexchange` does. The
// native F3NV_Sex.ChangeSex queues that handler on the main thread with an argument count of 0; the caller
// (TES4Polyfill.SetSex) only calls it when the sex differs.
#include "condition.h"

#include "f4se/GameForms.h"
#include "f4se/GameReferences.h"
#include "f4se/GameThreads.h"
#include "f4se/ObScript.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/PluginAPI.h"

#include <cstring>

namespace condition {

namespace {

const char *SEX_SCRIPT = "F3NV_Sex";
F4SETaskInterface *g_sexTasks = nullptr;

// The game's SexChange script command; nullptr when the table has none.
ObScriptCommand *SexChangeCommand() {
    static ObScriptCommand *found = nullptr;
    ObScriptCommand *first = g_firstObScriptCommand;
    for (UInt32 i = 0; !found && i < kObScript_NumObScriptCommands; i++)
        if (first[i].longName && !_stricmp(first[i].longName, "SexChange")) found = &first[i];
    return found;
}

// Run SexChange with no arguments on the actor `formID` names, on the main thread.
class SexChangeTask : public ITaskDelegate {
public:
    explicit SexChangeTask(UInt32 formID) : formID_(formID) {}

    void Run() override {
        TESForm *form = LookupFormByID(formID_);
        ObScriptCommand *command = SexChangeCommand();
        if (!form || form->formType != kFormType_ACHR || !command || !command->execute) {
            _MESSAGE("SexChange on %08X not run (form %p, command %p)", formID_, form, command);
            return;
        }
        UInt8 data[8] = {};  // the command's compiled arguments: a count of 0 at offset 0
        UInt32 offset = 0;
        double result = 0;
        command->execute(command->params, data, static_cast<TESObjectREFR *>(form), nullptr, nullptr, nullptr,
                         &result, &offset);
        _MESSAGE("SexChange on %08X run", formID_);
    }

private:
    UInt32 formID_;
};

// Papyrus: toggle `actor`'s sex (the game's SexChange with no arguments), on the main thread's next task.
void ChangeSex(StaticFunctionTag *, Actor *actor) {
    if (actor && g_sexTasks) g_sexTasks->AddTask(new SexChangeTask(actor->formID));
}

}  // namespace

void RegisterSex(VirtualMachine *vm, void *tasks) {
    g_sexTasks = static_cast<F4SETaskInterface *>(tasks);
    vm->RegisterFunction(new NativeFunction1<StaticFunctionTag, void, Actor *>("ChangeSex", SEX_SCRIPT, ChangeSex, vm));
}

}  // namespace condition
