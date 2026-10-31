// F3NV: FO3/FNV Damage Threshold and Damage Resistance on Fallout 4 (docs/fork/fo4_pipeline.md#damage-threshold).
//
// Hook approach after Zoltanite's "Modular Damage Threshold System - F4SE" (Nexus Fallout 4 mod 109168; credit
// Zoltanite as its creator; docs/fork/research/fo4_damage_threshold_reference.md). The code is ours, from our own
// disassembly of Fallout4.exe 1.11.240.
//
// FO4 scales a hit by its resistance curve (0x6CB2E0: actor value, damage, resistance -> the share that gets
// through). It is called for physical damage at 0xE38C3D (the resistance after the attacker's Mod Target Damage
// Resistance perks; the target in rsi) and per damage type at 0xE3AF4A (the target's object at [[rbx]]). Both calls
// go to a stub that adds the target and jumps to FalloutDamage, which for physical and energy damage returns FNV's
// share instead (FalloutNV.exe 0x9B5A30): damage x (1 - DR), DR capped, minus DT, never below the floor. FO4's
// DamageResist carries FNV's DT (armor, abilities, ammo piercing as perks); FNV's DR is the helper plugin's actor
// value. Other damage types keep FO4's curve. Off until F3NV_Damage.SetRules names the actor values.
#include "condition.h"

#include "f4se/GameReferences.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se_common/BranchTrampoline.h"

#include <algorithm>
#include <cstring>

namespace condition {

namespace {

const char *DAMAGE_SCRIPT = "F3NV_Damage";
using CurveFn = float (*)(ActorValueInfo *, float, float);
RelocAddr<CurveFn> ResistCurve(0x6CB2E0);
RelocAddr<uintptr_t> PHYSICAL_CALL(0xE38C3D), TYPED_CALL(0xE3AF4A);
// The stubs' target loads: physical `mov r9, rsi`; typed `mov r9, [rbx]; mov r9, [r9]`.
const UInt8 PHYSICAL_TARGET[] = {0x49, 0x89, 0xF1};
const UInt8 TYPED_TARGET[] = {0x4C, 0x8B, 0x0B, 0x4D, 0x8B, 0x09};

struct Rules {
    float minDamage = 0.0f;  // fMinDamMultiplier
    float maxResist = 0.0f;  // fMaxArmorRating / 100
    ActorValueInfo *resist = nullptr;     // FNV's DR (the helper plugin's)
    ActorValueInfo *threshold = nullptr;  // FO4's DamageResist, FNV's DT
    ActorValueInfo *energy = nullptr;     // FO4's EnergyResist
} g_rules;

float Value(TESObjectREFR *target, ActorValueInfo *av) {
    return target && av ? target->actorValueOwner.GetValue(av) : 0.0f;
}

// FO4's resistance curve's place: for physical and energy damage, FNV's share of `damage` that gets through.
float FalloutDamage(ActorValueInfo *av, float damage, float resist, TESObjectREFR *target) {
    bool physical = av && av == g_rules.threshold, energy = av && av == g_rules.energy;
    if (!g_rules.threshold || damage <= 0.0f || !(physical || energy)) return ResistCurve(av, damage, resist);
    float threshold = physical ? resist : Value(target, g_rules.threshold);
    float dr = std::min(std::max(Value(target, g_rules.resist) / 100.0f, 0.0f), g_rules.maxResist);
    float after = std::max(damage * (1.0f - dr) - std::max(threshold, 0.0f), damage * g_rules.minDamage);
    return std::min(after / damage, 1.0f);
}

// A stub at a resistance-curve call: `load` (the target into r9), then jump to FalloutDamage.
uintptr_t Stub(const UInt8 *load, size_t size) {
    auto *code = static_cast<UInt8 *>(g_branchTrampoline.Allocate(size + 12));
    if (!code) return 0;
    std::memcpy(code, load, size);
    code[size] = 0x48, code[size + 1] = 0xB8;  // mov rax, FalloutDamage
    uintptr_t hook = reinterpret_cast<uintptr_t>(&FalloutDamage);
    std::memcpy(code + size + 2, &hook, sizeof(hook));
    code[size + 10] = 0xFF, code[size + 11] = 0xE0;  // jmp rax
    return reinterpret_cast<uintptr_t>(code);
}

// Point the call at `site` to a stub loading the target with `load`, when it still calls the resistance curve.
bool Patch(uintptr_t site, const UInt8 *load, size_t size) {
    auto *call = reinterpret_cast<const UInt8 *>(site);
    SInt32 rel;
    std::memcpy(&rel, call + 1, sizeof(rel));
    if (call[0] != 0xE8 || site + 5 + rel != ResistCurve.GetUIntPtr()) return false;
    uintptr_t stub = Stub(load, size);
    return stub && g_branchTrampoline.Write5Call(site, stub);
}

// Papyrus: FNV's rules (fMinDamMultiplier, fMaxArmorRating / 100) and the actor values of DR, DT and energy resist.
void SetRules(StaticFunctionTag *, float minDamage, float maxResist, ActorValueInfo *resist, ActorValueInfo *threshold,
              ActorValueInfo *energy) {
    g_rules.minDamage = minDamage, g_rules.maxResist = maxResist;
    g_rules.resist = resist, g_rules.threshold = threshold, g_rules.energy = energy;
    _MESSAGE("damage rules: floor %.2f, DR cap %.2f", minDamage, maxResist);
}

}  // namespace

bool HookDamage() {
    bool physical = Patch(PHYSICAL_CALL.GetUIntPtr(), PHYSICAL_TARGET, sizeof(PHYSICAL_TARGET));
    bool typed = Patch(TYPED_CALL.GetUIntPtr(), TYPED_TARGET, sizeof(TYPED_TARGET));
    _MESSAGE("damage threshold: physical %s, typed %s", physical ? "hooked" : "not hooked",
             typed ? "hooked" : "not hooked");
    return physical && typed;
}

void RegisterDamage(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction5<StaticFunctionTag, void, float, float, ActorValueInfo *,
                                             ActorValueInfo *, ActorValueInfo *>(
        "SetRules", DAMAGE_SCRIPT, SetRules, vm));
}

}  // namespace condition
