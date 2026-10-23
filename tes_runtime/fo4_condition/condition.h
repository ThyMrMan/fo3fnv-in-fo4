// FalloutCondition: the item health shared by the Papyrus natives (plugin.cpp) and the Pip-Boy (pipboy.cpp).
#pragma once

#include "f4se/GameExtraData.h"
#include "f4se/GameFormComponents.h"
#include "f4se/GameForms.h"
#include "f4se/GameReferences.h"

#include <mutex>
#include <unordered_set>
#include <vector>

namespace condition {

// The forms that wear (TES4_Condition.Track): the Pip-Boy shows their condition.
extern std::mutex g_lock;
extern std::unordered_set<UInt32> g_tracked;

// The item highlighted in the Pip-Boy's inventory: its form ID (0 for none) and stack index.
struct Selection {
    UInt32 form = 0;
    SInt32 stack = -1;
};
extern Selection g_selection;

// The stack of `item` held by `holder`: stack `index` when it has one, else its equipped one, else its first;
// its index in `at` when given.
BGSInventoryItem::Stack *FindStack(TESObjectREFR *holder, TESForm *item, SInt32 index = -1, SInt32 *at = nullptr);

// A stack's health (0 to 1); -1 with none set yet.
float HealthOf(BGSInventoryItem::Stack *stack);

// Set the health of `item`'s stack `index` in `holder` (as FindStack picks it) through the engine, which splits
// one copy off a shared stack, so only that copy changes; false when it is not held.
bool WriteHealth(TESObjectREFR *holder, TESForm *item, SInt32 index, float value);

// A spare to repair an item with (repair.cpp): a stack of the item or of its repair list, its health, its count.
struct Spare {
    TESForm *form;
    SInt32 stack;
    float health;
    UInt32 count;
};

// `item`'s FNV repair list, and the Repair skill's actor value (TES4_Condition.TrackRepair).
void TrackRepair(TESForm *item, BGSListForm *list, ActorValueInfo *skill);

// The holder's Repair skill.
float RepairSkill(Actor *holder);

// FNV's repaired condition (0 to 1) of an item at `ours` from a spare at `theirs`, at Repair `skill`.
float RepairResult(float ours, float theirs, float skill);

// The holder's spares for stack `stack` of `item` (unequipped stacks of it or of its repair list).
std::vector<Spare> Spares(Actor *holder, TESForm *item, SInt32 stack);

// The index in `spares` of the worst spare that still gives the best result; -1 with none.
SInt32 DefaultSpare(const std::vector<Spare> &spares, float ours, float skill);

// Repair stack `stack` of `item` from one copy of the spare's stack `spareStack` (-1: its worst stack): the new
// health, or -1 when there is no such spare.
float RepairWith(Actor *holder, TESForm *item, SInt32 stack, TESForm *spare, SInt32 spareStack);

// A repair chosen in the Pip-Boy's repair list (pipboy.cpp): the item's stack, and the spare's.
struct Repair {
    UInt32 item = 0;
    SInt32 stack = -1;
    UInt32 spare = 0;
    SInt32 spareStack = -1;
};

// The repair chosen in the Pip-Boy, cleared as it is taken; false with none.
bool TakePipboyRepair(Repair *out);

// Listen for the Pip-Boy opening (pipboy.cpp), with F4SE's task interface; once the game has loaded.
void InstallPipboy(void *taskInterface);

// Ask the Pip-Boy to show the highlighted item's condition again (after a repair).
void RefreshPipboy();

}  // namespace condition
