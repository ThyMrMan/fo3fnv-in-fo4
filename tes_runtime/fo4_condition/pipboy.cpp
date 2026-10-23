// FalloutCondition's Pip-Boy: a CND line on the inventory item card for items that wear, a REPAIR (G) button
// hint, and the highlighted item for TES4_Condition.PipboySelection (docs/fork/fo4_condition.md#pipboy).
//
// When the Pip-Boy menu opens (a menu open event, then a UI task), its movie gets a native enterFrame listener.
// The menu's instance (root.Menu_mc) keeps its current page in CurrentPage. The inventory page
// (pipboy_invpage.swf) has List_mc (its selectedEntry: formID, nodeID, equipState) and ItemCard_mc, which
// draws the line objects in its InfoObj array ({text, value, showAsPercent}) when it is dirty. Every frame
// while the Pip-Boy is open this file finds the highlighted line's stack (the game's own StackID for the line,
// LineStack) and keeps a CND line in InfoObj, redrawing the card when it adds or changes it. The game refills
// InfoObj on every selection change, which drops the line; the next frame puts it back. G or the REPAIR hint
// opens the repair list (below); confirming it sends the F4SE external event FNVConditionRepair to Papyrus.
#include "condition.h"

#include "f4se/GameEvents.h"
#include "f4se/GameMenus.h"
#include "f4se/GameThreads.h"
#include "f4se/PluginAPI.h"
#include "f4se/ScaleformCallbacks.h"
#include "f4se/ScaleformMovie.h"
#include "f4se/ScaleformValue.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <string>

