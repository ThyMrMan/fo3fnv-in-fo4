// FalloutCondition's repair (docs/fork/fo4_condition.md#repair-list): FNV's repair from a spare, on one copy.
//
// A spare is an unequipped stack of the same item (another stack, or another copy of the item's own stack) or
// of an item in its FNV repair list (TES4_Condition.TrackRepair). FNV's rule: the better of the two
// conditions, plus 5, plus 0.15 per Repair point, plus 0.05 of the worse, in percent, capped at 100. The
// default spare is the worst one that still gives the best result. Repairing removes one copy of the chosen
// spare stack with the engine's own remove-from-stack, then writes the item's stack (WriteHealth).
#include "condition.h"

#include <algorithm>
#include <unordered_map>

namespace condition {

namespace {

std::unordered_map<UInt32, BGSListForm *> g_repairLists;  // item form ID -> its repair list (under g_lock)
ActorValueInfo *g_repairSkill = nullptr;

// BGSInventoryList::RemoveFromStack(object, stack index, count, more stacks follow): the count removed. It sends
// the inventory event, marks the list's weight dirty and drops an emptied stack (Fallout4.exe 1.11.240, RVA
// 0x34E020, called by TESObjectREFR::RemoveItem once per stack ID; docs/fork/fo4_condition.md#repair-list).
using RemoveFromStackFn = UInt32 (*)(BGSInventoryList *, TESForm *, UInt32, UInt32, bool);
RelocAddr<RemoveFromStackFn> RemoveFromStack(0x34E020);

float Whole(float health) {
    return health < 0.0f ? 1.0f : health;
}

bool InRepairList(TESForm *item, TESForm *form) {
    auto it = g_repairLists.find(item->formID);
    if (it == g_repairLists.end() || !it->second) return false;
    for (UInt32 i = 0; i < it->second->forms.count; i++) {
        TESForm *member = nullptr;
        it->second->forms.GetNthItem(i, member);
        if (member == form) return true;
    }
    return false;
}

}  // namespace

float RepairSkill(Actor *holder) {
    std::lock_guard<std::mutex> hold(g_lock);
    return holder && g_repairSkill ? holder->actorValueOwner.GetValue(g_repairSkill) : 0.0f;
}

float RepairResult(float ours, float theirs, float skill) {
    float better = std::max(ours, theirs), worse = std::min(ours, theirs);
    return std::min(1.0f, better + 0.05f + 0.0015f * skill + 0.05f * worse);
}

std::vector<Spare> Spares(Actor *holder, TESForm *item, SInt32 stack) {
    std::vector<Spare> out;
    if (!holder || !item || !holder->inventoryList) return out;
    std::lock_guard<std::mutex> hold(g_lock);
    BGSInventoryList *list = holder->inventoryList;
    list->inventoryLock.LockForRead();
    for (UInt32 i = 0; i < list->items.count; i++) {
        BGSInventoryItem entry;
        list->items.GetNthItem(i, entry);
        if (!entry.form || (entry.form != item && !InRepairList(item, entry.form))) continue;
        SInt32 n = 0;
        for (BGSInventoryItem::Stack *s = entry.stack; s; s = s->next, n++) {
            bool equipped = (s->flags & BGSInventoryItem::Stack::kFlagEquipped) != 0;
            bool itself = entry.form == item && n == stack;
            if (equipped || (itself && s->count < 2)) continue;
            out.push_back({entry.form, n, Whole(HealthOf(s)), UInt32(s->count)});
        }
    }
    list->inventoryLock.UnlockRead();
    return out;
}

SInt32 DefaultSpare(const std::vector<Spare> &spares, float ours, float skill) {
    float best = -1.0f;
    for (const Spare &s : spares) best = std::max(best, RepairResult(ours, s.health, skill));
    SInt32 chosen = -1;
    for (SInt32 i = 0; i < SInt32(spares.size()); i++)
        if (RepairResult(ours, spares[i].health, skill) >= best - 0.005f &&
            (chosen < 0 || spares[i].health < spares[chosen].health))
            chosen = i;
    return chosen;
}

float RepairWith(Actor *holder, TESForm *item, SInt32 stack, TESForm *spare, SInt32 spareStack) {
    SInt32 at = -1;
    BGSInventoryItem::Stack *target = FindStack(holder, item, stack, &at);
    if (!target || !spare || at < 0) return -1.0f;
    float ours = Whole(HealthOf(target)), skill = RepairSkill(holder);
    std::vector<Spare> spares = Spares(holder, item, at);
    const Spare *used = nullptr;
    for (const Spare &s : spares)
        if (s.form == spare && (spareStack < 0 ? !used || s.health < used->health : s.stack == spareStack)) used = &s;
    if (!used) return -1.0f;
    float result = RepairResult(ours, used->health, skill);
    BGSInventoryList *list = holder->inventoryList;
    list->inventoryLock.LockForWrite();
    UInt32 removed = RemoveFromStack(list, used->form, UInt32(used->stack), 1, false);
    list->inventoryLock.UnlockWrite();
    if (!removed) return -1.0f;
    if (used->form == item && used->stack < at && used->count == 1) at--;
    WriteHealth(holder, item, at, result);
    return result;
}

void TrackRepair(TESForm *item, BGSListForm *list, ActorValueInfo *skill) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (item) g_repairLists[item->formID] = list;
    if (skill) g_repairSkill = skill;
}

}  // namespace condition
