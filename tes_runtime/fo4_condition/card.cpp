// Other mods' lines on the Pip-Boy's inventory item card (docs/fork/swf_framework.md#card-lines): set from Papyrus
// (F3NV_ItemCard.SetLine) for one item, or for every item carrying a keyword, and drawn by our Pip-Boy movie after
// F3NV's own lines (pipboy.cpp PipboyCardLines). They are kept until a save loads or a new game starts, so a mod
// sets them again on each game load.
#include "condition.h"

#include "f4se/GameRTTI.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"

#include <algorithm>
#include <string>
#include <vector>

namespace condition {

namespace {

const char *SCRIPT = "F3NV_ItemCard";

// A mod's line: the item's form ID (or a keyword's, for every item carrying it) and the line.
struct CardLine {
    UInt32 form;
    bool keyword;
    Row row;
};
std::vector<CardLine> g_cardLines;  // under g_lock

// Papyrus: show `label` with `value` on the item card of `item` (a Keyword: of every item carrying it), replacing
// that item's line of the same label; an empty value removes it.
void SetLine(StaticFunctionTag *, TESForm *item, BSFixedString label, BSFixedString value) {
    const char *text = label.c_str(), *shown = value.c_str();
    if (!item || !text || !*text) return;
    std::lock_guard<std::mutex> hold(g_lock);
    g_cardLines.erase(std::remove_if(g_cardLines.begin(), g_cardLines.end(),
                                     [&](const CardLine &l) { return l.form == item->formID && l.row.text == text; }),
                      g_cardLines.end());
    if (shown && *shown) g_cardLines.push_back({item->formID, item->formType == kFormType_KYWD, {text, shown}});
}

// Whether `form` carries the keyword of form ID `keyword`.
bool Carries(TESForm *form, UInt32 keyword) {
    auto *keys = form ? DYNAMIC_CAST(form, TESForm, BGSKeywordForm) : nullptr;
    for (UInt32 k = 0; keys && keys->keywords && k < keys->numKeywords; k++)
        if (keys->keywords[k] && keys->keywords[k]->formID == keyword) return true;
    return false;
}

}  // namespace

void CardLinesOf(UInt32 formID, std::vector<Row> *out) {
    TESForm *form = LookupFormByID(formID);
    std::lock_guard<std::mutex> hold(g_lock);
    for (const CardLine &line : g_cardLines)
        if (line.keyword ? Carries(form, line.form) : line.form == formID) out->push_back(line.row);
}

void ForgetCardLines() {
    std::lock_guard<std::mutex> hold(g_lock);
    g_cardLines.clear();
}

void RegisterItemCard(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction3<StaticFunctionTag, void, TESForm *, BSFixedString, BSFixedString>(
        "SetLine", SCRIPT, SetLine, vm));
}

}  // namespace condition
