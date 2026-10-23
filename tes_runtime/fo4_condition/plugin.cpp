// FalloutCondition: FO3/FNV item condition on Fallout 4 (docs/fork/fo4_condition.md).
//
// Condition is the engine's own item health (ExtraHealth, 0 to 1) on an inventory stack, which the save keeps.
// Fallout 4 gives Papyrus no way to read or write it on an inventory item, so this plugin adds natives to the
// script TES4_Condition; the rules (wear, effects, repair) live in Papyrus and records. pipboy.cpp shows the
// condition on the Pip-Boy's item card and reports the highlighted item.
// Built against F4SE 0.7.9 for Fallout4.exe 1.11.240.
#include "condition.h"

#include "f4se/PluginAPI.h"
#include "f4se/GameRTTI.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/PapyrusVM.h"
#include "f4se_common/f4se_version.h"

#include <shlobj.h>

namespace condition {

std::mutex g_lock;
std::unordered_set<UInt32> g_tracked;
Selection g_selection;

BGSInventoryItem::Stack *FindStack(TESObjectREFR *holder, TESForm *item, SInt32 index, SInt32 *at) {
    if (!holder || !item || !holder->inventoryList) return nullptr;
    BGSInventoryItem::Stack *first = nullptr, *equipped = nullptr, *indexed = nullptr;
    SInt32 equippedAt = -1;
    BGSInventoryList *list = holder->inventoryList;
    list->inventoryLock.LockForRead();
    for (UInt32 i = 0; i < list->items.count && !first; i++) {
        BGSInventoryItem entry;
        list->items.GetNthItem(i, entry);
        if (entry.form != item) continue;
        SInt32 n = 0;
        for (BGSInventoryItem::Stack *s = entry.stack; s; s = s->next, n++) {
            if (!first) first = s;
            if (n == index) indexed = s;
            if (!equipped && (s->flags & BGSInventoryItem::Stack::kFlagEquipped)) equipped = s, equippedAt = n;
        }
    }
    list->inventoryLock.UnlockRead();
    if (at) *at = indexed ? index : equipped ? equippedAt : first ? 0 : -1;
    return indexed ? indexed : equipped ? equipped : first;
}

float HealthOf(BGSInventoryItem::Stack *stack) {
    if (!stack || !stack->extraData) return -1.0f;
    auto *health = static_cast<ExtraHealth *>(stack->extraData->GetByType(kExtraData_Health));
    return health ? health->health : -1.0f;
}

namespace {

// The engine's own stack writer (Fallout4.exe 1.11.240; docs/fork/fo4_condition.md#stack-writer):
// TESObjectREFR::FindAndWriteStackData(object, compare, write, objectCompare, alwaysContinue) visits the
// stacks of the items objectCompare matches and writes the first the compare functor accepts.
// BGSInventoryItem::CheckStackIDFunctor accepts the stack its countdown reaches; SetHealthFunctor writes
// health, splitting one copy off a shared stack and moving the equipped flag to it (both flags set, as the
// game's own call at 0x98E750 sets them).
using FindAndWrite = void (*)(TESObjectREFR *, TESForm *, void *, void *, bool (*)(TESForm *, TESForm *), bool);
RelocAddr<FindAndWrite> FindAndWriteStackData(0x502560);
RelocAddr<void *> CHECK_STACK_ID_VTABLE(0x247A038), SET_HEALTH_VTABLE(0x252B680);

struct CheckStackID {
    uintptr_t vtable;
    UInt32 countdown;
    UInt32 pad;
};

struct SetHealthWrite {
    uintptr_t vtable;
    UInt8 splitStacks, transferEquipped, pad[6];
    float health;
    UInt32 pad2;
};

bool SameObject(TESForm *a, TESForm *b) {
    return a == b;
}

}  // namespace

bool WriteHealth(TESObjectREFR *holder, TESForm *item, SInt32 index, float value) {
    SInt32 at = -1;
    if (!FindStack(holder, item, index, &at) || at < 0) return false;
    CheckStackID compare = {CHECK_STACK_ID_VTABLE.GetUIntPtr(), UInt32(at), 0};
    SetHealthWrite write = {SET_HEALTH_VTABLE.GetUIntPtr(), 1, 1, {}, value < 0.0f ? 0.0f : value > 1.0f ? 1.0f : value, 0};
    FindAndWriteStackData(holder, item, &compare, &write, SameObject, false);
    return true;
}

}  // namespace condition

