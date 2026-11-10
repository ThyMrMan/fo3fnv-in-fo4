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
//
// A projectile's hit (0xE37220) scales its damage up by the shot's projectile count, resists it, then divides it
// again, so one DT would be shared by a shotgun's pellets. FNV takes DT off each pellet (only a split-beam mod shares
// it), so while that hit resists its damage the DT counts once per pellet.
#include "condition.h"

#include "f4se/GameObjects.h"
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
// A hit's typed damage (HitData, its weapon, the damage scale) and its resistances (HitData, a flag); the projectile
// hit's calls to them, made with the damage scaled up to the whole shot.
using TypedFn = void (*)(void *, void *, float);
using ResistFn = void (*)(void *, bool);
RelocAddr<TypedFn> HitTyped(0xE387B0);
RelocAddr<ResistFn> HitResist(0xE38A00);
RelocAddr<uintptr_t> SHOT_TYPED_CALL(0xE373BF), SHOT_RESIST_CALL(0xE37472);
// HitData: the weapon form and its instance.
const size_t HIT_WEAPON = 0x58, HIT_INSTANCE = 0x60;

// The pellets of the projectile hit being resisted on this thread; 1 for any other hit.
thread_local float t_pellets = 1.0f;

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
    float after = std::max(damage * (1.0f - dr) - std::max(threshold, 0.0f) * t_pellets, damage * g_rules.minDamage);
    return std::min(after / damage, 1.0f);
}

// A firing's projectile count, as the game reads it (one byte); 1 without one.
float Count(const TESObjectWEAP::InstanceData::FiringData *firing) {
    return firing ? std::max<float>(static_cast<UInt8>(firing->numProjectiles), 1.0f) : 1.0f;
}

// The pellets each taking FNV's DT in projectile hit `hit`: its shot's projectile count (the instance's, as the game
// reads it, so an ammo's count counts), or 1 for a gun firing one projectile, whose extra beams are a split beam.
float Pellets(void *hit) {
    auto *at = static_cast<UInt8 *>(hit);
    auto *form = *reinterpret_cast<TESForm **>(at + HIT_WEAPON);
    auto *weapon = form && form->formType == TESObjectWEAP::kTypeID ? static_cast<TESObjectWEAP *>(form) : nullptr;
    if (!weapon || Count(weapon->weapData.firingData) <= 1.0f) return 1.0f;
    auto *instance = *reinterpret_cast<TESObjectWEAP::InstanceData **>(at + HIT_INSTANCE);
    return Count(instance && instance->firingData ? instance->firingData : weapon->weapData.firingData);
}

// The projectile hit's typed damage, with its pellets counted.
void ShotTyped(void *hit, void *weapon, float scale) {
    t_pellets = Pellets(hit);
    HitTyped(hit, weapon, scale);
    t_pellets = 1.0f;
}

// The projectile hit's resistances, with its pellets counted.
void ShotResist(void *hit, bool flag) {
    t_pellets = Pellets(hit);
    HitResist(hit, flag);
    t_pellets = 1.0f;
}

// Whether the call at `site` still calls `target`.
bool Calls(uintptr_t site, uintptr_t target) {
    auto *call = reinterpret_cast<const UInt8 *>(site);
    SInt32 rel;
    std::memcpy(&rel, call + 1, sizeof(rel));
    return call[0] == 0xE8 && site + 5 + rel == target;
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
    if (!Calls(site, ResistCurve.GetUIntPtr())) return false;
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
    uintptr_t shotTyped = SHOT_TYPED_CALL.GetUIntPtr(), shotResist = SHOT_RESIST_CALL.GetUIntPtr();
    bool pellets = Calls(shotTyped, HitTyped.GetUIntPtr()) && Calls(shotResist, HitResist.GetUIntPtr()) &&
                   g_branchTrampoline.Write5Call(shotTyped, uintptr_t(ShotTyped)) &&
                   g_branchTrampoline.Write5Call(shotResist, uintptr_t(ShotResist));
    _MESSAGE("damage threshold: physical %s, typed %s, pellets %s", physical ? "hooked" : "not hooked",
             typed ? "hooked" : "not hooked", pellets ? "hooked" : "not hooked");
    return physical && typed && pellets;
}

void RegisterDamage(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction5<StaticFunctionTag, void, float, float, ActorValueInfo *,
                                             ActorValueInfo *, ActorValueInfo *>(
        "SetRules", DAMAGE_SCRIPT, SetRules, vm));
}

}  // namespace condition
