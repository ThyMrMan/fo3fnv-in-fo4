// F3NV's vendor repair (docs/fork/fo4_condition.md#vendor-repair): FNV's ShowRepairMenu, offered on
// the Pip-Boy's repair card while a vendor is set (pipboy.cpp).
//
// FalloutNV.exe's rule (0x648230, called by RepairServicesMenu 0x7B7920 per item): the vendor reaches
// fRepairSkillBase + (fRepairSkillMax - fRepairSkillBase) x Repair / 100 tenths of condition (FalloutNV.esm: 4
// and 10, so 40% plus 0.6% a point); the price is fItemRepairCostMult (2) x the item's value x the tenths gained
// / 10, nothing at 0.5 or less, else at least 1 cap. Paying removes the caps with the engine's remove-from-stack.
#include "condition.h"

#include "f4se/GameObjects.h"

#include <algorithm>
#include <cmath>

namespace condition {

namespace {

const UInt32 CAPS = 0x0000000F;  // Fallout4.esm's Caps001
float g_skillBase = 4.0f, g_skillMax = 10.0f, g_costMult = 2.0f;  // under g_lock
bool g_vendor = false;
std::string g_vendorName;
float g_vendorSkill = 0.0f;

}  // namespace

void SetServiceRules(float skillBase, float skillMax, float costMult) {
    std::lock_guard<std::mutex> hold(g_lock);
    g_skillBase = skillBase, g_skillMax = skillMax, g_costMult = costMult;
}

void SetVendor(Actor *vendor) {
    float skill = vendor ? RepairSkill(vendor) : 0.0f;
    const char *name = vendor && vendor->baseForm ? vendor->baseForm->GetFullName() : nullptr;
    std::lock_guard<std::mutex> hold(g_lock);
    if (!vendor && !g_vendor) return;
    g_vendor = vendor != nullptr;
    g_vendorName = name ? name : "";
    g_vendorSkill = skill;
    _MESSAGE("repair vendor %s (Repair %.0f)", g_vendor ? g_vendorName.c_str() : "cleared", skill);
}

bool Vendor(std::string *name, float *skill) {
    std::lock_guard<std::mutex> hold(g_lock);
    *name = g_vendorName;
    *skill = g_vendorSkill;
    return g_vendor;
}

Offer VendorOffer(float health, UInt32 value, float skill) {
    std::lock_guard<std::mutex> hold(g_lock);
    float cap = g_skillBase + (g_skillMax - g_skillBase) * skill / 100.0f;
    float cost = g_costMult * float(value) * (cap - health * 10.0f) / 10.0f;
    if (cost <= 0.5f) return {health, 0};
    return {std::min(1.0f, cap / 10.0f), std::max<UInt32>(1, UInt32(std::lround(cost)))};
}

UInt32 ItemValue(TESForm *item) {
    if (!item) return 0;
    if (item->formType == kFormType_WEAP) return static_cast<TESObjectWEAP *>(item)->weapData.value;
    if (item->formType == kFormType_ARMO) return static_cast<TESObjectARMO *>(item)->instanceData.value;
    return 0;
}

UInt32 Caps(Actor *holder) {
    BGSInventoryList *list = holder ? holder->inventoryList : nullptr;
    if (!list) return 0;
    UInt32 total = 0;
    list->inventoryLock.LockForRead();
    for (UInt32 i = 0; i < list->items.count; i++) {
        BGSInventoryItem entry;
        list->items.GetNthItem(i, entry);
        if (!entry.form || entry.form->formID != CAPS) continue;
        for (BGSInventoryItem::Stack *s = entry.stack; s; s = s->next) total += s->count;
    }
    list->inventoryLock.UnlockRead();
    return total;
}

float BuyRepair(Actor *holder, TESForm *item, SInt32 stack, UInt32 cost, float health) {
    SInt32 at = -1;
    if (!FindStack(holder, item, stack, &at) || at < 0) return -1.0f;
    if (Caps(holder) < cost) return -2.0f;
    TESForm *caps = LookupFormByID(CAPS);
    BGSInventoryList *list = holder->inventoryList;
    list->inventoryLock.LockForWrite();
    for (UInt32 paid = 0, removed = 1; paid < cost && removed;) {
        removed = TakeFromStack(list, caps, 0, cost - paid);
        paid += removed;
    }
    list->inventoryLock.UnlockWrite();
    WriteHealth(holder, item, at, health);
    return health;
}

}  // namespace condition
