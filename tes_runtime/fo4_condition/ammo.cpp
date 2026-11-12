// F3NV's ammo list in the Pip-Boy (docs/fork/fo4_condition.md#ammo-list): FNV's choice of ammo for the
// highlighted gun, drawn by our Pip-Boy movie from AmmoView the way the repair list is (pipboy.cpp). V or the AMMO
// hint opens it on a gun of an FNV ammo list: each round of the list with the count carried, the loaded one
// marked. Confirming sends the F4SE external event FNVAmmoSwitch; F3NV_AmmoSwitch takes the choice
// (F3NV_PipboyAmmo.ChosenGun, TakeChoice) and attaches that round's ammo mod (fo4_import/spike/ammo_switch.py).
// Keys (Flash key codes): Up or W, Down or S move; Enter or E loads; Esc, Tab or V cancels.
#include "condition.h"

#include "f4se/GameObjects.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/ScaleformCallbacks.h"

#include <algorithm>
#include <string>
#include <vector>

namespace condition {

namespace {

const char *SCRIPT = "F3NV_PipboyAmmo", *EVENT = "FNVAmmoSwitch", *HINT = "AMMO", *HINT_KEY = "V";
enum : int { KEY_TAB = 9, KEY_ENTER = 13, KEY_ESC = 27, KEY_UP = 38, KEY_DOWN = 40, KEY_E = 69, KEY_S = 83,
             KEY_V = 86, KEY_W = 87 };

// One FNV ammo list (F3NV_AmmoSwitch's arrays): the keyword its guns carry, its first round's index there, its
// rounds and the form IDs of their ammo mods.
struct Group {
    TESForm *list = nullptr;
    SInt32 start = 0;
    std::vector<TESForm *> rounds;
    std::vector<UInt32> mods;
};
std::vector<Group> g_groups;  // under g_lock
UInt32 g_chosenGun = 0;       // the confirmed gun and round (its index in F3NV_AmmoSwitch.Rounds), under g_lock
SInt32 g_chosenRound = -1;

struct AmmoList {
    bool open = false;
    UInt32 gun = 0;
    Group group;
    std::vector<UInt32> counts;
    SInt32 chosen = 0, loaded = 0;
} g_ammo;  // UI thread only

// The index in g_groups of gun `form`'s list (a list keyword on its record), or -1 (held under g_lock).
SInt32 GroupOf(TESForm *form) {
    if (!form || form->formType != kFormType_WEAP) return -1;
    BGSKeywordForm &keys = static_cast<TESObjectWEAP *>(form)->keyword;
    for (SInt32 g = 0; g < SInt32(g_groups.size()); g++)
        for (UInt32 k = 0; keys.keywords && k < keys.numKeywords; k++)
            if (keys.keywords[k] == g_groups[g].list) return g;
    return -1;
}

// How many of `form` `holder` carries, over all its stacks.
UInt32 Carried(TESObjectREFR *holder, TESForm *form) {
    if (!holder || !form || !holder->inventoryList) return 0;
    UInt32 total = 0;
    BGSInventoryList *list = holder->inventoryList;
    list->inventoryLock.LockForRead();
    for (UInt32 i = 0; i < list->items.count; i++) {
        BGSInventoryItem entry;
        list->items.GetNthItem(i, entry);
        if (entry.form != form) continue;
        for (BGSInventoryItem::Stack *s = entry.stack; s; s = s->next) total += UInt32(std::max<SInt32>(0, s->count));
    }
    list->inventoryLock.UnlockRead();
    return total;
}

// Which of `group`'s rounds gun stack `stack` holds (an ammo mod among its instance's mods); the first when none
// does, as the gun's default combination holds the first round's mod.
SInt32 Loaded(BGSInventoryItem::Stack *stack, const Group &group) {
    BSExtraData *data = stack && stack->extraData ? stack->extraData->GetByType(kExtraData_ObjectInstance) : nullptr;
    auto *extra = static_cast<BGSObjectInstanceExtra *>(data);
    if (!extra || !extra->data || !extra->data->forms) return 0;
    UInt32 n = extra->data->blockSize / sizeof(BGSObjectInstanceExtra::Data::Form);
    for (UInt32 i = 0; i < n; i++) {
        auto at = std::find(group.mods.begin(), group.mods.end(), extra->data->forms[i].formId);
        if (at != group.mods.end()) return SInt32(at - group.mods.begin());
    }
    return 0;
}

bool CanLoad() {
    return g_ammo.chosen != g_ammo.loaded && g_ammo.counts[g_ammo.chosen] > 0;
}

// Open the ammo list for the highlighted gun, on its loaded round; on a gun of one ammo type, or with two copies
// of it (Papyrus attaches a mod to the form, not to one copy), say so on the card.
void Open(GFxMovieRoot *movie) {
    GFxValue page, list, entry, id, node;
    if (!CurrentPage(movie, &page) || !PipboyMovieThere() || !Get(page, "List_mc", &list) ||
        !Get(list, "selectedEntry", &entry) || !Get(entry, "formID", &id))
        return;
    UInt32 formID = UInt32(SInt64(Num(id)));
    TESForm *gun = LookupFormByID(formID);
    PlayerCharacter *player = *g_player;
    SInt32 g;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        g = GroupOf(gun);
        if (g >= 0) g_ammo.group = g_groups[g];
    }
    if (g < 0 || !player) {
        if (gun && gun->formType == kFormType_WEAP) SayOnCard("One type only", HINT);
        return;
    }
    if (Carried(player, gun) > 1) {
        SayOnCard("Drop a copy first", HINT);
        return;
    }
    Get(entry, "nodeID", &node);
    g_ammo.loaded = Loaded(FindStack(player, gun, PipboyLineStack(formID, UInt32(Num(node)))), g_ammo.group);
    g_ammo.counts.clear();
    for (TESForm *round : g_ammo.group.rounds) g_ammo.counts.push_back(Carried(player, round));
    g_ammo.chosen = g_ammo.loaded;
    g_ammo.gun = formID;
    g_ammo.open = true;
    _MESSAGE("Pip-Boy ammo list for %08X: %u rounds, loaded %d", formID, UInt32(g_ammo.counts.size()),
             g_ammo.loaded);
    SetModal(page, true);
}

// Close the ammo list, loading the chosen round when `load`; the game redraws the item card.
void Close(GFxMovieRoot *movie, bool load) {
    GFxValue page;
    if (load) {
        std::lock_guard<std::mutex> hold(g_lock);
        g_chosenGun = g_ammo.gun;
        g_chosenRound = g_ammo.group.start + g_ammo.chosen;
    }
    g_ammo.open = false;
    if (CurrentPage(movie, &page)) {
        SetModal(page, false);
        page.Invoke("onListSelectionChange", nullptr, nullptr, 0);
    }
    if (load)
        _MESSAGE("Pip-Boy ammo: %08X round %d, %s %s", g_ammo.gun, g_ammo.group.start + g_ammo.chosen, EVENT,
                 SendExternal(movie, EVENT) ? "sent" : "not sent");
}

// The AMMO hint's click: open the ammo list.
class HintClick : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        if (!g_ammo.open && !RepairListOpen()) AmmoKey(args->movie->movieRoot, KEY_V);
    }
};