namespace condition {

namespace {

// The Pip-Boy's own keys there: Enter, X, R, Q, C, Tab, Z, and T (Grid View); G is free. No gamepad button is.
const char *MENU = "PipboyMenu", *LINE = "CND", *HINT = "REPAIR", *HINT_KEY = "G", *HOOKED = "fnvConditionHooked";
const char *HINT_CLASS = "Shared.AS3.BSButtonHintData", *REPAIR_EVENT = "FNVConditionRepair";
const UInt32 KEYBOARD_MOUSE = 0;  // PlatformChangeEvent.PLATFORM_PC_KB_MOUSE
F4SETaskInterface *g_tasks = nullptr;
std::atomic<bool> g_refresh{false};
std::string g_lastKey;           // The highlighted entry last resolved (UI thread only).
float g_health = 1.0f;           // Its health, when it wears.
bool g_wears = false;            // Whether it does.
const void *g_hintPage = nullptr;  // The inventory page given the REPAIR hint (identity only).
bool g_loggedEntry = false;
std::string g_base = "root";       // The path of the PipboyMenu instance (root, or root.Menu_mc).

double Num(const GFxValue &v) {
    switch (v.GetType()) {
        case GFxValue::kType_Int: return v.GetInt();
        case GFxValue::kType_UInt: return v.GetUInt();
        case GFxValue::kType_Number: return v.GetNumber();
        case GFxValue::kType_Bool: return v.GetBool() ? 1.0 : 0.0;
        default: return 0.0;
    }
}

bool Get(GFxValue &obj, const char *name, GFxValue *out) {
    return obj.IsObject() && obj.GetMember(name, out);
}

// Log an object's members by name and GFx type (the first highlighted entry; the root when the hook fails).
class LogMembers : public GFxValue::ObjectInterface::ObjVisitor {
public:
    void Visit(const char *member, GFxValue *value) override {
        _MESSAGE("  member %s (type %d)", member, value->GetType());
    }
};

// The game's Pip-Boy inventory lines (Fallout4.exe 1.11.240; docs/fork/fo4_condition.md#pipboy-lines): the
// PipboyDataManager pointer's global, its PipboyInventoryData, and that one's map of form ID -> its lines.
RelocPtr<UInt8 *> g_pipboyData(0x30E8AF8);
RelocAddr<void *> g_inventoryDataVtable(0x2544750);  // PipboyInventoryData's, set by its constructor
const UInt32 INVENTORY_DATA = 0x358, FORM_LINES = 0xF8;

// A node of a form's line list (circular, with a sentinel): its record starts with the line's PipboyObject.
struct LineNode {
    LineNode *next, *prev;
    PipboyObject **record;
};

// One slot of the form ID map (F4SE's tHashSet layout: free while `next` is null).
struct FormLines {
    UInt32 formID, pad;
    LineNode **list;
    FormLines *next;
};

// The first stack index the game lists on Pip-Boy line `nodeID` of form `formID` (its StackID), or -1.
SInt32 LineStack(UInt32 formID, UInt32 nodeID) {
    UInt8 *manager = *g_pipboyData;
    if (!manager || *reinterpret_cast<uintptr_t *>(manager + INVENTORY_DATA) != g_inventoryDataVtable.GetUIntPtr())
        return -1;
    UInt8 *map = manager + INVENTORY_DATA + FORM_LINES;
    UInt32 size = *reinterpret_cast<UInt32 *>(map + 4);
    FormLines *slots = *reinterpret_cast<FormLines **>(map + 0x20);
    for (UInt32 i = 0; slots && i < size; i++) {
        FormLines &slot = slots[i];
        if (!slot.next || slot.formID != formID || !slot.list || !*slot.list) continue;
        LineNode *head = *slot.list;
        for (LineNode *n = head->next; n && n != head; n = n->next) {
            PipboyObject *line = n->record ? *n->record : nullptr;
            if (!line || line->unk08 != nodeID) continue;
            BSFixedString key("StackID");
            PipboyObject::PipboyTableItem *item = line->table.Find(&key);
            UInt8 *stacks = item ? reinterpret_cast<UInt8 *>(item->value) : nullptr;
            UInt32 count = stacks ? *reinterpret_cast<UInt32 *>(stacks + 0x28) : 0;
            PipboyValue **values = stacks ? *reinterpret_cast<PipboyValue ***>(stacks + 0x18) : nullptr;
            if (!count || !values || !values[0]) return -1;
            return SInt32(static_cast<PipboyPrimitiveValue<UInt32> *>(values[0])->value);
        }
    }
    return -1;
}

// The player's stack of form `formID` (one that wears) Pip-Boy line `nodeID` shows: the game's own stack index
// for the line (LineStack), else, logged once, the equipped stack, else the first. Sets g_selection and
// g_health; false when the form does not wear or is not held.
bool Resolve(UInt32 formID, UInt32 nodeID) {
    PlayerCharacter *player = *g_player;
    SInt32 stack = LineStack(formID, nodeID);
    static bool logged = false;
    if (stack < 0 && !logged) _MESSAGE("no StackID for Pip-Boy line %u of %08X; using the equipped or first stack",
                                       nodeID, formID);
    logged = logged || stack < 0;
    std::lock_guard<std::mutex> hold(g_lock);
    g_selection = Selection();
    if (!player || !g_tracked.count(formID)) return false;
    TESForm *form = LookupFormByID(formID);
    BGSInventoryItem::Stack *chosen = FindStack(player, form, stack);
    if (!chosen) return false;
    g_selection.form = formID;
    g_selection.stack = stack;
    float health = HealthOf(chosen);
    g_health = health < 0.0f ? 1.0f : health;
    return true;
}

// Ask Papyrus to repair the highlighted item: TES4_ConditionPlayer listens for the F4SE external event.
void SendRepair(GFxMovieRoot *movie, const char *why) {
    GFxValue f4se, name;
    bool sent = movie->GetVariable(&f4se, "root.f4se") && f4se.IsObject();
    if (sent) {
        movie->CreateString(&name, REPAIR_EVENT);
        sent = f4se.Invoke("SendExternalEvent", nullptr, &name, 1);
    }
    _MESSAGE("Pip-Boy repair (%s): %s %s", why, REPAIR_EVENT, sent ? "sent" : "not sent");
}

// ---- The repair list ----
// FNV's "repair with" menu, drawn on the inventory page's item card while it is open: the Repair skill, the
// spares (name, CND) with the chosen one marked, and the item's CND before and after. The page's own modal
// (ModalFadeRect_mc, which its pop-ups use) blocks the page's actions and List_mc's input meanwhile.
// Keys (Flash key codes): Up or W, Down or S move; Enter or E repairs; Esc, Tab or G cancels.

struct RepairListState {
    bool open = false;
    std::vector<Spare> spares;
    SInt32 chosen = -1;
    UInt32 item = 0;
    SInt32 stack = -1;
    float health = 1.0f, skill = 0.0f;
} g_list;  // UI thread only
Repair g_pending;
bool g_hasPending = false;  // under g_lock
const SInt32 LIST_ROWS = 6;
SInt32 g_cardIndex = -1;  // the item card's place among the page's children while lifted
enum : int { KEY_TAB = 9, KEY_ENTER = 13, KEY_ESC = 27, KEY_UP = 38, KEY_DOWN = 40, KEY_E = 69, KEY_G = 71,
             KEY_S = 83, KEY_W = 87 };

bool CurrentPage(GFxMovieRoot *movie, GFxValue *page) {
    return movie->GetVariable(page, (g_base + ".CurrentPage").c_str()) && page->IsObject() &&
           page->HasMember("ItemCard_mc");
}

std::string Percent(float health) {
    return std::to_string(int(std::floor(health * 100.0f + 0.5f))) + "%";
}

void AddLine(GFxMovieRoot *movie, GFxValue &lines, const std::string &text, const std::string &value) {
    GFxValue line, label, shown;
    movie->CreateObject(&line);
    movie->CreateString(&label, text.c_str());
    movie->CreateString(&shown, value.c_str());
    line.SetMember("text", &label);
    line.SetMember("value", &shown);
    lines.PushBack(&line);
}

// Draw the repair list on `page`'s item card.
void DrawList(GFxMovieRoot *movie, GFxValue &page) {
    GFxValue card, lines;
    if (!Get(page, "ItemCard_mc", &card)) return;
    movie->CreateArray(&lines);
    AddLine(movie, lines, "REPAIR SKILL", std::to_string(int(g_list.skill)));
    SInt32 size = SInt32(g_list.spares.size());
    SInt32 first = std::max<SInt32>(0, std::min<SInt32>(g_list.chosen - LIST_ROWS / 2, size - LIST_ROWS));
    for (SInt32 i = first; i < size && i < first + LIST_ROWS; i++) {
        const Spare &spare = g_list.spares[i];
        const char *name = spare.form->GetFullName();
        std::string text = std::string(i == g_list.chosen ? "> " : "  ") + (name ? name : "?");
        if (spare.count > 1) text += " (" + std::to_string(spare.count) + ")";
        AddLine(movie, lines, text, Percent(spare.health));
    }
    float result = RepairResult(g_list.health, g_list.spares[g_list.chosen].health, g_list.skill);
    AddLine(movie, lines, "CND", Percent(g_list.health) + " > " + Percent(result));
    AddLine(movie, lines, "ENTER) REPAIR", "ESC) CANCEL");
    card.SetMember("InfoObj", &lines);
    card.Invoke("onDataChange", nullptr, nullptr, 0);
}

// Turn `page`'s modal (its fade, which blocks the page's actions, and its list's input) on or off. While on,
// the item card is lifted above the fade, as the page's own pop-ups are, so the list reads as the pop-up; off,
// it goes back to its place (played 2026-10-23: under the fade the list looked like a pop-up that never came).
void SetModal(GFxValue &page, bool on) {
    GFxValue rect, list, shown(on), blocked(on), at, top, args[2];  // args[0]: the card, read in place (no copy)
    if (Get(page, "ModalFadeRect_mc", &rect)) rect.SetMember("visible", &shown);
    if (Get(page, "List_mc", &list)) list.SetMember("disableInput", &blocked);
    if (!Get(page, "ItemCard_mc", &args[0])) return;
    if (on && page.Invoke("getChildIndex", &at, &args[0], 1) && Get(page, "numChildren", &top)) {
        g_cardIndex = SInt32(Num(at));
        args[1].SetInt(SInt32(Num(top)) - 1);
    } else if (!on && g_cardIndex >= 0) {
        args[1].SetInt(g_cardIndex);
        g_cardIndex = -1;
    } else {
        return;
    }
    page.Invoke("setChildIndex", nullptr, args, 2);
}

// Open the repair list for the highlighted item, on its default spare; on a whole item or with no spare, say so
// on the card.
void OpenList(GFxMovieRoot *movie) {
    GFxValue page;
    if (!g_wears || !CurrentPage(movie, &page)) return;
    Selection selected;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        selected = g_selection;
    }
    Actor *player = *g_player;
    g_list.spares = Spares(player, LookupFormByID(selected.form), selected.stack);
    g_list.item = selected.form;
    g_list.stack = selected.stack;
    g_list.health = g_health;
    g_list.skill = RepairSkill(player);
    _MESSAGE("Pip-Boy repair list for %08X stack %d: %u spares", selected.form, selected.stack,
             UInt32(g_list.spares.size()));
    GFxValue card, info;
    bool whole = g_list.health >= 0.995f;
    if (whole || g_list.spares.empty()) {
        if (Get(page, "ItemCard_mc", &card) && Get(card, "InfoObj", &info) && info.IsArray()) {
            AddLine(movie, info, "REPAIR", whole ? "Not needed" : "No spare");
            card.Invoke("onDataChange", nullptr, nullptr, 0);
        }
        return;
    }
    g_list.chosen = DefaultSpare(g_list.spares, g_list.health, g_list.skill);
    g_list.open = true;
    SetModal(page, true);
    DrawList(movie, page);
}

// Close the repair list, repairing with the chosen spare when `repair`; the game redraws the item card.
void CloseList(GFxMovieRoot *movie, bool repair) {
    GFxValue page;
    if (repair) {
        const Spare &spare = g_list.spares[g_list.chosen];
        std::lock_guard<std::mutex> hold(g_lock);
        g_pending = {g_list.item, g_list.stack, spare.form->formID, spare.stack};
        g_hasPending = true;
    }
    g_list.open = false;
    if (CurrentPage(movie, &page)) {
        SetModal(page, false);
        page.Invoke("onListSelectionChange", nullptr, nullptr, 0);
    }
    g_lastKey.clear();
    if (repair) SendRepair(movie, "list");
}

// The REPAIR hint's click: open the repair list.
class HintClick : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        if (!g_list.open) OpenList(args->movie->movieRoot);
    }
};

