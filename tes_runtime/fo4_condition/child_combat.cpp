// A child a script put into a fight keeps fighting (docs/fork/fo4_pipeline.md#child-flee). FO4's combat tree flees
// a child before its morale test: the Flee Link condition (0xED96D0, shared by both combat trees) calls
// Actor::IsChild (vtable +0x3F0) at 0xED97BA and flees on true. Fallout3.exe never does. That one call is redirected:
// an actor F3NV_Combat.KeepFighting marked answers false there; every other actor, and every other IsChild call, is
// unchanged. The mark lives for this session only (a load starts with none).
#include "condition.h"

#include "f4se/GameReferences.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se_common/BranchTrampoline.h"
#include "f4se_common/SafeWrite.h"

#include <cstring>
#include <unordered_set>

namespace condition {

namespace {

RelocAddr<uintptr_t> FLEE_CHILD_CALL(0xED97BA);
const UInt8 FLEE_CHILD_BYTES[] = {0xFF, 0x90, 0xF0, 0x03, 0x00, 0x00};
const size_t IS_CHILD_SLOT = 0x3F0 / sizeof(void *);
const char *COMBAT_SCRIPT = "F3NV_Combat";

std::mutex g_fightLock;
std::unordered_set<UInt32> g_fighting;

bool Fighting(UInt32 formID) {
    std::lock_guard<std::mutex> hold(g_fightLock);
    return g_fighting.count(formID) != 0;
}

// The Flee Link's IsChild call: false for an actor a script keeps fighting, else the actor's own IsChild.
bool FleeAsChild(TESForm *actor) {
    if (Fighting(actor->formID)) return false;
    using IsChildFn = bool (*)(TESForm *);
    return (*reinterpret_cast<IsChildFn **>(actor))[IS_CHILD_SLOT](actor);
}

void KeepFighting(StaticFunctionTag *, Actor *actor, bool on) {
    if (!actor) return;
    std::lock_guard<std::mutex> hold(g_fightLock);
    if (on) g_fighting.insert(actor->formID);
    else g_fighting.erase(actor->formID);
    _MESSAGE("child combat: %08X %s", actor->formID, on ? "keeps fighting" : "back to FO4's flee");
}

}  // namespace

bool HookChildCombat() {
    uintptr_t site = FLEE_CHILD_CALL.GetUIntPtr();
    bool found = !std::memcmp(reinterpret_cast<const void *>(site), FLEE_CHILD_BYTES, sizeof(FLEE_CHILD_BYTES));
    bool hooked = found && g_branchTrampoline.Write5Call(site, uintptr_t(FleeAsChild));
    if (hooked) SafeWrite8(site + 5, 0x90);
    _MESSAGE("child combat flee %s", hooked ? "hooked" : found ? "not hooked" : "not hooked (call not found)");
    return hooked;
}

void RegisterChildCombat(VirtualMachine *vm) {
    vm->RegisterFunction(
        new NativeFunction2<StaticFunctionTag, void, Actor *, bool>("KeepFighting", COMBAT_SCRIPT, KeepFighting, vm));
}

}  // namespace condition
