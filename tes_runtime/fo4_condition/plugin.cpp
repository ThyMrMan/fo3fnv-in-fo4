// FalloutCondition: FO3/FNV item condition on Fallout 4 (docs/fork/fo4_condition.md).
//
// Condition is the engine's own item health (ExtraHealth, 0 to 1) on an inventory stack, which the save keeps.
// Fallout 4 gives Papyrus no way to read or write it on an inventory item, so this plugin adds four natives to
// the script TES4_Condition; the rules (wear, effects, repair) live in Papyrus and records.
// Built against F4SE 0.7.9 for Fallout4.exe 1.11.240.
#include "f4se/PluginAPI.h"
#include "f4se/GameExtraData.h"
#include "f4se/GameFormComponents.h"
#include "f4se/GameForms.h"
#include "f4se/GameReferences.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/PapyrusVM.h"
#include "f4se_common/f4se_version.h"

#include <shlobj.h>

namespace {

const char *SCRIPT = "TES4_Condition";
PluginHandle g_handle = kPluginHandle_Invalid;

// The stack of `item` held by `holder`: its equipped one when it has one, else its first; null when not held.
BGSInventoryItem::Stack *FindStack(TESObjectREFR *holder, TESForm *item) {
    if (!holder || !item || !holder->inventoryList) return nullptr;
    BGSInventoryItem::Stack *first = nullptr, *equipped = nullptr;
    BGSInventoryList *list = holder->inventoryList;
    list->inventoryLock.LockForRead();
    for (UInt32 i = 0; i < list->items.count && !equipped; i++) {
        BGSInventoryItem entry;
        list->items.GetNthItem(i, entry);
        if (entry.form != item) continue;
        for (BGSInventoryItem::Stack *s = entry.stack; s; s = s->next) {
            if (!first) first = s;
            if (s->flags & BGSInventoryItem::Stack::kFlagEquipped) {
                equipped = s;
                break;
            }
        }
    }
    list->inventoryLock.UnlockRead();
    return equipped ? equipped : first;
}

ExtraHealth *HealthOf(BGSInventoryItem::Stack *stack) {
    return stack && stack->extraData ? static_cast<ExtraHealth *>(stack->extraData->GetByType(kExtraData_Health))
                                     : nullptr;
}

// Papyrus: the health of `item` in `holder` (0 to 1); -1 when it is not held or has none set yet.
float GetHealth(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item) {
    ExtraHealth *health = HealthOf(FindStack(holder, item));
    return health ? health->health : -1.0f;
}

// Papyrus: set `item`'s health in `holder`, adding it when it has none; false when it is not held.
bool SetHealth(StaticFunctionTag *, TESObjectREFR *holder, TESForm *item, float value) {
    BGSInventoryItem::Stack *stack = FindStack(holder, item);
    if (!stack) return false;
    float clamped = value < 0.0f ? 0.0f : value > 1.0f ? 1.0f : value;
    if (ExtraHealth *health = HealthOf(stack)) {
        health->health = clamped;
        return true;
    }
    if (!stack->extraData) return false;
    return stack->extraData->Add(kExtraData_Health, ExtraHealth::Create(clamped));
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

bool Register(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction2<StaticFunctionTag, float, TESObjectREFR *, TESForm *>(
        "GetHealth", SCRIPT, GetHealth, vm));
    vm->RegisterFunction(new NativeFunction3<StaticFunctionTag, bool, TESObjectREFR *, TESForm *, float>(
        "SetHealth", SCRIPT, SetHealth, vm));
    vm->RegisterFunction(new NativeFunction1<StaticFunctionTag, float, Actor *>(
        "GetEquippedWeaponHealth", SCRIPT, GetEquippedWeaponHealth, vm));
    vm->RegisterFunction(new NativeFunction2<StaticFunctionTag, UInt32, TESObjectREFR *, TESForm *>(
        "StackCount", SCRIPT, StackCount, vm));
    _MESSAGE("registered %s natives", SCRIPT);
    return true;
}

}  // namespace

extern "C" {

__declspec(dllexport) F4SEPluginVersionData F4SEPlugin_Version = {
    F4SEPluginVersionData::kVersion,
    1,
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
    return papyrus->Register(Register);
}

}