// ---- Papyrus (F3NV_PipboyAmmo) ----

// Papyrus: F3NV_AmmoSwitch's lists (its Lists, Starts, Rounds and Mods arrays); the plugin forgets them each game
// start. Lists of one round are left out.
void SetLists(StaticFunctionTag *, VMArray<TESForm *> lists, VMArray<SInt32> starts, VMArray<TESForm *> rounds,
              VMArray<TESForm *> mods) {
    std::lock_guard<std::mutex> hold(g_lock);
    g_groups.clear();
    for (UInt32 g = 0; g < lists.Length() && g + 1 < starts.Length(); g++) {
        Group group;
        SInt32 end = 0;
        lists.Get(&group.list, g);
        starts.Get(&group.start, g);
        starts.Get(&end, g + 1);
        for (SInt32 m = group.start; m >= 0 && m < end && UInt32(m) < rounds.Length() && UInt32(m) < mods.Length();
             m++) {
            TESForm *round = nullptr, *mod = nullptr;
            rounds.Get(&round, m);
            mods.Get(&mod, m);
            group.rounds.push_back(round);
            group.mods.push_back(mod ? mod->formID : 0);
        }
        if (group.list && group.rounds.size() > 1) g_groups.push_back(group);
    }
    _MESSAGE("ammo lists: %u", UInt32(g_groups.size()));
}