// The Pip-Boy's own key events: G opens the repair list on an item that wears; the list's keys while it is open.
class KeyHandler : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        GFxValue code, page;
        if (args->numArgs < 1 || !Get(args->args[0], "keyCode", &code)) return;
        GFxMovieRoot *movie = args->movie->movieRoot;
        int key = int(Num(code));
        if (!g_list.open) {
            if (key == KEY_G) OpenList(movie);
            return;
        }
        SInt32 last = SInt32(g_list.spares.size()) - 1;
        if (key == KEY_UP || key == KEY_W || key == KEY_DOWN || key == KEY_S) {
            g_list.chosen = std::max<SInt32>(0, std::min<SInt32>(last, g_list.chosen + (key == KEY_UP || key == KEY_W ? -1 : 1)));
            if (CurrentPage(movie, &page)) DrawList(movie, page);
        } else if (key == KEY_ENTER || key == KEY_E) {
            CloseList(movie, true);
        } else if (key == KEY_ESC || key == KEY_TAB || key == KEY_G) {
            CloseList(movie, false);
        }
    }
};

// Give inventory page `page` the REPAIR hint, once per page, on keyboard and mouse only.
void AddHint(GFxMovieRoot *movie, GFxValue &root, GFxValue &page) {
    if (page.data.obj == g_hintPage) return;
    GFxValue hints, bar, hint, platform, args[6];
    if (!Get(page, "buttonHintDataV", &hints) || !Get(root, "ButtonHintBar_mc", &bar)) return;
    g_hintPage = page.data.obj;
    if (Get(root, "uiPlatform", &platform) && Num(platform) != KEYBOARD_MOUSE) return;
    const char *texts[4] = {HINT, HINT_KEY, "", ""};
    for (int i = 0; i < 4; i++) movie->CreateString(&args[i], texts[i]);
    args[4] = GFxValue(UInt32(1));
    CreateFunction<HintClick>(&args[5], movie);
    movie->CreateObject(&hint, HINT_CLASS, args, 6);
    if (!hint.IsObject()) {
        _MESSAGE("could not create the Pip-Boy %s hint (%s)", HINT, HINT_CLASS);
        return;
    }
    hints.Invoke("push", nullptr, &hint, 1);
    bar.Invoke("SetButtonHintData", nullptr, &hints, 1);
    _MESSAGE("added the Pip-Boy %s hint", HINT);
}

