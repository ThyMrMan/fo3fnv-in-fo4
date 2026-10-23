// FalloutCondition's Pip-Boy tabs (docs/fork/fo4_pipboy_tabs.md): FNV's Skills, Reputation and Karma, as tabs
// of the Pip-Boy's STAT page after its own (STATUS, SPECIAL, PERKS).
//
// TES4_Pipboy.SetTab gives a tab: its rows (a FormList of actor values on the player, or globals), the strings
// a row's value picks (none: the number shows) and the globals that show each row. The STAT page's tab names are
// the array its public TabNames getter returns, so a name pushed there is a tab the header shows and the menu
// switches to (the engine keeps the current tab number). Each tab is a copy of the page's own SPECIAL tab
// (SPECIALTab, in the menu's class domain once the page is loaded): its list (BSScrollingList of
// SPECIALListEntry rows: text, value, modifier, description) and description field move into a clip of ours on
// the page, at the SPECIAL tab's place; the copy itself never joins the stage, so it never takes SPECIAL's data.
// While its tab is current, a clip is shown, filled and given the keyboard focus.
#include "condition.h"

#include "f4se/GameMenus.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/ScaleformCallbacks.h"

#include <algorithm>
#include <cctype>
#include <atomic>
#include <cmath>
#include <string>
#include <vector>

