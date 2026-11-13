// F3NV.dll: FNV's own rules on Fallout 4 (docs/fork/spin_offs.md#move): the weapons' starting condition and no
// combat sprint (plugin.cpp), Damage Threshold (damage.cpp), Hardcore (hardcore.cpp), a Goodbye ending the talk
// (talk.cpp), and the natives the casino's movie calls (gfx.cpp). The item condition API, the Pip-Boy, the
// transfer menus' CND line and the dialogue menu are Cleanroom UI's (CleanroomUI.dll, CleanroomDialogue.dll).
#pragma once

#include "f4se/GameForms.h"
#include "f4se/PapyrusVM.h"
#include "f4se/ScaleformCallbacks.h"
#include "f4se/ScaleformMovie.h"
#include "f4se/ScaleformValue.h"

#include <mutex>

namespace condition {

// Guards state the game's threads and Papyrus share (hardcore.cpp's needs).
extern std::mutex g_lock;

// ---- Flash helpers (gfx.cpp) ----

// A Flash value as a number (int, uint, number or bool; else 0).
double Num(const GFxValue &v);

// Member `name` of Flash object `obj` into `out`; false when `obj` is not an object or lacks it.
bool Get(GFxValue &obj, const char *name, GFxValue *out);

// Listen for `event` on Flash object `target` with a native `Handler`; false when it could not be added.
template <class Handler>
bool Listen(GFxMovieRoot *movie, GFxValue &target, const char *event) {
    GFxValue args[2];
    movie->CreateString(&args[0], event);
    CreateFunction<Handler>(&args[1], movie);
    return target.Invoke("addEventListener", nullptr, args, 2);
}

// F4SE's Scaleform callback (gfx.cpp): give a movie's f4se.plugins.F3NV the natives the casino's movie calls: Log,
// HudColor and TextureExists (f3ui's Images).
bool RegisterMovieNatives(GFxMovieView *view, GFxValue *plugin);

// ---- A Goodbye ends the talk (talk.cpp; docs/fork/fo4_pipeline.md#goodbye-ends-talk) ----

// Register F3NV_Talk's native EndTalk, run through F4SE's task interface `tasks`.
void RegisterTalk(VirtualMachine *vm, void *tasks);

// ---- Damage Threshold (damage.cpp; docs/fork/fo4_pipeline.md#damage-threshold) ----

// Point FO4's two resistance-curve calls at FNV's DT and DR, and count a projectile hit's pellets, through
// g_branchTrampoline (set up); false when not all of them.
bool HookDamage();

// Register F3NV_Damage's native SetRules.
void RegisterDamage(VirtualMachine *vm);

// Whether the call instruction at `site` still calls `target`.
bool CallsTarget(uintptr_t site, uintptr_t target);

// ---- FNV Hardcore (hardcore.cpp; docs/fork/fo4_hardcore.md#dll) ----

// INI color `prefix`R/G/B:Interface (the player's HUD colors, e.g. iHUDColor) as 0xRRGGBB; white when not found.
UInt32 HudColor(const char *prefix);

// Weigh ammo while Hardcore is on: FO4's ammo weight test, through g_branchTrampoline (set up); false when not.
bool HookAmmoWeight();

// Listen for menus opening, with F4SE's task interface, and give the open HUD its needs fields on the UI thread as
// each opens (so a HUD opened before the listener still gets them); once the game has loaded.
void InstallHud(void *taskInterface);

// Register F3NV_Hardcore's native Track.
void RegisterHardcore(VirtualMachine *vm);

}  // namespace condition
