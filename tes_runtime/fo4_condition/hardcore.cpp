// F3NV: FNV Hardcore's ammo weight and HUD needs on Fallout 4 (docs/fork/fo4_hardcore.md#dll). Both read the
// F3NV_Hardcore global, which F3NV_HardcoreNative.Track names, so both stop the moment Hardcore is turned off.
//
// Ammo weight. FO4's form weight (0x321FD0, a switch on the form type) gives AMMO its weight (its TESWeightForm at
// +0x150) only when the player's difficulty (0xD6D600) is 6, Survival; the call at 0x3220E0 is that test, and the
// only one of its kind there. It goes to AmmoDifficulty, which answers 6 while Hardcore is on, so ammo weighs its
// record's weight (FNV's, written by the converter) wherever the engine weighs an item: the Pip-Boy, containers,
// barter and carry weight. Off Hardcore the real difficulty is returned, so Survival keeps its own ammo weight.
//
// HUD. While Hardcore is on, three fields above the health bar (in HUDMenu's LeftMeters_mc, pinned bottom-left)
// show FNV's H2O, FOD and SLP numbers. Each takes FNV's step for its need: dim below 400, full from 400, the HUD's
// warning color from 600, flashing from 800 (the guide's "dark, light, red, pulsing red"; FNV's thresholds 200,
// 400, 600 and 800). The normal and warning colors are the player's HUD colors (iHUDColor*, iHUDColorWarning*);
// the engine does not tint a field it did not make.
#include "condition.h"

#include "f4se/GameMenus.h"
#include "f4se/GameSettings.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/ScaleformCallbacks.h"
#include "f4se_common/BranchTrampoline.h"

#include <atomic>
#include <cstring>
#include <string>
#include <vector>

namespace condition {

namespace {

const char *SCRIPT = "F3NV_HardcoreNative", *HUD = "HUDMenu", *HOOKED = "f3nvNeeds", *FONT = "$MAIN_Font_Bold";
const char *LABELS[] = {"H2O", "FOD", "SLP"};
const size_t NEEDS = 3;
const float DIM_BELOW = 400.0f, WARN_FROM = 600.0f, FLASH_FROM = 800.0f, DIM_ALPHA = 0.5f;
const double FIELD_STEP = 90.0, ABOVE_METERS = 30.0;
const ULONGLONG FLASH_MS = 400;
const SInt32 SURVIVAL = 6;

using DifficultyFn = SInt32 (*)(void *);
RelocAddr<DifficultyFn> Difficulty(0xD6D600);
RelocAddr<uintptr_t> AMMO_DIFFICULTY_CALL(0x3220E0);

std::atomic<TESGlobal *> g_on{nullptr};
std::vector<ActorValueInfo *> g_needs;  // under g_lock

bool On() {
    TESGlobal *on = g_on.load();
    return on && on->value != 0.0f;
}

// The ammo case's difficulty test: Survival while Hardcore is on, so ammo weighs its record's weight.
SInt32 AmmoDifficulty(void *player) {
    return On() ? SURVIVAL : Difficulty(player);
}

// INI color `prefix`R/G/B:Interface as 0xRRGGBB; white when not found.
UInt32 HudColor(const char *prefix) {
    UInt32 rgb = 0;
    for (const char *channel : {"R", "G", "B"}) {
        Setting *setting = GetINISetting((std::string(prefix) + channel + ":Interface").c_str());
        rgb = (rgb << 8) | (setting ? (setting->data.u32 & 0xFF) : 0xFF);
    }
    return rgb;
}

// The fields' last shown state, to set them only on a change.
struct Shown {
    SInt32 value = -1;
    UInt32 color = 0;
    float alpha = -1.0f;
    bool visible = true;
};
Shown g_shown[NEEDS];  // UI thread only
UInt32 g_normal = 0xFFFFFF, g_warning = 0xFF0000;

// Need `i`'s field at `value`: its label and number, and FNV's step as color, alpha and flashing.
void ShowNeed(GFxMovieRoot *movie, GFxValue &field, size_t i, float value, bool flashOff) {
    Shown now;
    now.value = SInt32(value);
    now.color = value >= WARN_FROM ? g_warning : g_normal;
    now.alpha = value < DIM_BELOW ? DIM_ALPHA : 1.0f;
    now.visible = !(value >= FLASH_FROM && flashOff);
    Shown &was = g_shown[i];
    if (now.value != was.value) {
        std::string html = std::string("<font face='") + FONT + "' size='20'>" + LABELS[i] + " " +
                           std::to_string(now.value) + "</font>";
        GFxValue text;
        movie->CreateString(&text, html.c_str());
        field.SetMember("htmlText", &text);
        was.color = 0xFFFFFFFF;  // htmlText resets the color
    }
    if (now.color != was.color) {
        GFxValue color(now.color);
        field.SetMember("textColor", &color);
    }
    if (now.alpha != was.alpha) {
        GFxValue alpha(double(now.alpha));
        field.SetMember("alpha", &alpha);
    }
    if (now.visible != was.visible) {
        GFxValue visible(now.visible);
        field.SetMember("visible", &visible);
    }
    was = now;
}

// One HUD frame: show the needs while Hardcore is on, else hide them.
void UpdateHud(GFxMovieRoot *movie) {
    GFxValue box;
    if (!movie->GetVariable(&box, (std::string("root.LeftMeters_mc.") + HOOKED).c_str()) || !box.IsObject()) return;
    std::vector<ActorValueInfo *> needs;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        needs = g_needs;
    }
    Actor *player = *g_player;
    bool on = On() && player && needs.size() == NEEDS;
    GFxValue shown(on);
    box.SetMember("visible", &shown);
    if (!on) return;
    bool flashOff = (GetTickCount64() / FLASH_MS) % 2 == 1;
    for (size_t i = 0; i < NEEDS; i++) {
        GFxValue field;
        if (Get(box, ("need" + std::to_string(i)).c_str(), &field))
            ShowNeed(movie, field, i, needs[i] ? player->actorValueOwner.GetValue(needs[i]) : 0.0f, flashOff);
    }
}

class HudFrame : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override { UpdateHud(args->movie->movieRoot); }
};