namespace condition {

namespace {

struct Tab {
    std::string name;
    SInt32 order;
    std::vector<UInt32> rows, shown;
    std::vector<std::string> values;
};
std::vector<Tab> g_tabs;  // by order, under g_lock
std::atomic<bool> g_dirty{false};

// The STAT page given our tabs (identity only), the page's own tab count, and which of ours is shown (-1: none).
const void *g_page = nullptr;
UInt32 g_first = 0;
SInt32 g_showing = -1;
std::string g_description;
const char *CLIP = "fnvTab", *SCRIPT = "TES4_Pipboy";

std::string ClipName(size_t i) {
    return std::string(CLIP) + std::to_string(i);
}

// A form's value on the player (an actor value's, with its base in `base`) or a global's; false otherwise.
bool ValueOf(TESForm *form, float *value, float *base) {
    if (!form) return false;
    if (form->formType == kFormType_AVIF) {
        Actor *player = *g_player;
        if (!player) return false;
        auto *av = static_cast<ActorValueInfo *>(form);
        *value = player->actorValueOwner.GetValue(av);
        *base = player->actorValueOwner.GetBase(av);
        return true;
    }
    if (form->formType == kFormType_GLOB) {
        *value = *base = static_cast<TESGlobal *>(form)->value;
        return true;
    }
    return false;
}

std::string NameOf(TESForm *form) {
    if (form->formType == kFormType_AVIF) {
        const char *name = static_cast<ActorValueInfo *>(form)->fullName.name.c_str();
        if (name && *name) return name;
    }
    const char *edid = form->formType == kFormType_GLOB ? static_cast<TESGlobal *>(form)->editorID : nullptr;
    return edid ? edid : "";
}

std::string DescriptionOf(TESForm *form) {
    if (form->formType != kFormType_AVIF) return "";
    auto *av = static_cast<ActorValueInfo *>(form);
    BSString text;
    CALL_MEMBER_FN(&av->description, Get)(&text, av);
    const char *got = text.Get();
    return got ? got : "";
}

// Tab `tab`'s list entries: a row per shown form, its name, its value (a string of the tab's, or the number and
// its modifier from its base) and description.
void Entries(GFxMovieRoot *movie, const Tab &tab, GFxValue *out) {
    movie->CreateArray(out);
    for (size_t i = 0; i < tab.rows.size(); i++) {
        float value = 0.0f, base = 0.0f, shown = 1.0f, unused = 0.0f;
        TESForm *form = LookupFormByID(tab.rows[i]);
        if (!ValueOf(form, &value, &base)) continue;
        if (i < tab.shown.size() && (!ValueOf(LookupFormByID(tab.shown[i]), &shown, &unused) || shown < 1.0f))
            continue;
        GFxValue entry, text, shownValue, modifier, description;
        movie->CreateObject(&entry);
        movie->CreateString(&text, NameOf(form).c_str());
        SInt32 index = SInt32(std::floor(value + 0.5f));
        bool named = !tab.values.empty() && index >= 0 && index < SInt32(tab.values.size());
        if (named) movie->CreateString(&shownValue, tab.values[index].c_str());
        else shownValue.SetInt(index);
        modifier.SetInt(named ? 0 : SInt32(std::floor(value - base + 0.5f)));
        movie->CreateString(&description, DescriptionOf(form).c_str());
        entry.SetMember("text", &text);
        entry.SetMember("value", &shownValue);
        entry.SetMember("modifier", &modifier);
        entry.SetMember("description", &description);
        out->PushBack(&entry);
    }
}

// Give STAT page `page` a clip per tab (a SPECIAL tab copy's list and description) and the tabs' names.
bool Install(GFxMovieRoot *movie, GFxValue &page, const std::vector<Tab> &tabs) {
    GFxValue names, special, x, y;
    if (!Get(page, "TabNames", &names) || !names.IsArray() || !Get(page, "SPECIALTab_mc", &special)) return false;
    g_first = names.GetArraySize();
    Get(special, "x", &x);
    Get(special, "y", &y);
    for (size_t i = 0; i < tabs.size(); i++) {
        GFxValue copy, clip, args[1], name, hidden(false), count(UInt32(std::max<size_t>(tabs[i].rows.size(), 7)));
        movie->CreateObject(&copy, "SPECIALTab");
        movie->CreateObject(&clip, "flash.display.MovieClip");
        if (!copy.IsObject() || !clip.IsObject() || !Get(copy, "List_mc", &args[0])) {
            _MESSAGE("could not copy the Pip-Boy's SPECIAL tab for the %s tab", tabs[i].name.c_str());
            return false;
        }
        args[0].SetMember("numListItems", &count);
        clip.Invoke("addChild", nullptr, args, 1);
        if (Get(copy, "Description_tf", &args[0])) clip.Invoke("addChild", nullptr, args, 1);
        movie->CreateString(&name, ClipName(i).c_str());
        clip.SetMember("name", &name);
        clip.SetMember("x", &x);
        clip.SetMember("y", &y);
        clip.SetMember("visible", &hidden);
        page.Invoke("addChild", nullptr, &clip, 1);
        std::string upper = tabs[i].name;  // Papyrus strings keep the case first stored ("skills")
        std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char c) { return char(toupper(c)); });
        movie->CreateString(&name, upper.c_str());
        names.PushBack(&name);
    }
    _MESSAGE("added %u Pip-Boy STAT tabs after its %u", UInt32(tabs.size()), g_first);
    return true;
}

// Show the clip of our tab `shown` (-1: none) on `page`; filling and focusing its list as it shows or when
// the tabs change.
void Show(GFxMovieRoot *movie, GFxValue &page, SInt32 shown, const std::vector<Tab> &tabs, bool refill) {
    for (size_t i = 0; i < tabs.size(); i++) {
        GFxValue clip, name, list, on(SInt32(i) == shown);
        movie->CreateString(&name, ClipName(i).c_str());
        if (!page.Invoke("getChildByName", &clip, &name, 1) || !clip.IsObject()) continue;
        clip.SetMember("visible", &on);
        if (SInt32(i) != shown || (shown == g_showing && !refill) || !Get(clip, "List_mc", &list)) continue;
        GFxValue entries, stage, selected;
        Entries(movie, tabs[i], &entries);
        list.SetMember("entryList", &entries);
        list.Invoke("InvalidateData", nullptr, nullptr, 0);
        if (Get(list, "selectedIndex", &selected) && Num(selected) < 0) {
            GFxValue first(SInt32(0));
            list.SetMember("selectedClipIndex", &first);
        }
        if (Get(list, "stage", &stage) && stage.IsObject()) stage.SetMember("focus", &list);
    }
    g_showing = shown;
}

