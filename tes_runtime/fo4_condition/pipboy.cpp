// F3NV's Pip-Boy: a CND line on the inventory item card for items that wear, a REPAIR (G) button
// hint, the AMMO (V) hint and its keys (ammo.cpp), and the highlighted item for F3NV_Condition.PipboySelection
// (docs/fork/fo4_condition.md#pipboy).
//
// When the Pip-Boy menu opens (a menu open event, then a UI task), its movie gets a native enterFrame listener.
// The menu's instance (root.Menu_mc) keeps its current page in CurrentPage. The inventory page
// (pipboy_invpage.swf) has List_mc (its selectedEntry: formID, nodeID, equipState) and ItemCard_mc, which
// draws the line objects in its InfoObj array ({text, value, showAsPercent}) when it is dirty. Every frame
// while the Pip-Boy is open this file finds the highlighted line's stack (the game's own StackID for the line,
// LineStack) and its health. Once per menu it loads our own movie into the menu instance (LoadOverlay), which
// asks PipboyCardLines for the card's lines each frame and keeps them in InfoObj, and draws the open repair or
// ammo list from PipboyList. This file keeps the lists' state and keys: G or the REPAIR hint opens the repair
// list (below); confirming it sends the F4SE external event FNVConditionRepair to Papyrus.
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

// Ask Papyrus to repair the highlighted item: F3NV_ConditionPlayer listens for the F4SE external event.
void SendRepair(GFxMovieRoot *movie, const char *why) {
    _MESSAGE("Pip-Boy repair (%s): %s %s", why, REPAIR_EVENT, SendExternal(movie, REPAIR_EVENT) ? "sent" : "not sent");
}

// ---- The repair list ----
// FNV's "repair with" menu, drawn by our Pip-Boy movie from RepairView while it is open: the Repair skill, the
// spares (name, CND) with the chosen one highlighted, and the item's CND before and after. The page's own modal
// (ModalFadeRect_mc, which its pop-ups use) blocks the page's actions and List_mc's input meanwhile.
// Keys (Flash key codes): Up or W, Down or S move; Enter or E repairs; Esc, Tab or G cancels.

struct RepairListState {
    bool open = false;
    std::vector<Spare> spares;
    SInt32 chosen = -1;
    UInt32 item = 0;
    SInt32 stack = -1;
    float health = 1.0f, skill = 0.0f;
    bool service = false;  // a vendor's offer (FNV's repair services) instead of the spares
    std::string vendor;
    Offer offer{};
    UInt32 caps = 0;
} g_list;  // UI thread only
Repair g_pending;
bool g_hasPending = false;  // under g_lock
Row g_say;                  // why nothing opened, shown on the card until the selection changes (UI thread only)
bool g_movieThere = false;  // our movie called PipboyCardLines in this Pip-Boy menu (UI thread only)
UInt32 g_selectedForm = 0;  // the highlighted entry's form (UI thread only)
enum : int { KEY_TAB = 9, KEY_ENTER = 13, KEY_ESC = 27, KEY_UP = 38, KEY_DOWN = 40, KEY_E = 69, KEY_G = 71,
             KEY_S = 83, KEY_W = 87 };

std::string Percent(float health) {
    return std::to_string(int(std::floor(health * 100.0f + 0.5f))) + "%";
}

}  // namespace

bool CurrentPage(GFxMovieRoot *movie, GFxValue *page) {
    return movie->GetVariable(page, (g_base + ".CurrentPage").c_str()) && page->IsObject() &&
           page->HasMember("ItemCard_mc");
}

namespace {

// The vendor's offer: its skill, the condition before and after, the price, the caps held.
void OfferView(ListView *view) {
    view->heading = {"REPAIR SERVICES", g_list.vendor};
    view->notes = {{"VENDOR REPAIR", std::to_string(int(g_list.skill))},
                   {"CND", Percent(g_list.health) + " > " + Percent(g_list.offer.health)},
                   {"COST", std::to_string(g_list.offer.cost) + " caps"},
                   {"YOUR CAPS", std::to_string(g_list.caps)}};
    view->keys = {g_list.caps >= g_list.offer.cost ? "ENTER) REPAIR" : "NOT ENOUGH CAPS", "ESC) CANCEL"};
}

// The open repair list, or the vendor's offer, as a view for our movie.
void RepairView(ListView *view) {
    if (g_list.service) {
        OfferView(view);
        return;
    }
    view->heading = {"REPAIR SKILL", std::to_string(int(g_list.skill))};
    for (const Spare &spare : g_list.spares) {
        const char *name = spare.form->GetFullName();
        std::string text = name ? name : "?";
        if (spare.count > 1) text += " (" + std::to_string(spare.count) + ")";
        view->rows.push_back({text, Percent(spare.health)});
    }
    view->chosen = g_list.chosen;
    float result = RepairResult(g_list.health, g_list.spares[g_list.chosen].health, g_list.skill);
    view->notes = {{"CND", Percent(g_list.health) + " > " + Percent(result)}};
    view->keys = {"ENTER) REPAIR", "ESC) CANCEL"};
}

}  // namespace