// A text field `name` at `x` in `box`, as the HUD's own (no mouse, not selectable, embedded font).
void AddField(GFxMovieRoot *movie, GFxValue &box, const std::string &name, double x) {
    GFxValue field, value;
    movie->CreateObject(&field, "flash.text.TextField");
    if (!field.IsObject()) return;
    movie->CreateString(&value, name.c_str());
    field.SetMember("name", &value);
    movie->CreateString(&value, "left");
    field.SetMember("autoSize", &value);
    GFxValue yes(true), no(false), at(x);
    field.SetMember("embedFonts", &yes);
    field.SetMember("selectable", &no);
    field.SetMember("mouseEnabled", &no);
    field.SetMember("x", &at);
    box.SetMember(name.c_str(), &field);
    box.Invoke("addChild", nullptr, &field, 1);
}

// Papyrus: Hardcore's global (on while not 0) and its three needs (Dehydration, Hunger, Sleep Deprivation).
void Track(StaticFunctionTag *, TESGlobal *on, VMArray<ActorValueInfo *> needs) {
    std::vector<ActorValueInfo *> avs;
    for (UInt32 i = 0; i < needs.Length(); i++) {
        ActorValueInfo *av = nullptr;
        needs.Get(&av, i);
        avs.push_back(av);
    }
    {
        std::lock_guard<std::mutex> hold(g_lock);
        g_needs = avs;
    }
    g_on = on;
}

}  // namespace

bool HookAmmoWeight() {
    uintptr_t site = AMMO_DIFFICULTY_CALL.GetUIntPtr();
    auto *call = reinterpret_cast<const UInt8 *>(site);
    SInt32 rel;
    std::memcpy(&rel, call + 1, sizeof(rel));
    bool hooked = call[0] == 0xE8 && site + 5 + rel == Difficulty.GetUIntPtr() &&
                  g_branchTrampoline.Write5Call(site, uintptr_t(AmmoDifficulty));
    _MESSAGE("Hardcore ammo weight %s", hooked ? "hooked" : "not hooked");
    return hooked;
}

// The HUD's needs clip above its health bar, and a frame listener; once per HUD movie, nothing without a HUD.
void HookHud() {
    BSFixedString name(HUD);
    IMenu *menu = (*g_ui)->GetMenu(name);
    GFxValue root, meters, bounds, top, left, box, boxName;
    if (!menu || !menu->movie || !menu->movie->movieRoot) return;
    GFxMovieRoot *movie = menu->movie->movieRoot;
    if (!movie->GetVariable(&root, "root") || !Get(root, "LeftMeters_mc", &meters) || !meters.IsObject()) {
        _MESSAGE("HUD opened, but it has no LeftMeters_mc: no Hardcore needs");
        return;
    }
    if (meters.HasMember(HOOKED)) return;
    movie->CreateObject(&box, "flash.display.MovieClip");
    if (!box.IsObject()) return;
    if (meters.Invoke("getBounds", &bounds, &meters, 1) && Get(bounds, "y", &top) && Get(bounds, "x", &left)) {
        GFxValue y(Num(top) - ABOVE_METERS);
        box.SetMember("x", &left);
        box.SetMember("y", &y);
    }
    movie->CreateString(&boxName, HOOKED);
    box.SetMember("name", &boxName);
    GFxValue hidden(false), no(false);
    box.SetMember("visible", &hidden);
    box.SetMember("mouseChildren", &no);
    for (size_t i = 0; i < NEEDS; i++) AddField(movie, box, "need" + std::to_string(i), FIELD_STEP * double(i));
    meters.Invoke("addChild", nullptr, &box, 1);
    meters.SetMember(HOOKED, &box);
    GFxValue args[2];
    movie->CreateString(&args[0], "enterFrame");
    CreateFunction<HudFrame>(&args[1], movie);
    root.Invoke("addEventListener", nullptr, args, 2);
    g_normal = HudColor("iHUDColor");
    g_warning = HudColor("iHUDColorWarning");
    for (Shown &shown : g_shown) shown = Shown();
    _MESSAGE("Hardcore needs added to the HUD (colors %06X, %06X)", g_normal, g_warning);
}

void RegisterHardcore(VirtualMachine *vm) {
    vm->RegisterFunction(new NativeFunction2<StaticFunctionTag, void, TESGlobal *, VMArray<ActorValueInfo *>>(
        "Track", SCRIPT, Track, vm));
}

}  // namespace condition
