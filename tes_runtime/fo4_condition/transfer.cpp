// F3NV's transfer and barter menus: a CND line on the item card for items that wear, each line at
// its own stack's condition (docs/fork/fo4_condition.md#transfer-menu).
//
// Each menu builds its Flash lines with a virtual function, slot 28 of ContainerMenu's and BarterMenu's vtables
// (Fallout4.exe 1.11.240: 0x103E690 and 0xA4B500; ContainerMenuBase leaves it pure). Its arguments: the menu,
// the owner's reference handle, the game's line record (an InventoryInterface handle, then the line's stack
// indices: count at +8, inline at +0x10 when the count is negative, else a pointer there) and the Flash line.
// Both slots are replaced: the original builds the line, then the line's item (InventoryInterface lookup,
// 0x347C10) and first stack give it fnvCND, its condition. While a menu is open, a native enterFrame listener
// keeps a CND line at the highlighted line's fnvCND on the item card (whose InfoObj is that line's
// ItemCardInfoList).
#include "condition.h"

#include "f4se/GameMenus.h"
#include "f4se/ScaleformCallbacks.h"
#include "f4se_common/SafeWrite.h"

#include <string>

namespace condition {

namespace {

using LineFn = void (*)(void *, UInt32 *, UInt8 *, GFxValue *);
using ItemOfFn = BGSInventoryItem *(*)(void *, UInt8 *);
RelocPtr<void *> g_inventoryInterface(0x30EC470);
RelocAddr<ItemOfFn> ItemOf(0x347C10);
RelocAddr<uintptr_t> CONTAINER_LINE_SLOT(0x25AC7A8), BARTER_LINE_SLOT(0x2534710);
LineFn g_containerLine = nullptr, g_barterLine = nullptr;
const char *STAMP = "fnvCND", *HOOKED = "fnvConditionHooked";
const char *LISTS[] = {"ContainerList_mc", "PlayerInventory_mc.PlayerList_mc"};

// The health (0 to 1) of game line record `entry`'s first stack, when its item wears; -1 otherwise.
float LineHealth(UInt8 *entry) {
    BGSInventoryItem *item = entry ? ItemOf(*g_inventoryInterface, entry) : nullptr;
    if (!item || !item->form) return -1.0f;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        if (!g_tracked.count(item->form->formID)) return -1.0f;
    }
    SInt32 count = *reinterpret_cast<SInt32 *>(entry + 8);
    if (!count) return -1.0f;
    UInt16 *stacks = count < 0 ? reinterpret_cast<UInt16 *>(entry + 0x10) : *reinterpret_cast<UInt16 **>(entry + 0x10);
    BGSInventoryItem::Stack *stack = item->stack;
    for (UInt16 n = 0; stack && n < stacks[0]; n++) stack = stack->next;
    if (!stack) return -1.0f;
    float health = HealthOf(stack);
    return health < 0.0f ? 1.0f : health;
}

void Stamp(UInt8 *entry, GFxValue *line) {
    float health = line && line->IsObject() ? LineHealth(entry) : -1.0f;
    if (health < 0.0f) return;
    GFxValue value;
    value.SetNumber(health);
    line->SetMember(STAMP, &value);
}

void ContainerLine(void *menu, UInt32 *owner, UInt8 *entry, GFxValue *line) {
    g_containerLine(menu, owner, entry, line);
    Stamp(entry, line);
}

void BarterLine(void *menu, UInt32 *owner, UInt8 *entry, GFxValue *line) {
    g_barterLine(menu, owner, entry, line);
    Stamp(entry, line);
}

std::string g_base;  // the path of the open transfer menu's instance (UI thread only)

// Log an object's members by name and GFx type (the menu's root, when its item card is not found).
class LogMembers : public GFxValue::ObjectInterface::ObjVisitor {
public:
    void Visit(const char *member, GFxValue *value) override {
        _MESSAGE("  member %s (type %d)", member, value->GetType());
    }
} g_logMembers;

// One transfer menu frame: the highlighted line whose ItemCardInfoList the card shows gets its CND line.
void Update(GFxMovieRoot *movie) {
    GFxValue card, info;
    if (!movie->GetVariable(&card, (g_base + ".ItemCard_mc").c_str()) || !Get(card, "InfoObj", &info) ||
        !info.IsArray())
        return;
    for (const char *path : LISTS) {
        GFxValue entry, list, stamp;
        if (!movie->GetVariable(&entry, (g_base + "." + path + ".selectedEntry").c_str()) || !entry.IsObject() ||
            !Get(entry, "ItemCardInfoList", &list) || list.data.obj != info.data.obj || !Get(entry, STAMP, &stamp))
            continue;
        ShowLine(movie, card, float(Num(stamp)), false);
        return;
    }
}

class FrameHandler : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override { Update(args->movie->movieRoot); }
};

}  // namespace

void InstallTransfer() {
    g_containerLine = *reinterpret_cast<LineFn *>(CONTAINER_LINE_SLOT.GetUIntPtr());
    g_barterLine = *reinterpret_cast<LineFn *>(BARTER_LINE_SLOT.GetUIntPtr());
    SafeWrite64(CONTAINER_LINE_SLOT.GetUIntPtr(), UInt64(ContainerLine));
    SafeWrite64(BARTER_LINE_SLOT.GetUIntPtr(), UInt64(BarterLine));
    _MESSAGE("hooked the transfer and barter menus' lines");
}

void HookTransferMenu(const char *name) {
    BSFixedString menuName(name);
    IMenu *menu = (*g_ui)->GetMenu(menuName);
    if (!menu || !menu->movie || !menu->movie->movieRoot) return;
    GFxMovieRoot *movie = menu->movie->movieRoot;
    GFxValue code, root, card, flag(true), args[2];
    g_base.clear();
    // The transfer menu's root holds only FilterHolder_mc (played: its members were f4se and FilterHolder_mc).
    for (const char *base : {"root.FilterHolder_mc.Menu_mc", "root.FilterHolder_mc", "root.Menu_mc", "root"})
        if (movie->GetVariable(&code, (std::string(base) + ".BGSCodeObj").c_str()) && code.IsObject() &&
            movie->GetVariable(&card, (std::string(base) + ".ItemCard_mc").c_str()) && card.IsObject() &&
            movie->GetVariable(&root, base)) {
            g_base = base;
            break;
        }
    if (g_base.empty()) {
        _MESSAGE("%s opened, but no known path has its item card; root.FilterHolder_mc's members:", name);
        if (movie->GetVariable(&root, "root.FilterHolder_mc")) root.VisitMembers(&g_logMembers);
        return;
    }
    if (code.HasMember(HOOKED)) return;
    movie->CreateString(&args[0], "enterFrame");
    CreateFunction<FrameHandler>(&args[1], movie);
    root.Invoke("addEventListener", nullptr, args, 2);
    code.SetMember(HOOKED, &flag);
    _MESSAGE("hooked %s at %s", name, g_base.c_str());
}

}  // namespace condition