// Turn `page`'s modal (its fade, which blocks the page's actions, and its list's input) on or off. Our movie draws
// the list above the page, fade included.
void SetModal(GFxValue &page, bool on) {
    GFxValue rect, list, shown(on), blocked(on);
    if (Get(page, "ModalFadeRect_mc", &rect)) rect.SetMember("visible", &shown);
    if (Get(page, "List_mc", &list)) list.SetMember("disableInput", &blocked);
}

void SayOnCard(const char *why, const char *label) {
    g_say = {label, why};
}

bool PipboyMovieThere() {
    static bool logged = false;
    if (!g_movieThere && !logged) _MESSAGE("Pip-Boy: no list without our movie (%s)", "F3NV_Pipboy.swf");
    logged = logged || !g_movieThere;
    return g_movieThere;
}

bool SendExternal(GFxMovieRoot *movie, const char *event) {
    GFxValue f4se, name;
    if (!movie->GetVariable(&f4se, "root.f4se") || !f4se.IsObject()) return false;
    movie->CreateString(&name, event);
    return f4se.Invoke("SendExternalEvent", nullptr, &name, 1);
}

bool MakeHint(GFxMovieRoot *movie, const char *label, const char *key, MakeClick click, GFxValue *hint) {
    GFxValue args[6];
    const char *texts[4] = {label, key, "", ""};
    for (int i = 0; i < 4; i++) movie->CreateString(&args[i], texts[i]);
    args[4] = GFxValue(UInt32(1));
    click(movie, &args[5]);
    movie->CreateObject(hint, HINT_CLASS, args, 6);
    if (!hint->IsObject()) _MESSAGE("could not create the Pip-Boy %s hint (%s)", label, HINT_CLASS);
    return hint->IsObject();
}

namespace {

// Open the vendor's offer for the highlighted item (stack chosen in g_list); on one the vendor cannot improve,
// say so on the card.
void OpenOffer(GFxMovieRoot *movie, GFxValue &page) {
    g_list.offer = VendorOffer(g_list.health, ItemValue(LookupFormByID(g_list.item)), g_list.skill);
    g_list.caps = Caps(*g_player);
    _MESSAGE("vendor repair offer for %08X stack %d: %.3f for %u caps (held %u)", g_list.item, g_list.stack,
             g_list.offer.health, g_list.offer.cost, g_list.caps);
    if (!g_list.offer.cost) {
        SayOnCard(g_list.health >= 0.995f ? "Not needed" : "Beyond the vendor's skill");
        return;
    }
    g_list.open = true;
    SetModal(page, true);
}

// Open the repair list for the highlighted item, on its default spare; on a whole item or with no spare, say so
// on the card. While a vendor offers repair services, open its offer instead.
void OpenList(GFxMovieRoot *movie) {
    GFxValue page;
    if (!g_wears || !CurrentPage(movie, &page) || !PipboyMovieThere()) return;
    Selection selected;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        selected = g_selection;
    }
    Actor *player = *g_player;
    g_list.item = selected.form;
    g_list.stack = selected.stack;
    g_list.health = g_health;
    g_list.service = Vendor(&g_list.vendor, &g_list.skill);
    if (g_list.service) {
        OpenOffer(movie, page);
        return;
    }
    g_list.spares = Spares(player, LookupFormByID(selected.form), selected.stack);
    g_list.skill = RepairSkill(player);
    _MESSAGE("Pip-Boy repair list for %08X stack %d: %u spares", selected.form, selected.stack,
             UInt32(g_list.spares.size()));
    bool whole = g_list.health >= 0.995f;
    if (whole || g_list.spares.empty()) {
        SayOnCard(whole ? "Not needed" : "No spare");
        return;
    }
    g_list.chosen = DefaultSpare(g_list.spares, g_list.health, g_list.skill);
    g_list.open = true;
    SetModal(page, true);
}