// Keep the CND line in item card `card`'s InfoObj at g_health, redrawing the card when it changes.
void ShowLine(GFxMovieRoot *movie, GFxValue &card, bool force) {
    GFxValue info, text, value;
    if (!Get(card, "InfoObj", &info) || !info.IsArray()) return;
    double percent = std::floor(g_health * 100.0 + 0.5);
    SInt32 at = -1;
    for (UInt32 i = 0, n = info.GetArraySize(); i < n && at < 0; i++) {
        GFxValue item, label;
        if (info.GetElement(i, &item) && Get(item, "text", &label) && label.IsString() &&
            !strcmp(label.GetString(), LINE))
            at = SInt32(i);
    }
    GFxValue line;
    if (at >= 0 && info.GetElement(UInt32(at), &line)) {
        if (Get(line, "value", &value) && Num(value) == percent && !force) return;
    } else {
        GFxValue on(true);
        movie->CreateObject(&line);
        movie->CreateString(&text, LINE);
        line.SetMember("text", &text);
        line.SetMember("showAsPercent", &on);
        info.PushBack(&line);
        static bool logged = false;
        if (!logged) _MESSAGE("added the %s line to the Pip-Boy item card", LINE);
        logged = true;
    }
    value.SetNumber(percent);
    line.SetMember("value", &value);
    card.Invoke("onDataChange", nullptr, nullptr, 0);
}