// Keep the shown tab's description field at its highlighted row's description.
void Describe(GFxMovieRoot *movie, GFxValue &page) {
    GFxValue clip, name, list, entry, text, field;
    movie->CreateString(&name, ClipName(size_t(g_showing)).c_str());
    if (!page.Invoke("getChildByName", &clip, &name, 1) || !Get(clip, "List_mc", &list) ||
        !Get(list, "selectedEntry", &entry) || !Get(entry, "description", &text) || !text.IsString() ||
        g_description == text.GetString() || !Get(clip, "Description_tf", &field))
        return;
    g_description = text.GetString();
    field.SetMember("text", &text);
}

// Papyrus: give the Pip-Boy's STAT page tab `name` (placed by `order` among ours): `rows`' values on the player
// (actor values) or their own (globals), each picking from `values` (none: the number), shown while its global
// in `shown` (None: always) is at least 1.
void SetTab(StaticFunctionTag *, BSFixedString name, SInt32 order, BGSListForm *rows, VMArray<BSFixedString> values,
            BGSListForm *shown) {
    Tab tab{name.c_str() ? name.c_str() : "", order, {}, {}, {}};
    for (UInt32 i = 0; rows && i < rows->forms.count; i++) {
        TESForm *form = nullptr;
        rows->forms.GetNthItem(i, form);
        tab.rows.push_back(form ? form->formID : 0);
    }
    for (UInt32 i = 0; shown && i < shown->forms.count; i++) {
        TESForm *form = nullptr;
        shown->forms.GetNthItem(i, form);
        tab.shown.push_back(form ? form->formID : 0);
    }
    for (UInt32 i = 0; i < values.Length(); i++) {
        BSFixedString value;
        values.Get(&value, i);
        tab.values.push_back(value.c_str() ? value.c_str() : "");
    }
    std::lock_guard<std::mutex> hold(g_lock);
    auto at = std::find_if(g_tabs.begin(), g_tabs.end(), [&](const Tab &t) { return t.name == tab.name; });
    if (at != g_tabs.end()) *at = tab;
    else g_tabs.push_back(tab);
    std::stable_sort(g_tabs.begin(), g_tabs.end(), [](const Tab &a, const Tab &b) { return a.order < b.order; });
    g_dirty = true;
}

}  // namespace

void UpdatePages(GFxMovieRoot *movie, const std::string &base) {
    GFxValue page, tab;
    if (!movie->GetVariable(&page, (base + ".CurrentPage").c_str()) || !page.IsObject() ||
        !page.HasMember("SPECIALTab_mc") || !movie->GetVariable(&tab, (base + ".DataObj.CurrentTab").c_str()))
        return;
    std::vector<Tab> tabs;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        tabs = g_tabs;
    }
    if (tabs.empty()) return;
    if (page.data.obj != g_page) {
        g_page = page.data.obj;
        g_showing = -1;
        g_description.clear();
        if (!Install(movie, page, tabs)) return;
        GFxValue menu;
        if (movie->GetVariable(&menu, base.c_str())) menu.Invoke("InvalidateData", nullptr, nullptr, 0);
    }
    SInt32 current = SInt32(Num(tab)) - SInt32(g_first);
    SInt32 shown = current >= 0 && current < SInt32(tabs.size()) ? current : -1;
    Show(movie, page, shown, tabs, g_dirty.exchange(false));
    if (shown >= 0) Describe(movie, page);
}

void ResetPages() {
    g_page = nullptr;
}

void RegisterPages(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction5<StaticFunctionTag, void, BSFixedString, SInt32, BGSListForm *,
                                             VMArray<BSFixedString>, BGSListForm *>("SetTab", SCRIPT, SetTab, vm));
}

}  // namespace condition