// Close the repair list, repairing with the chosen spare when `repair`; the game redraws the item card.
void CloseList(GFxMovieRoot *movie, bool repair) {
    GFxValue page;
    if (repair) {
        std::lock_guard<std::mutex> hold(g_lock);
        g_pending = g_list.service ? Repair{g_list.item, g_list.stack, 0, -1, g_list.offer.cost, g_list.offer.health}
                                   : Repair{g_list.item, g_list.stack, g_list.spares[g_list.chosen].form->formID,
                                            g_list.spares[g_list.chosen].stack};
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
        if (!g_list.open && !AmmoListOpen()) OpenList(args->movie->movieRoot);
    }
};

// Whether key event `event` was typed into a text box (FallUI's list search), which our keys leave alone.
bool Typed(GFxValue &event) {
    GFxValue target, type;
    return Get(event, "target", &target) && Get(target, "type", &type) && type.IsString() &&
           !strcmp(type.GetString(), "input");
}

// The Pip-Boy's own key events: G opens the repair list on an item that wears, V the ammo list (ammo.cpp); the
// open list's keys. Keys typed into a text box are left alone.
class KeyHandler : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        GFxValue code;
        if (args->numArgs < 1 || !Get(args->args[0], "keyCode", &code) || Typed(args->args[0])) return;
        GFxMovieRoot *movie = args->movie->movieRoot;
        int key = int(Num(code));
        if (!g_list.open && AmmoKey(movie, key)) return;
        if (!g_list.open) {
            if (key == KEY_G) OpenList(movie);
            return;
        }
        SInt32 last = SInt32(g_list.spares.size()) - 1;
        bool vertical = key == KEY_UP || key == KEY_W || key == KEY_DOWN || key == KEY_S;
        if (vertical && !g_list.service) {
            g_list.chosen = std::max<SInt32>(0, std::min<SInt32>(last, g_list.chosen + (key == KEY_UP || key == KEY_W ? -1 : 1)));
        } else if ((key == KEY_ENTER || key == KEY_E) && (!g_list.service || g_list.caps >= g_list.offer.cost)) {
            CloseList(movie, true);
        } else if (key == KEY_ESC || key == KEY_TAB || key == KEY_G) {
            CloseList(movie, false);
        }
    }
};

// Give inventory page `page` the REPAIR and AMMO hints, once per page, on keyboard and mouse only.
void AddHint(GFxMovieRoot *movie, GFxValue &root, GFxValue &page) {
    if (page.data.obj == g_hintPage) return;
    GFxValue hints, bar, hint, ammo, platform;
    if (!Get(page, "buttonHintDataV", &hints) || !Get(root, "ButtonHintBar_mc", &bar)) return;
    g_hintPage = page.data.obj;
    if (Get(root, "uiPlatform", &platform) && Num(platform) != KEYBOARD_MOUSE) return;
    MakeClick click = [](GFxMovieRoot *m, GFxValue *out) { CreateFunction<HintClick>(out, m); };
    if (!MakeHint(movie, HINT, HINT_KEY, click, &hint)) return;
    hints.Invoke("push", nullptr, &hint, 1);
    if (MakeAmmoHint(movie, &ammo)) hints.Invoke("push", nullptr, &ammo, 1);
    bar.Invoke("SetButtonHintData", nullptr, &hints, 1);
    _MESSAGE("added the Pip-Boy %s and ammo hints", HINT);
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
    UpdatePages(movie, g_base);
    if (!movie->GetVariable(&root, g_base.c_str()) || !movie->GetVariable(&page, (g_base + ".CurrentPage").c_str()) ||
        !page.IsObject() || !page.HasMember("ItemCard_mc")) {
        std::lock_guard<std::mutex> hold(g_lock);
        g_selection = Selection();
        g_lastKey.clear();
        g_list.open = false;
        ForgetAmmoList();
        return;
    }
    AddHint(movie, root, page);
    if (g_list.open || AmmoListOpen()) return;
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
            LogMembers(entry);
        }
    }
    g_selectedForm = formID;
    if (key != g_lastKey || force) {
        if (key != g_lastKey) g_say = Row();
        g_lastKey = key;
        g_wears = !key.empty() && Resolve(formID, UInt32(Num(node)));
        if (g_wears)
            _MESSAGE("Pip-Boy line %u of %08X: stack %d at %.3f", UInt32(Num(node)), formID, g_selection.stack,
                     g_health);
    }
    if (force && formID) FixEquipMarks(list, formID);
}