// Set the equipped mark (equipState) of each of Pip-Boy `list`'s lines of form `formID` from its own stack (its
// StackID), redrawing the list when one changes: the game leaves the marks of two copies of one form as they were
// when the equipped copy changes (played 2026-10-23).
void FixEquipMarks(GFxValue &list, UInt32 formID) {
    GFxValue entries;
    PlayerCharacter *player = *g_player;
    TESForm *form = LookupFormByID(formID);
    if (!player || !form || !Get(list, "entryList", &entries) || !entries.IsArray()) return;
    bool changed = false;
    for (UInt32 i = 0, n = entries.GetArraySize(); i < n; i++) {
        GFxValue item, id, node, state;
        if (!entries.GetElement(i, &item) || !Get(item, "formID", &id) || UInt32(SInt64(Num(id))) != formID ||
            !Get(item, "nodeID", &node))
            continue;
        SInt32 at = LineStack(formID, UInt32(Num(node)));
        BGSInventoryItem::Stack *stack = at < 0 ? nullptr : FindStack(player, form, at);
        if (!stack) continue;
        bool on = (stack->flags & BGSInventoryItem::Stack::kFlagEquipped) != 0;
        if (Get(item, "equipState", &state) && (Num(state) != 0.0) == on) continue;
        GFxValue mark(UInt32(on ? 1 : 0));
        item.SetMember("equipState", &mark);
        changed = true;
    }
    if (changed) {
        list.Invoke("UpdateList", nullptr, nullptr, 0);
        _MESSAGE("fixed the Pip-Boy equipped marks of %08X", formID);
    }
}

// One Pip-Boy frame: on the inventory page, resolve the highlighted entry and keep its CND line.
void Update(GFxMovieRoot *movie) {
    GFxValue root, page, card, list, entry, id, node, equip;
    if (!movie->GetVariable(&root, g_base.c_str()) || !movie->GetVariable(&page, (g_base + ".CurrentPage").c_str()) ||
        !page.IsObject() || !page.HasMember("ItemCard_mc")) {
        std::lock_guard<std::mutex> hold(g_lock);
        g_selection = Selection();
        g_lastKey.clear();
        g_list.open = false;
        return;
    }
    AddHint(movie, root, page);
    if (g_list.open) return;
    if (!Get(page, "ItemCard_mc", &card) || !Get(page, "List_mc", &list)) return;
    bool force = g_refresh.exchange(false);
    std::string key;
    UInt32 formID = 0;
    if (Get(list, "selectedEntry", &entry) && entry.IsObject() && Get(entry, "formID", &id)) {
        formID = UInt32(SInt64(Num(id)));
        Get(entry, "nodeID", &node);
        Get(entry, "equipState", &equip);
        key = std::to_string(formID) + "|" + std::to_string(Num(node)) + "|" + std::to_string(Num(equip));
        if (!g_loggedEntry) {
            g_loggedEntry = true;
            LogMembers log;
            entry.VisitMembers(&log);
        }
    }
    if (key != g_lastKey || force) {
        g_lastKey = key;
        g_wears = !key.empty() && Resolve(formID, UInt32(Num(node)));
        if (g_wears)
            _MESSAGE("Pip-Boy line %u of %08X: stack %d at %.3f", UInt32(Num(node)), formID, g_selection.stack,
                     g_health);
    }
    if (force && formID) FixEquipMarks(list, formID);
    if (g_wears) ShowLine(movie, card, force);
}

