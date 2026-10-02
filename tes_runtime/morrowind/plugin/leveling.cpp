#include "leveling.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>

#include "actor_stats.h"
#include "dialogue_state.h"
#include "log.h"
#include "script_tables.h"

namespace tesruntime::mw {

namespace {

// Where the progress is kept among DialogueState's variables.
constexpr const char* kOwner = "leveling|player";
constexpr const char* kLevelVar = "level";
constexpr const char* kPendingVar = "pending";

constexpr const char* kPlayer = "player";

// The attribute and increase caps OpenMW's LevelupDialog applies.
constexpr int kAttributeMax = 100;
constexpr int kMaxCountedIncreases = 10;

// A Skyrim skill, and the Morrowind skill whose SKIL record governs it: its
// namesake, or for a folded skill the one it is named after (One- and
// Two-Handed are Long Blade, Morrowind's sword skill; Pickpocket is Sneak,
// which picked pockets in Morrowind).
// See: docs/commentary/morrowind_runtime.md#leveling
struct Tracked {
    const char* skyrim;
    int tes3;
};

constexpr Tracked kTracked[] = {
    {"OneHanded", 5},    {"TwoHanded", 5},    {"Marksman", 23},
    {"Block", 0},        {"Smithing", 1},     {"HeavyArmor", 3},
    {"LightArmor", 21},  {"Pickpocket", 19},  {"Lockpicking", 18},
    {"Sneak", 19},       {"Alchemy", 16},     {"Speechcraft", 25},
    {"Alteration", 11},  {"Conjuration", 13}, {"Destruction", 10},
    {"Illusion", 12},    {"Restoration", 15}, {"Enchanting", 9},
};

// The race the last read saw. In memory only: a load restores the skills and
// the samples together, so treating the first read after one as a change
// costs nothing.
const void* g_race = nullptr;

std::string BaseKey(const char* skill) { return std::string("base.") + skill; }

std::string IncreaseKey(int attribute) {
    return "inc" + std::to_string(attribute);
}

std::string SpecializationKey(int specialization) {
    return "spec" + std::to_string(specialization);
}

int Counter(const std::string& name) {
    return static_cast<int>(State().Var(kOwner, name));
}

void AddTo(const std::string& name, int amount) {
    State().SetVar(kOwner, name, static_cast<float>(Counter(name) + amount));
}

void Credit(const Tracked& skill, int amount) {
    const SkillDef* def = FindSkill(skill.tes3);
    if (!def) return;
    if (def->attribute >= 0 && def->attribute < kAttributeCount) {
        AddTo(IncreaseKey(def->attribute), amount);
    }
    if (def->specialization >= 0 && def->specialization < kSpecializationCount) {
        AddTo(SpecializationKey(def->specialization), amount);
    }
}

// Records each skill's base, crediting what rose when `credit` is set.
void SampleSkills(bool credit) {
    for (const Tracked& skill : kTracked) {
        const int now = static_cast<int>(
            std::floor(Hooks().baseActorValue(kPlayer, skill.skyrim)));
        const std::string key = BaseKey(skill.skyrim);
        const bool known = State().HasVar(kOwner, key);
        const int rise = known ? now - Counter(key) : 0;
        if (credit && rise > 0) Credit(skill, rise);
        State().SetVar(kOwner, key, static_cast<float>(now));
    }
}

void SampleLevel(bool credit) {
    const int now = Hooks().playerLevel();
    const int seen = Counter(kLevelVar);
    if (credit && now > seen) {
        AddTo(kPendingVar, now - seen);
        Log("leveling: level %d -> %d, %d step(s) pending", seen, now,
            PendingLevelUps());
    }
    State().SetVar(kOwner, kLevelVar, static_cast<float>(now));
}

}  // namespace

void SampleLeveling() {
    if (!Hooks().baseActorValue || !Hooks().playerLevel) return;
    const void* race = Hooks().race ? Hooks().race(kPlayer) : nullptr;
    const bool raceChanged = race != g_race;
    g_race = race;
    const bool first = !State().HasVar(kOwner, kLevelVar);
    SampleSkills(!first && !raceChanged);
    SampleLevel(!first);
}

int PendingLevelUps() { return std::max(0, Counter(kPendingVar)); }

int PendingStepLevel() {
    return Counter(kLevelVar) - PendingLevelUps() + 1;
}

int AttributeIncreases(int attribute) {
    return Counter(IncreaseKey(attribute));
}

int SpecializationIncreases(int specialization) {
    return Counter(SpecializationKey(specialization));
}

int AttributeGain(int attribute) {
    const int current = static_cast<int>(ActorAttribute(kPlayer, attribute));
    const int count = std::min(kMaxCountedIncreases, AttributeIncreases(attribute));
    int gain = 1;
    if (count > 0) {
        char name[16];
        std::snprintf(name, sizeof(name), "iLevelUp%02dMult", count);
        gain = static_cast<int>(GmstNumber(name, 1.0f));
    }
    return std::max(0, std::min(gain, kAttributeMax - current));
}

void CompleteLevelUp(const std::vector<int>& attributes) {
    for (int attribute : attributes) {
        const int gain = AttributeGain(attribute);
        const float now = ActorAttribute(kPlayer, attribute);
        SetActorAttribute(kPlayer, attribute, now + static_cast<float>(gain));
        Log("leveling: attribute %d %.0f -> %.0f", attribute, now, now + gain);
    }
    for (int i = 0; i < kAttributeCount; ++i) {
        State().SetVar(kOwner, IncreaseKey(i), 0.0f);
    }
    for (int i = 0; i < kSpecializationCount; ++i) {
        State().SetVar(kOwner, SpecializationKey(i), 0.0f);
    }
    AddTo(kPendingVar, -1);
    if (Counter(kPendingVar) < 0) State().SetVar(kOwner, kPendingVar, 0.0f);
}

void ResetLevelingForTest() { g_race = nullptr; }

}  // namespace tesruntime::mw
