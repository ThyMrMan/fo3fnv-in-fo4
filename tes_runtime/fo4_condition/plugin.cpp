// F3NV: FNV's own rules on Fallout 4 (condition.h; docs/fork/spin_offs.md#move): weapons' starting condition and
// no combat sprint (here), Damage Threshold, Hardcore, a Goodbye ending the talk, and the casino movie's natives.
// The item condition API and the Pip-Boy are Cleanroom UI's CleanroomUI.dll, which this plugin no longer carries.
// Built against F4SE 0.7.9 for Fallout4.exe 1.11.240.
#include "condition.h"

#include "f4se/PluginAPI.h"
#include "f4se/GameReferences.h"
#include "f4se/GameSettings.h"
#include "f4se/PapyrusVM.h"
#include "f4se_common/BranchTrampoline.h"
#include "f4se_common/f4se_version.h"

#include <shlobj.h>

namespace condition {

std::mutex g_lock;

}  // namespace condition

namespace {

using namespace condition;

PluginHandle g_handle = kPluginHandle_Invalid;
void *g_tasks = nullptr;

// ---- Starting condition (docs/fork/fo4_condition.md#entry-condition) ----
// The game gives an item spawned from an inventory entry the entry's COED condition (0x271570) only when the
// item has a maximum health (0x316940: armor's own field, ammo's charge, else a health component). Weapons have
// none, so their COED was dropped. The one call there (0x271611) is redirected: a weapon answers 1, so its
// condition applies. Vanilla puts COED only on power armor entries, so only FNV's data is affected.
using MaxHealthFn = UInt32 (*)(TESForm *, TESObjectREFR *);
RelocAddr<MaxHealthFn> MaxHealth(0x316940);
RelocAddr<uintptr_t> SPAWN_HEALTH_CALL(0x271611);
// The spawn-health call, damage.cpp's four calls and two stubs, hardcore.cpp's call.
const size_t TRAMPOLINE_SIZE = 256;

UInt32 SpawnMaxHealth(TESForm *form, TESObjectREFR *ref) {
    UInt32 health = MaxHealth(form, ref);
    return health || !form || form->formType != kFormType_WEAP ? health : 1;
}

// Redirect the spawn routine's max-health call to SpawnMaxHealth, with F4SE's branch pool; false when it cannot.
bool HookSpawnHealth(const F4SEInterface *f4se) {
    auto *trampolines = static_cast<F4SETrampolineInterface *>(f4se->QueryInterface(kInterface_Trampoline));
    void *pool = trampolines ? trampolines->AllocateFromBranchPool(g_handle, TRAMPOLINE_SIZE) : nullptr;
    if (!pool) return false;
    g_branchTrampoline.SetBase(TRAMPOLINE_SIZE, pool);
    return g_branchTrampoline.Write5Call(SPAWN_HEALTH_CALL.GetUIntPtr(), uintptr_t(SpawnMaxHealth));
}

// ---- No combat sprint (docs/fork/fo4_pipeline.md#combat-sprint) ----
// FO3/FNV actors never sprint; FO4's approach controller (0x1008c20) sprints at a far target while the INI setting
// bCombatPathSprinting:Combat (its Setting at 0x2F38A98, read at 0x1008f12) is on. Turned off for every actor, as
// FNV plays; set at load and again once the game has loaded, after the INI files are read.
RelocAddr<Setting *> COMBAT_PATH_SPRINTING(0x2F38A98);
const char *SPRINT_SETTING = "bCombatPathSprinting:Combat";

void NoCombatSprint() {
    auto *setting = reinterpret_cast<Setting *>(COMBAT_PATH_SPRINTING.GetUIntPtr());
    bool found = setting->name && !strcmp(setting->name, SPRINT_SETTING);
    if (found) setting->data.u8 = 0;
    _MESSAGE("combat approach sprint %s", found ? "off" : "left on (setting not found)");
}

// F4SE messages: once the game has loaded (the INI files are read and the UI exists), no combat sprint again and
// listen for menus for the Hardcore HUD.
void OnMessage(F4SEMessagingInterface::Message *msg) {
    if (msg->type != F4SEMessagingInterface::kMessage_GameLoaded) return;
    NoCombatSprint();
    InstallHud(g_tasks);
}

bool Register(VirtualMachine *vm) {
    RegisterTalk(vm, g_tasks);
    RegisterDamage(vm);
    RegisterHardcore(vm);
    _MESSAGE("registered F3NV's natives");
    return true;
}

}  // namespace

extern "C" {

__declspec(dllexport) F4SEPluginVersionData F4SEPlugin_Version = {
    F4SEPluginVersionData::kVersion,
    3,
    "F3NV",
    "fo3fnv-in-fo4",
    0,
    0,
    {RUNTIME_VERSION_1_11_240, 0},
    0,
};

__declspec(dllexport) bool F4SEPlugin_Load(const F4SEInterface *f4se) {
    gLog.OpenRelative(CSIDL_MYDOCUMENTS, "\\My Games\\Fallout4\\F4SE\\F3NV.log");
    g_handle = f4se->GetPluginHandle();
    auto *papyrus = static_cast<F4SEPapyrusInterface *>(f4se->QueryInterface(kInterface_Papyrus));
    if (!papyrus) {
        _MESSAGE("no Papyrus interface");
        return false;
    }
    _MESSAGE("F3NV loaded, runtime %08X", f4se->runtimeVersion);
    g_tasks = f4se->QueryInterface(kInterface_Task);
    auto *messaging = static_cast<F4SEMessagingInterface *>(f4se->QueryInterface(kInterface_Messaging));
    bool trampoline = HookSpawnHealth(f4se);
    _MESSAGE("weapon starting condition %s", trampoline ? "hooked" : "not hooked");
    if (trampoline) HookDamage(), HookAmmoWeight();
    auto *scaleform = static_cast<F4SEScaleformInterface *>(f4se->QueryInterface(kInterface_Scaleform));
    if (!scaleform || !scaleform->Register("F3NV", RegisterMovieNatives)) _MESSAGE("no movie natives");
    NoCombatSprint();
    if (!messaging || !g_tasks || !messaging->RegisterListener(g_handle, "F4SE", OnMessage))
        _MESSAGE("no Hardcore HUD (messaging %p, task %p)", messaging, g_tasks);
    return papyrus->Register(Register);
}

}