class FrameHandler : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override { Update(args->movie->movieRoot); }
};

// The open Pip-Boy menu's movie: listen for its frames, once per menu (a flag on its BGSCodeObj).
class HookTask : public ITaskDelegate {
public:
    void Run() override {
        BSFixedString name(MENU);
        IMenu *menu = (*g_ui)->GetMenu(name);
        GFxValue root, code, flag(true), args[2];
        if (!menu || !menu->movie || !menu->movie->movieRoot) {
            _MESSAGE("Pip-Boy opened, but its menu has no movie");
            return;
        }
        GFxMovieRoot *movie = menu->movie->movieRoot;
        const char *bases[] = {"root", "root.Menu_mc"};
        g_base.clear();
        for (const char *base : bases)
            if (movie->GetVariable(&code, (std::string(base) + ".BGSCodeObj").c_str()) && code.IsObject() &&
                movie->GetVariable(&root, base)) {
                g_base = base;
                break;
            }
        if (g_base.empty()) {
            _MESSAGE("Pip-Boy opened, but neither root nor root.Menu_mc has a BGSCodeObj; root's members:");
            LogMembers log;
            if (movie->GetVariable(&root, "root")) root.VisitMembers(&log);
            return;
        }
        if (code.HasMember(HOOKED)) return;
        movie->CreateString(&args[0], "enterFrame");
        CreateFunction<FrameHandler>(&args[1], movie);
        root.Invoke("addEventListener", nullptr, args, 2);
        GFxValue keys[2];
        movie->CreateString(&keys[0], "keyUp");
        CreateFunction<KeyHandler>(&keys[1], movie);
        bool listening = root.Invoke("addEventListener", nullptr, keys, 2);
        _MESSAGE("Pip-Boy key listener %s", listening ? "added" : "not added");
        code.SetMember(HOOKED, &flag);
        g_hintPage = nullptr;
        g_list.open = false;
        g_lastKey.clear();
        GFxValue f4se;
        _MESSAGE("hooked the Pip-Boy menu at %s (root.f4se: %s)", g_base.c_str(),
                 movie->GetVariable(&f4se, "root.f4se") && f4se.IsObject() ? "yes" : "no");
    }
};

// Menu open and close events: hook the Pip-Boy on the UI thread as it opens.
class OpenSink : public BSTEventSink<MenuOpenCloseEvent> {
public:
    EventResult ReceiveEvent(MenuOpenCloseEvent *evn, void *) override {
        if (evn && evn->isOpen && evn->menuName.c_str() && !strcmp(evn->menuName.c_str(), MENU) && g_tasks)
            g_tasks->AddUITask(new HookTask);
        return kEvent_Continue;
    }
};
OpenSink g_openSink;

}  // namespace

void InstallPipboy(void *tasks) {
    g_tasks = static_cast<F4SETaskInterface *>(tasks);
    bool added = *g_ui && (*g_ui)->menuOpenCloseEventSource.AddEventSink(&g_openSink);
    _MESSAGE("Pip-Boy hook %s", added ? "listening for the menu" : "could not listen for menus");
}

bool TakePipboyRepair(Repair *out) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (!g_hasPending) return false;
    *out = g_pending;
    g_hasPending = false;
    return true;
}

void RefreshPipboy() {
    g_refresh = true;
}

}  // namespace condition