namespace {

using namespace condition;

const char *SCRIPT = "TES4_Condition";
PluginHandle g_handle = kPluginHandle_Invalid;
void *g_tasks = nullptr;

// F4SE messages: hook the Pip-Boy once the game has loaded (the UI exists then).
void OnMessage(F4SEMessagingInterface::Message *msg) {
    if (msg->type == F4SEMessagingInterface::kMessage_GameLoaded) InstallPipboy(g_tasks);
}


// Papyrus: the health of `item` in `holder` (0 to 1); -1 when it is not held or has none set yet.
float GetHealth(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item) {
    return HealthOf(FindStack(holder, item));
}

// Papyrus: set `item`'s health in `holder`, adding it when it has none; false when it is not held.
bool SetHealth(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item, float value) {
    return WriteHealth(holder, item, -1, value);
}

// Papyrus: GetHealth on stack `stack` of `item` (-1: its equipped, else first; a stack it lacks: the same).
float GetStackHealth(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item, SInt32 stack) {
    return HealthOf(FindStack(holder, item, stack));
}

// Papyrus: SetHealth on stack `stack` of `item`, as GetStackHealth picks it.
bool SetStackHealth(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item, SInt32 stack, float value) {
    return WriteHealth(holder, item, stack, value);
}

// Papyrus: the health of the weapon `actor` has equipped (0 to 1); -1 with none or none set.
float GetEquippedWeaponHealth(StaticFunctionTag *tag, Actor *actor) {
    if (!actor || !actor->inventoryList) return -1.0f;
    BGSInventoryList *list = actor->inventoryList;
    TESForm *weapon = nullptr;
    list->inventoryLock.LockForRead();
    for (UInt32 i = 0; i < list->items.count && !weapon; i++) {
        BGSInventoryItem entry;
        list->items.GetNthItem(i, entry);
        if (entry.form && entry.form->formType == kFormType_WEAP)
            for (BGSInventoryItem::Stack *s = entry.stack; s; s = s->next)
                if (s->flags & BGSInventoryItem::Stack::kFlagEquipped) weapon = entry.form;
    }
    list->inventoryLock.UnlockRead();
    return weapon ? GetHealth(tag, actor, weapon) : -1.0f;
}

// Papyrus: how many of `item` share its stack in `holder` (they share one condition); 0 when not held.
UInt32 StackCount(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item) {
    BGSInventoryItem::Stack *stack = FindStack(holder, item);
    return stack ? stack->count : 0;
}

// Papyrus: `items` wear, so the Pip-Boy shows their condition; adds to the forms already given.
void Track(StaticFunctionTag *, VMArray<TESForm *> items) {
    std::lock_guard<std::mutex> hold(g_lock);
    for (UInt32 i = 0; i < items.Length(); i++) {
        TESForm *form = nullptr;
        items.Get(&form, i);
        if (form) g_tracked.insert(form->formID);
    }
}

// Papyrus: the item highlighted in the Pip-Boy's inventory when it wears; None otherwise.
TESForm *PipboySelection(StaticFunctionTag *) {
    std::lock_guard<std::mutex> hold(g_lock);
    return g_selection.form ? LookupFormByID(g_selection.form) : nullptr;
}

// Papyrus: the stack index of PipboySelection's item (-1 with none).
SInt32 PipboyStack(StaticFunctionTag *) {
    std::lock_guard<std::mutex> hold(g_lock);
    return g_selection.form ? g_selection.stack : -1;
}

// Papyrus: show the highlighted item's condition again on the Pip-Boy's item card.
void PipboyRefresh(StaticFunctionTag *) {
    RefreshPipboy();
}

// Papyrus: the FNV repair lists (`lists`: weapons' first, then armors', parallel to the two) and the Repair skill.
void TrackRepairLists(StaticFunctionTag *, VMArray<TESForm *> weapons, VMArray<TESForm *> armors,
                      VMArray<TESForm *> lists, ActorValueInfo *skill) {
    for (UInt32 i = 0; i < weapons.Length() + armors.Length() && i < lists.Length(); i++) {
        TESForm *item = nullptr, *list = nullptr;
        if (i < weapons.Length()) weapons.Get(&item, i);
        else armors.Get(&item, i - weapons.Length());
        lists.Get(&list, i);
        TrackRepair(item, list ? DYNAMIC_CAST(list, TESForm, BGSListForm) : nullptr, skill);
    }
    TrackRepair(nullptr, nullptr, skill);
}

// Papyrus: repair stack `stack` of `item` from one copy of `spare` (its stack `spareStack`; -1: its worst):
// the new health, or -1 with no such spare.
float RepairWithNative(StaticFunctionTag *, Actor *holder, TESForm *item, SInt32 stack, TESForm *spare,
                       SInt32 spareStack) {
    return RepairWith(holder, item, stack, spare, spareStack);
}

// Papyrus: carry out the repair chosen in the Pip-Boy's repair list: the new health, or -1 with none chosen.
float PipboyRepair(StaticFunctionTag *, Actor *holder) {
    Repair chosen;
    if (!TakePipboyRepair(&chosen)) return -1.0f;
    return RepairWith(holder, LookupFormByID(chosen.item), chosen.stack, LookupFormByID(chosen.spare),
                      chosen.spareStack);
}

bool Register(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction2<StaticFunctionTag, float, TESObjectREFR *, TESForm *>(
        "GetHealth", SCRIPT, GetHealth, vm));
    vm->RegisterFunction(new NativeFunction3<StaticFunctionTag, bool, TESObjectREFR *, TESForm *, float>(
        "SetHealth", SCRIPT, SetHealth, vm));
    vm->RegisterFunction(new NativeFunction3<StaticFunctionTag, float, TESObjectREFR *, TESForm *, SInt32>(
        "GetStackHealth", SCRIPT, GetStackHealth, vm));
    vm->RegisterFunction(new NativeFunction4<StaticFunctionTag, bool, TESObjectREFR *, TESForm *, SInt32, float>(
        "SetStackHealth", SCRIPT, SetStackHealth, vm));
    vm->RegisterFunction(new NativeFunction1<StaticFunctionTag, float, Actor *>(
        "GetEquippedWeaponHealth", SCRIPT, GetEquippedWeaponHealth, vm));
    vm->RegisterFunction(new NativeFunction2<StaticFunctionTag, UInt32, TESObjectREFR *, TESForm *>(
        "StackCount", SCRIPT, StackCount, vm));
    vm->RegisterFunction(new NativeFunction1<StaticFunctionTag, void, VMArray<TESForm *>>(
        "Track", SCRIPT, Track, vm));
    vm->RegisterFunction(new NativeFunction0<StaticFunctionTag, TESForm *>("PipboySelection", SCRIPT,
                                                                          PipboySelection, vm));
    vm->RegisterFunction(new NativeFunction0<StaticFunctionTag, SInt32>("PipboyStack", SCRIPT, PipboyStack, vm));
    vm->RegisterFunction(new NativeFunction0<StaticFunctionTag, void>("PipboyRefresh", SCRIPT, PipboyRefresh, vm));
    vm->RegisterFunction(new NativeFunction4<StaticFunctionTag, void, VMArray<TESForm *>, VMArray<TESForm *>,
                                             VMArray<TESForm *>, ActorValueInfo *>("TrackRepair", SCRIPT,
                                                                                   TrackRepairLists, vm));
    vm->RegisterFunction(new NativeFunction5<StaticFunctionTag, float, Actor *, TESForm *, SInt32, TESForm *, SInt32>(
        "RepairWith", SCRIPT, RepairWithNative, vm));
    vm->RegisterFunction(new NativeFunction1<StaticFunctionTag, float, Actor *>("PipboyRepair", SCRIPT,
                                                                                PipboyRepair, vm));
    _MESSAGE("registered %s natives", SCRIPT);
    return true;
}

}  // namespace