// Papyrus: the gun whose ammo was chosen in the Pip-Boy; None with no choice waiting.
TESForm *ChosenGun(StaticFunctionTag *) {
    std::lock_guard<std::mutex> hold(g_lock);
    return g_chosenRound >= 0 ? LookupFormByID(g_chosenGun) : nullptr;
}

// Papyrus: the chosen round's index in F3NV_AmmoSwitch.Rounds, cleared as it is taken; -1 with none.
SInt32 TakeChoice(StaticFunctionTag *) {
    std::lock_guard<std::mutex> hold(g_lock);
    SInt32 round = g_chosenRound;
    g_chosenRound = -1;
    return round;
}

}  // namespace

bool AmmoListOpen() {
    return g_ammo.open;
}

void ForgetAmmoList() {
    g_ammo.open = false;
}

bool AmmoKey(GFxMovieRoot *movie, int key) {
    if (!g_ammo.open) {
        if (key == KEY_V) Open(movie);
        return key == KEY_V;
    }
    SInt32 last = SInt32(g_ammo.group.rounds.size()) - 1;
    if (key == KEY_UP || key == KEY_W || key == KEY_DOWN || key == KEY_S) {
        SInt32 step = key == KEY_UP || key == KEY_W ? -1 : 1;
        g_ammo.chosen = std::max<SInt32>(0, std::min<SInt32>(last, g_ammo.chosen + step));
    } else if (key == KEY_ENTER || key == KEY_E) {
        if (g_ammo.chosen == g_ammo.loaded || CanLoad()) Close(movie, CanLoad());
    } else if (key == KEY_ESC || key == KEY_TAB || key == KEY_V) {
        Close(movie, false);
    }
    return true;
}

bool AmmoView(ListView *view) {
    if (!g_ammo.open) return false;
    view->heading = {"AMMO TYPE", "CARRIED"};
    for (size_t i = 0; i < g_ammo.group.rounds.size(); i++) {
        TESForm *round = g_ammo.group.rounds[i];
        const char *name = round ? round->GetFullName() : nullptr;
        std::string text = name && *name ? name : "?";
        if (SInt32(i) == g_ammo.loaded) text += " (loaded)";
        view->rows.push_back({text, std::to_string(g_ammo.counts[i])});
    }
    view->chosen = g_ammo.chosen;
    view->keys = {CanLoad() ? "ENTER) LOAD" : "", "ESC) CANCEL"};
    return true;
}

bool MakeAmmoHint(GFxMovieRoot *movie, GFxValue *hint) {
    return MakeHint(movie, HINT, HINT_KEY, [](GFxMovieRoot *m, GFxValue *out) { CreateFunction<HintClick>(out, m); },
                    hint);
}

void RegisterAmmo(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction4<StaticFunctionTag, void, VMArray<TESForm *>, VMArray<SInt32>,
                                             VMArray<TESForm *>, VMArray<TESForm *>>("SetLists", SCRIPT, SetLists, vm));
    vm->RegisterFunction(new NativeFunction0<StaticFunctionTag, TESForm *>("ChosenGun", SCRIPT, ChosenGun, vm));
    vm->RegisterFunction(new NativeFunction0<StaticFunctionTag, SInt32>("TakeChoice", SCRIPT, TakeChoice, vm));
}

}  // namespace condition