class FrameHandler : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override { Update(args->movie->movieRoot); }
};

// A {text, value} object of `row` into `out`.
void RowObject(GFxMovieRoot *movie, const Row &row, GFxValue *out) {
    GFxValue text, value;
    movie->CreateObject(out);
    movie->CreateString(&text, row.text.c_str());
    movie->CreateString(&value, row.value.c_str());
    out->SetMember("text", &text);
    out->SetMember("value", &value);
}

// `rows`' objects pushed onto array `out`.
void PushRows(GFxMovieRoot *movie, const std::vector<Row> &rows, GFxValue *out) {
    for (const Row &row : rows) {
        GFxValue line;
        RowObject(movie, row, &line);
        out->PushBack(&line);
    }
}

// PipboyCardLines(): the lines for the highlighted item's card, [{text, value, showAsPercent}], for our Pip-Boy
// movie to keep there: the CND line of an item that wears, why a list did not open, then other mods' lines
// (card.cpp). Null while a list of ours is open or off the inventory page.
class CardLinesNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        GFxMovieRoot *movie = args->movie->movieRoot;
        GFxValue page;
        g_movieThere = true;
        args->result->SetNull();
        if (g_list.open || AmmoListOpen() || !CurrentPage(movie, &page)) return;
        movie->CreateArray(args->result);
        if (g_wears) {
            GFxValue line, text, value(std::floor(g_health * 100.0 + 0.5)), percent(true);
            movie->CreateObject(&line);
            movie->CreateString(&text, LINE);
            line.SetMember("text", &text);
            line.SetMember("value", &value);
            line.SetMember("showAsPercent", &percent);
            args->result->PushBack(&line);
        }
        std::vector<Row> rows;
        if (!g_say.text.empty()) rows.push_back(g_say);
        if (g_selectedForm) CardLinesOf(g_selectedForm, &rows);
        PushRows(movie, rows, args->result);
    }
};

// PipboyList(): the open repair or ammo list for our movie to draw, {heading, rows, chosen, notes, keys} (heading
// and keys {text, value}; rows and notes arrays of them; chosen the highlighted row, -1 for none); null when none.
class ListNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        GFxMovieRoot *movie = args->movie->movieRoot;
        ListView view;
        args->result->SetNull();
        if (g_list.open) RepairView(&view);
        else if (!AmmoView(&view)) return;
        GFxValue heading, rows, chosen(view.chosen), notes, keys;
        RowObject(movie, view.heading, &heading);
        movie->CreateArray(&rows);
        PushRows(movie, view.rows, &rows);
        movie->CreateArray(&notes);
        PushRows(movie, view.notes, &notes);
        RowObject(movie, view.keys, &keys);
        movie->CreateObject(args->result);
        args->result->SetMember("heading", &heading);
        args->result->SetMember("rows", &rows);
        args->result->SetMember("chosen", &chosen);
        args->result->SetMember("notes", &notes);
        args->result->SetMember("keys", &keys);
    }
};

// Our own movie (Interface/F3NV_Pipboy.swf, fo4_import/pipboy_overlay) loaded into the menu instance `menu` with a
// Loader, as F4SE's UI.Load does; it draws PipboyCardLines on the item card (docs/fork/swf_framework.md#pipboy).
const char *OVERLAY = "F3NV_Pipboy.swf";

void LoadOverlay(GFxMovieRoot *movie, GFxValue &menu) {
    GFxValue loader, path, args[2];
    movie->CreateObject(&loader, "flash.display.Loader");
    movie->CreateString(&path, OVERLAY);
    movie->CreateObject(&args[0], "flash.net.URLRequest", &path, 1);
    args[1].SetNull();
    bool added = loader.IsObject() && menu.Invoke("addChild", nullptr, &loader, 1);
    bool loading = added && loader.Invoke("load", nullptr, args, 2);
    _MESSAGE("Pip-Boy: %s %s", OVERLAY, loading ? "loading" : added ? "not loaded" : "not added");
}