extern "C" {

__declspec(dllexport) F4SEPluginVersionData F4SEPlugin_Version = {
    F4SEPluginVersionData::kVersion,
    2,
    "FalloutCondition",
    "fo3fnv-in-fo4",
    0,
    0,
    {RUNTIME_VERSION_1_11_240, 0},
    0,
};

__declspec(dllexport) bool F4SEPlugin_Load(const F4SEInterface *f4se) {
    gLog.OpenRelative(CSIDL_MYDOCUMENTS, "\\My Games\\Fallout4\\F4SE\\FalloutCondition.log");
    g_handle = f4se->GetPluginHandle();
    auto *papyrus = static_cast<F4SEPapyrusInterface *>(f4se->QueryInterface(kInterface_Papyrus));
    if (!papyrus) {
        _MESSAGE("no Papyrus interface");
        return false;
    }
    _MESSAGE("FalloutCondition loaded, runtime %08X", f4se->runtimeVersion);
    g_tasks = f4se->QueryInterface(kInterface_Task);
    auto *messaging = static_cast<F4SEMessagingInterface *>(f4se->QueryInterface(kInterface_Messaging));
    if (!messaging || !g_tasks || !messaging->RegisterListener(g_handle, "F4SE", OnMessage))
        _MESSAGE("no Pip-Boy display (messaging %p, task %p)", messaging, g_tasks);
    return papyrus->Register(Register);
}

}
