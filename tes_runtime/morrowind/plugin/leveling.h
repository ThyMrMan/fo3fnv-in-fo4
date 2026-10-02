// Morrowind's attribute step on top of Skyrim's own level-up.
//
// Skyrim keeps the skills and decides when the player levels. This keeps
// what Morrowind adds: every skill increase is credited to its GOVERNING
// attribute (the SKIL record's), and each level the player gains is a pending
// step where three attributes rise by the multiplier those credits earned
// (iLevelUp01Mult..iLevelUp10Mult), as OpenMW's NpcStats does.
//
// Everything lives in DialogueState's variables, so it rides the co-save.
// See: docs/commentary/morrowind_runtime.md#leveling

#pragma once

#include <vector>

namespace tesruntime::mw {

// TES3's attribute count, and its three specializations.
constexpr int kAttributeCount = 8;
constexpr int kSpecializationCount = 3;

// Reads the player's skills and level once. A skill whose BASE rose is
// credited to its namesake Morrowind skill's governing attribute and
// specialization; a level gained queues one step. The first read of a game,
// and any read after the player's race changed, only records what it sees.
// Game thread.
void SampleLeveling();

// Level-ups whose attribute step has not been taken yet.
int PendingLevelUps();

// The level the next pending step belongs to.
int PendingStepLevel();

// Skill increases credited to an attribute or a specialization since the
// last step.
int AttributeIncreases(int attribute);
int SpecializationIncreases(int specialization);

// What choosing `attribute` adds at the step: iLevelUpNNMult for its
// increases (at most 10), 1 with none, and never past 100.
int AttributeGain(int attribute);

// Takes one step: each chosen attribute rises by its gain, the credits reset,
// and one pending level-up is used.
void CompleteLevelUp(const std::vector<int>& attributes);

// Forgets the race the last read saw, so a case starts from a first read.
void ResetLevelingForTest();

}  // namespace tesruntime::mw