// A display object joined the menu: when it is a newly loaded STAT page, give it our tabs at once, before the
// menu's header reads its tab names (from the next frame on, a page loaded on one of ours showed none of them).
class AddedHandler : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        GFxValue target;
        if (args->numArgs > 0 && Get(args->args[0], "target", &target) && target.IsObject() &&
            target.HasMember("SPECIALTab_mc"))
            UpdatePages(args->movie->movieRoot, g_base);
    }
};

// The open Pip-Boy menu's movie: listen for its frames, once per menu (a flag on its BGSCodeObj).
class HookTask : public ITaskDelegate {
public:
    void Run() override {
        BSFixedString name(MENU);
        IMenu *menu = (*g_ui)->GetMenu(name);
        GFxValue root, code, flag(true);
        if (!menu || !menu->movie || !menu->movie->movieRoot) {
            _MESSAGE("Pip-Boy opened, but its menu has no movie");
            return;
        }
        GFxMovieRoot *movie = menu->movie->movieRoot;
        if (!FindMenu(movie, {"root", "root.Menu_mc"}, nullptr, &g_base, &root, &code)) {
            _MESSAGE("Pip-Boy opened, but neither root nor root.Menu_mc has a BGSCodeObj; root's members:");
            if (movie->GetVariable(&root, "root")) LogMembers(root);
            return;
        }
        if (code.HasMember(HOOKED)) return;
        Listen<FrameHandler>(movie, root, "enterFrame");
        bool listening = Listen<KeyHandler>(movie, root, "keyUp");
        Listen<AddedHandler>(movie, root, "added");
        _MESSAGE("Pip-Boy key listener %s", listening ? "added" : "not added");
        code.SetMember(HOOKED, &flag);
        g_movieThere = false;
        LoadOverlay(movie, root);
        g_hintPage = nullptr;
        ResetPages();
        g_list.open = false;
        ForgetAmmoList();
        g_lastKey.clear();
        GFxValue f4se;
        _MESSAGE("hooked the Pip-Boy menu at %s (root.f4se: %s)", g_base.c_str(),
                 movie->GetVariable(&f4se, "root.f4se") && f4se.IsObject() ? "yes" : "no");
    }
};

// Menu open and close events: hook the Pip-Boy on the UI thread as it opens.
// The transfer or barter menu just opened: hook it on the UI thread (transfer.cpp).
class TransferHookTask : public ITaskDelegate {
public:
    explicit TransferHookTask(const char *name) : m_name(name) {}
    void Run() override { HookTransferMenu(m_name); }

private:
    const char *m_name;
};

const char *TRANSFER_MENUS[] = {"ContainerMenu", "BarterMenu"};

// A menu opened: give the HUD Hardcore's needs on the UI thread, if it has none yet (hardcore.cpp).
class HudHookTask : public ITaskDelegate {
public:
    void Run() override { HookHud(); }
};

class OpenSink : public BSTEventSink<MenuOpenCloseEvent> {
public:
    EventResult ReceiveEvent(MenuOpenCloseEvent *evn, void *) override {
        if (evn && !evn->isOpen && !strcmp(evn->menuName.c_str(), MENU)) SetVendor(nullptr);
        const char *name = evn && evn->isOpen ? evn->menuName.c_str() : nullptr;
        if (!name || !g_tasks) return kEvent_Continue;
        if (!strcmp(name, MENU)) g_tasks->AddUITask(new HookTask);
        g_tasks->AddUITask(new HudHookTask);
        for (const char *transfer : TRANSFER_MENUS)
            if (!strcmp(name, transfer)) g_tasks->AddUITask(new TransferHookTask(transfer));
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

SInt32 PipboyLineStack(UInt32 formID, UInt32 nodeID) {
    return LineStack(formID, nodeID);
}

bool RepairListOpen() {
    return g_list.open;
}

void RegisterPipboyMenu(GFxMovieRoot *movie, GFxValue *plugin) {
    RegisterFunction<CardLinesNative>(plugin, movie, "PipboyCardLines");
    RegisterFunction<ListNative>(plugin, movie, "PipboyList");
}

void ShowLine(GFxMovieRoot *movie, GFxValue &card, float health, bool force) {
    GFxValue info, text, value;
    if (!Get(card, "InfoObj", &info) || !info.IsArray()) return;
    double percent = std::floor(health * 100.0 + 0.5);
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
        if (!logged) _MESSAGE("added the %s line to an item card", LINE);
        logged = true;
    }
    value.SetNumber(percent);
    line.SetMember("value", &value);
    card.Invoke("onDataChange", nullptr, nullptr, 0);
}

}  // namespace condition
