// F3NV: our dialogue menu in place of XDI (docs/fork/fo4_dialogue_menu_plan.md#test-build).
//
// An option is a player INFO that names an answer topic (the links in Data\F4SE\Plugins\F3NV_Menus\*.txt); its
// answer is that topic's first passing INFO, chosen by the engine's own picker, so nothing pairs options and answers
// by position. The option shows that answer line's prompt (FNV shows the first passing line's) and skill check. The menu movie (Interface/DialogueMenu.swf, built by fo4_import.dialogue_menu) asks for the running
// Player Dialogue action's options and picks one as option index + 5. The engine then asks three call sites for the
// INFOs of the picked option; index 5 and up are ours, below 5 go to the engine's functions as before.
//
// Fallout4.exe 1.11.240, read in Fallout4.exe.unpacked.exe; the plan's engine table lists each address.
#include "condition.h"

#include "f4se/GameData.h"
#include "f4se/GameMenus.h"
#include "f4se/GameReferences.h"
#include "f4se/GameThreads.h"
#include "f4se/PluginAPI.h"
#include "f4se/ScaleformCallbacks.h"
#include "f4se/ScaleformMovie.h"
#include "f4se/ScaleformValue.h"
#include "f4se_common/BranchTrampoline.h"
#include "f4se_common/SafeWrite.h"

#include <atomic>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <unordered_map>

namespace condition {

namespace {

// ---- Engine functions ----
// The option's INFO for the player (target the NPC) or the NPC (target the player), reading the action's chosen option.
using OptionInfoFn = TESForm *(*)(void *action, void *scene, TESObjectREFR *target, SInt32 option);
// An NPC Response action's INFO for the player's chosen response (player + PLAYER_RESPONSE).
using ResponseFn = TESForm *(*)(void *action, void *scene);
// A topic's first passing INFO for `speaker` talking to `target` (Random runs included).
using PickFn = TESForm *(*)(TESForm *topic, TESObjectREFR *speaker, TESObjectREFR *target);
// Whether an INFO passes for `speaker` and `target`: not deleted, not a said Say Once, its quest's dialogue
// conditions and its own.
using PassesFn = bool (*)(TESForm *info, bool *flag, TESObjectREFR *speaker, TESObjectREFR *target);
// An INFO's prompt (RNAM), through its shared INFO; "" without one.
using PromptFn = const char *(*)(TESForm *info);
// Mark an INFO said (its said byte, its change flag for the save, its reset timer), as speaking it does.
using SaidFn = void (*)(TESForm *info);
// A quest alias's reference handle, and a handle's reference (the engine's own pair in the option functions).
using AliasFn = UInt32 *(*)(TESForm *quest, UInt32 *handle, UInt32 alias);
using HandleFn = NiPointer<TESObjectREFR> *(*)(NiPointer<TESObjectREFR> *out, UInt32 *handle);
// Pick dialogue option `option` (4: none) for the player.
using SelectFn = void (*)(PlayerCharacter *player, UInt32 option);
// A Player Dialogue action's run function (its vtable slot 21; both option calls are in it).
using RunFn = UInt64 (*)(void *action, void *scene, void *third, void *fourth);
// Stop a scene: Papyrus Scene.Stop's native (0x1119D20) calls this, then sets SCENE_STOPPING in its flags.
using StopFn = void (*)(void *scene);
// An actor's "talking" test, the one the run function waits on before the NPC slot (vtable +0x270, 0x4159BF).
using TalkingFn = bool (*)(void *actor);
// An input handler's "should handle" test (BSInputEventUser slot 1); an input event's user-event name (its slot 2);
// the game's static ZoomIn / ZoomOut user-event names.
using ShouldFn = bool (*)(void *handler, void *event);
using EventNameFn = void **(*)(void *event);
using StaticNameFn = void **(*)();
// BSGFxShaderFXTarget::EnableShadedBackground(type, brightness): the UI shader's translucent quad behind a target.
using ShadeFn = void (*)(void *target, UInt32 type, float brightness);
// DialogueMenu's holder color (0x1043EF0): 0 the HUD color, 1-7 the speech-challenge tints (iDialogueSC_*_Tint).
using TintFn = void (*)(void *menu, void *target, UInt32 type, bool dim);

RelocAddr<OptionInfoFn> OptionInfo(0x416600);
RelocAddr<ResponseFn> ResponseInfo(0x414180);
RelocAddr<PickFn> Pick(0x698DB0);
RelocAddr<PassesFn> Passes(0x69F490);
RelocAddr<PromptFn> Prompt(0x69E740);
RelocAddr<SaidFn> MarkSaid(0x69F8D0);
RelocAddr<AliasFn> AliasHandle(0x671FA0);
RelocAddr<HandleFn> HandleRef(0x21E550);
RelocAddr<SelectFn> SelectOption(0xD76130);
RelocAddr<StopFn> StopScene(0x638D60);
// The player-slot and NPC-slot calls to OptionInfo (in 0x415280), and the NPC Response call to ResponseInfo.
RelocAddr<uintptr_t> PLAYER_SLOT_CALL(0x41568A), NPC_SLOT_CALL(0x415A21), RESPONSE_CALL(0x413DA8);
RelocAddr<uintptr_t> PLAYER_DIALOGUE_VTABLE(0x2488978);
const size_t RUN_SLOT = 21;
// The player starting to say the picked option (`mov rcx, rax` before the call at 0x4158E9); `jmp 0x4158F2` takes
// the said path without saying it. The camera's switch to the player (its 1 at 0x832665 + 7; 2 keeps it on the NPC).
RelocAddr<uintptr_t> PLAYER_SPEAKS(0x4158D2), CAMERA_TO_PLAYER(0x83266C);
// The camera states that take the mouse wheel (first person: ZoomOut to third; third person: both), their vtables
// and "should handle" tests; the ZoomIn and ZoomOut name getters those tests call.
RelocAddr<uintptr_t> FIRST_PERSON_VTABLE(0x25AAB08), FIRST_PERSON_SHOULD(0x10213E0);
RelocAddr<uintptr_t> THIRD_PERSON_VTABLE(0x2522A88), THIRD_PERSON_SHOULD(0x102DFC0);
RelocAddr<StaticNameFn> ZoomInName(0xB25620), ZoomOutName(0xA7A080);
// The shaded background, and a plain BSGFxShaderFXTarget's vtable (what DialogueMenu registers its holders as).
RelocAddr<ShadeFn> EnableShadedBackground(0x1B04350);
RelocAddr<uintptr_t> SHADER_TARGET_VTABLE(0x27236D0);
RelocAddr<TintFn> TintChallenge(0x1043EF0);
const UInt8 SPEAKS[] = {0x48, 0x8B, 0xC8}, SILENT[] = {0xEB, 0x1E, 0x90};
const UInt8 CAMERA_PLAYER = 1, CAMERA_SPEAKER = 2;

// ---- Engine layouts ----
// BGSScene: its quest. Scene action: its alias, its four player topics, its chosen option (4: none).
const size_t SCENE_QUEST = 0xA8, ACTION_ALIAS = 0x08, ACTION_TOPICS = 0x20, ACTION_OPTION = 0xE0;
// TESTopic: its INFOs, their order (u16 head at +2, next of INFO i at 4 * i + 4), their count. TESTopicInfo: said.
const size_t TOPIC_INFOS = 0x50, TOPIC_ORDER = 0x58, TOPIC_COUNT = 0x60, INFO_SAID = 0x43;
// PlayerCharacter: the chosen response an NPC Response action answers.
const size_t PLAYER_RESPONSE = 0xD3C;
// BGSScene flags (Scene.Stop sets STOPPING). Action flags: the player line done (the NPC slot runs next), the NPC
// line said. Player: the flag that skips the talking wait (0x4159B3). Actor: the "talking" vtable slot.
const size_t SCENE_FLAGS = 0x28, ACTION_FLAGS = 0x10, PLAYER_NO_WAIT = 0x440, TALKING_SLOT = 0x270 / 8;
const UInt32 SCENE_STOPPING = 0x100000, PLAYER_DONE = 0x2000000, NPC_SAID = 0x4000;
const UInt32 NO_OPTION = 4, FIRST_OURS = 5, SLOTS = 4;
// DialogueMenu: the Question holder's shader target (registerObjects keeps the four at +0xE0, Question last). The
// shaded background as vanilla menus ask for it: MenuNoColorBackground at full size.
const size_t MENU_NEGATIVE_TARGET = 0xE8, MENU_QUESTION_TARGET = 0xF8, TARGET_FX_FLAGS = 0x8C;
// The speech-challenge tint 0x1043EF0 gives types 3 and 7: iDialogueSC_Hard_Tint (red).
const UInt32 CHALLENGE_HARD = 3;
const UInt32 FX_BACKGROUND_QUAD = 1;
const UInt32 MENU_NO_COLOR_BACKGROUND = 1;
const float FULL_QUAD = 1.0f;
const UInt16 END = 0xFFFF;
const char *LINKS = "Data\\F4SE\\Plugins\\F3NV_Menus\\";
// The links of the XDI-era hub plugin (tools.dialog.menu_rebuild), from before each build wrote its own: still read,
// logged DEPRECATED. Builds and the deploy delete it.
const char *LEGACY_HUB = "F3NV_MenuHub.txt";

template <class T>
T &At(void *base, size_t offset) {
    return *reinterpret_cast<T *>(static_cast<UInt8 *>(base) + offset);
}

struct Option {
    TESForm *info;
    TESForm *answer;
    std::string prompt;
    bool said;
    bool failed;  // its skill check fails for the player now
};

// An option's skill check from its link: the player's actor value and the number it needs.
struct Check {
    ActorValueInfo *av;
    UInt32 needed;
};

// The options last listed, for which action; the option picked from them.
struct Menu {
    void *action = nullptr;
    std::vector<Option> options;
};
struct Chosen {
    void *action = nullptr;
    UInt32 index = 0;
    Option option{};
    bool answered = false;
};

std::mutex g_dialogueLock;
Menu g_menu;
Chosen g_chosen;
// The waiting action last logged as listing none of ours (the menu asks again each frame for a while).
void *g_noneLogged = nullptr;
// Option INFO FormID -> answer topic FormID, read once the data has loaded.
std::unordered_map<UInt32, UInt32> g_links;
// Answer INFO FormID (or a legacy link's option INFO) -> the skill check its prompt carries.
std::unordered_map<UInt32, Check> g_checks;
bool g_linksRead = false;
// The Player Dialogue action the engine ran last, and its scene.
std::atomic<void *> g_running{nullptr}, g_runningScene{nullptr};
OptionInfoFn g_optionInfo = nullptr;
ResponseFn g_responseInfo = nullptr;
RunFn g_run = nullptr;
ShouldFn g_firstShould = nullptr, g_thirdShould = nullptr;
bool g_hooked = false, g_speechPatch = false, g_playerSpeaks = true;
F4SETaskInterface *g_dialogueTasks = nullptr;
// The wait trace: the last state logged for our picked option, and when it was picked.
UInt32 g_lastWaits = ~0u;
ULONGLONG g_pickedAt = 0;

// `plugin`'s object id `id` (hex) as a loaded FormID; 0 when the plugin is not loaded.
UInt32 Resolve(const std::string &plugin, const std::string &id) {
    const ModInfo *mod = *g_dataHandler ? (*g_dataHandler)->LookupModByName(plugin.c_str()) : nullptr;
    return mod && mod->IsActive() ? mod->GetFormID(std::strtoul(id.c_str(), nullptr, 16)) : 0;
}

// A skill check on INFO `info`: columns `at` to `at` + 2 of `f`, the actor value's plugin and id and the number needed.
void ReadCheck(UInt32 info, const std::vector<std::string> &f, size_t at, UInt32 *checks) {
    if (!info || f.size() < at + 3) return;
    UInt32 id = Resolve(f[at], f[at + 1]);
    TESForm *av = id ? LookupFormByID(id) : nullptr;
    if (!av || av->formType != kFormType_AVIF) return;
    g_checks[info] = {static_cast<ActorValueInfo *>(av), UInt32(std::strtoul(f[at + 2].c_str(), nullptr, 10))};
    (*checks)++;
}

// One links file, tab-separated, # starting a comment. Four columns link an option to its answer topic (option
// plugin, option id, answer plugin, answer id); five name an answer INFO's skill check (INFO plugin, INFO id, skill
// plugin, skill id, needed). Seven, from older builds, are a link with its option's check.
void ReadLinks(const std::string &path) {
    std::ifstream in(path);
    std::string line;
    UInt32 read = 0, kept = 0, checks = 0;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::vector<std::string> f;
        for (size_t at = 0, tab; at <= line.size(); at = tab + 1) {
            tab = line.find('\t', at);
            tab = tab == std::string::npos ? line.size() : tab;
            f.push_back(line.substr(at, tab - at));
        }
        if (f.size() < 4) continue;
        if (f.size() == 5) {
            ReadCheck(Resolve(f[0], f[1]), f, 2, &checks);
            continue;
        }
        read++;
        UInt32 option = Resolve(f[0], f[1]), answer = Resolve(f[2], f[3]);
        TESForm *info = option ? LookupFormByID(option) : nullptr, *topic = answer ? LookupFormByID(answer) : nullptr;
        if (!info || !topic || info->formType != kFormType_INFO || topic->formType != kFormType_DIAL) continue;
        g_links[option] = answer, kept++;
        ReadCheck(option, f, 4, &checks);
    }
    _MESSAGE("dialogue menu: %s: %u links, %u resolved, %u skill checks", path.c_str(), read, kept, checks);
}

// Read every links file once (the data has loaded by the first menu).
void ReadAllLinks() {
    if (g_linksRead) return;
    g_linksRead = true;
    WIN32_FIND_DATAA found;
    HANDLE find = FindFirstFileA((std::string(LINKS) + "*.txt").c_str(), &found);
    if (find == INVALID_HANDLE_VALUE) {
        _MESSAGE("dialogue menu: no links in %s", LINKS);
        return;
    }
    do {
        if (!_stricmp(found.cFileName, LEGACY_HUB))
            _MESSAGE("dialogue menu: DEPRECATED %s (the XDI-era hub; each plugin now writes its own links)",
                     found.cFileName);
        ReadLinks(std::string(LINKS) + found.cFileName);
    } while (FindNextFileA(find, &found));
    FindClose(find);
}

// A topic's INFOs in the engine's order.
std::vector<TESForm *> Infos(TESForm *topic) {
    std::vector<TESForm *> out;
    auto *infos = topic ? At<TESForm **>(topic, TOPIC_INFOS) : nullptr;
    auto *order = topic ? At<UInt16 *>(topic, TOPIC_ORDER) : nullptr;
    UInt32 count = topic ? At<UInt32>(topic, TOPIC_COUNT) : 0;
    if (!infos || !order) return out;
    for (UInt16 i = order[1]; i != END && i < count && out.size() < count; i = order[2 * i + 2])
        if (infos[i]) out.push_back(infos[i]);
    return out;
}

// The reference in `action`'s alias of `scene`'s quest (the NPC who answers).
NiPointer<TESObjectREFR> ActionActor(void *action, void *scene) {
    NiPointer<TESObjectREFR> ref;
    TESForm *quest = scene ? At<TESForm *>(scene, SCENE_QUEST) : nullptr;
    if (!quest) return ref;
    UInt32 handle = 0;
    UInt32 *at = AliasHandle(quest, &handle, At<UInt32>(action, ACTION_ALIAS));
    HandleRef(&ref, at ? at : &handle);
    return ref;
}

// `prompt` with its build-time tag "[Speech 25] " written as FNV writes it (FalloutNV.exe's "[%s", "%s %d/%d",
// "%s]  %s"): "[Speech 25]  text" when the player's value passes `check`, "[Speech 17/25]  text" when it fails.
std::string Tagged(const char *prompt, const Check &check, bool *failed) {
    std::string text(prompt ? prompt : "");
    size_t open = text.find_first_not_of(' '), close = text.find(']');
    size_t space = close == std::string::npos ? close : text.rfind(' ', close);
    if (open == std::string::npos || text[open] != '[' || space == std::string::npos || space <= open) return text;
    int value = int((*g_player)->actorValueOwner.GetValue(check.av));
    *failed = value < int(check.needed);
    std::string name = text.substr(open + 1, space - open - 1);
    size_t rest = text.find_first_not_of(' ', close + 1);
    char tag[128];
    if (*failed) snprintf(tag, sizeof(tag), "[%s %d/%u]  ", name.c_str(), value, check.needed);
    else snprintf(tag, sizeof(tag), "[%s %u]  ", name.c_str(), check.needed);
    return tag + (rest == std::string::npos ? std::string() : text.substr(rest));
}

// An option as listed: the prompt of `line` (the answer line that plays) when it has one, else the option's; tagged
// live with the skill check of that line, else of the option.
Option Listed(TESForm *info, TESForm *answer, TESForm *line) {
    const char *own = Prompt(line);
    Option option{info, answer, own && *own ? own : Prompt(info), At<UInt8>(info, INFO_SAID) != 0, false};
    auto check = g_checks.find(line->formID);
    check = check != g_checks.end() ? check : g_checks.find(info->formID);
    if (check != g_checks.end()) option.prompt = Tagged(option.prompt.c_str(), check->second, &option.failed);
    return option;
}

// How far each line of a menu got: lines, linked, passing their own conditions, answered (listed).
struct Census {
    UInt32 lines = 0, linked = 0, passing = 0, answered = 0;
    UInt32 failed = 0;  // the first linked line whose conditions fail, or whose answer has no passing line
};

// The linked options of `action` that pass for the player talking to `npc` and whose answer topic has a line.
std::vector<Option> ListOptions(void *action, TESObjectREFR *npc, Census *census) {
    std::vector<Option> out;
    TESObjectREFR *player = *g_player;
    for (UInt32 slot = 0; slot < SLOTS; slot++)
        for (TESForm *info : Infos(At<TESForm *>(action, ACTION_TOPICS + slot * sizeof(void *)))) {
            census->lines++;
            auto link = g_links.find(info->formID);
            TESForm *answer = link == g_links.end() ? nullptr : LookupFormByID(link->second);
            bool flag = false;
            if (!answer) continue;
            census->linked++;
            bool passes = Passes(info, &flag, player, npc);
            census->passing += passes;
            TESForm *line = passes ? Pick(answer, npc, player) : nullptr;
            if (!line) {
                census->failed = census->failed ? census->failed : info->formID;
                continue;
            }
            census->answered++;
            out.push_back(Listed(info, answer, line));
        }
    return out;
}

// Why a waiting menu lists none of ours: its scene, its NPC and how far its lines got.
void LogNoOptions(void *scene, TESObjectREFR *npc, const Census &census) {
    _MESSAGE("dialogue menu: none of ours in scene %08X with NPC %08X: %u lines, %u linked, %u pass, %u answered; "
             "first failing linked line %08X", reinterpret_cast<TESForm *>(scene)->formID, npc ? npc->formID : 0,
             census.lines, census.linked, census.passing, census.answered, census.failed);
}

// The running Player Dialogue action of the player's scene, waiting for a pick; null when there is none.
void *WaitingAction(void **scene) {
    PlayerCharacter *player = *g_player;
    void *action = g_running.load();
    *scene = g_runningScene.load();
    if (!player || !action || !*scene || player->GetCurrentScene() != *scene) return nullptr;
    return At<UInt32>(action, ACTION_OPTION) == NO_OPTION ? action : nullptr;
}

// A wheel step (ZoomIn / ZoomOut) while a Player Dialogue choice waits: the menu scrolls with it, not the camera.
bool WheelWhileChoosing(void *event) {
    void **name = (*reinterpret_cast<EventNameFn **>(event))[2](event);
    void *scene = nullptr;
    return name && (*name == *ZoomInName() || *name == *ZoomOutName()) && WaitingAction(&scene);
}

bool FirstPersonShould(void *state, void *event) {
    return !WheelWhileChoosing(event) && g_firstShould(state, event);
}

bool ThirdPersonShould(void *state, void *event) {
    return !WheelWhileChoosing(event) && g_thirdShould(state, event);
}

// Route a camera state's "should handle" (vtable slot 1) through `hook` when the slot still holds `vanilla`.
bool HookShould(uintptr_t vtable, uintptr_t vanilla, ShouldFn hook, ShouldFn *original) {
    auto *slot = reinterpret_cast<ShouldFn *>(vtable + sizeof(void *));
    if (uintptr_t(*slot) != vanilla) return false;
    *original = *slot;
    SafeWrite64(uintptr_t(slot), UInt64(hook));
    return true;
}

// Keep the wheel from the first- and third-person cameras while a choice waits.
bool HookWheel() {
    return HookShould(FIRST_PERSON_VTABLE.GetUIntPtr(), FIRST_PERSON_SHOULD.GetUIntPtr(), FirstPersonShould,
                      &g_firstShould) &&
           HookShould(THIRD_PERSON_VTABLE.GetUIntPtr(), THIRD_PERSON_SHOULD.GetUIntPtr(), ThirdPersonShould,
                      &g_thirdShould);
}

// Let the player say the picked option (vanilla) or not (ours: the NPC answers at once, as in FNV).
void PlayerSpeaks(bool on) {
    if (!g_speechPatch || g_playerSpeaks == on) return;
    UInt8 code[sizeof(SPEAKS)];
    std::memcpy(code, on ? SPEAKS : SILENT, sizeof(code));
    SafeWriteBuf(PLAYER_SPEAKS.GetUIntPtr(), code, sizeof(code));
    SafeWrite8(CAMERA_TO_PLAYER.GetUIntPtr(), on ? CAMERA_PLAYER : CAMERA_SPEAKER);
    g_playerSpeaks = on;
}

// The option picked through SelectNative when option `chosen` is ours (of `action`, unless null); false otherwise.
bool PickedOption(void *action, UInt32 chosen, Chosen *out) {
    std::lock_guard<std::mutex> hold(g_dialogueLock);
    if (chosen < FIRST_OURS || !g_chosen.action || (action && g_chosen.action != action) ||
        g_chosen.index != chosen - FIRST_OURS)
        return false;
    *out = g_chosen;
    return true;
}

// The player slot: our option's own INFO, marked said, which the player does not say.
TESForm *PlayerSlot(void *action, void *scene, TESObjectREFR *target, SInt32 option) {
    UInt32 chosen = At<UInt32>(action, ACTION_OPTION);
    PlayerSpeaks(chosen < FIRST_OURS);
    if (chosen < FIRST_OURS) return g_optionInfo(action, scene, target, option);
    Chosen picked;
    if (!PickedOption(action, chosen, &picked)) {
        _MESSAGE("dialogue menu: option %u was not picked through the menu; none taken", chosen);
        At<UInt32>(action, ACTION_OPTION) = NO_OPTION;
        return nullptr;
    }
    MarkSaid(picked.option.info);
    _MESSAGE("dialogue menu: picked %u, %08X '%s', answer topic %08X", picked.index, picked.option.info->formID,
             picked.option.prompt.c_str(), picked.option.answer->formID);
    return picked.option.info;
}

// The answer to our option `chosen` (of Player Dialogue action `owner`, unless null), said by `action`'s actor: its
// answer topic's first passing INFO, once.
TESForm *Answer(void *owner, void *action, void *scene, UInt32 chosen, const char *where) {
    Chosen picked;
    if (!PickedOption(owner, chosen, &picked) || picked.answered) return nullptr;
    NiPointer<TESObjectREFR> npc = ActionActor(action, scene);
    TESForm *info = npc ? Pick(picked.option.answer, npc, *g_player) : nullptr;
    if (info) {
        std::lock_guard<std::mutex> hold(g_dialogueLock);
        if (g_chosen.action == picked.action) g_chosen.answered = true;
    }
    _MESSAGE("dialogue menu: %s answers %u from topic %08X with %08X", where, picked.index,
             picked.option.answer->formID, info ? info->formID : 0);
    return info;
}

// The NPC slot of a Player Dialogue action.
TESForm *NpcSlot(void *action, void *scene, TESObjectREFR *target, SInt32 option) {
    UInt32 chosen = At<UInt32>(action, ACTION_OPTION);
    if (chosen < FIRST_OURS) return g_optionInfo(action, scene, target, option);
    return Answer(action, action, scene, chosen, "NPC slot");
}

// An NPC Response action after a Player Dialogue one: our option's answer when its NPC slot gave none.
TESForm *Response(void *action, void *scene) {
    UInt32 chosen = At<UInt32>(*g_player, PLAYER_RESPONSE);
    if (chosen < FIRST_OURS) return g_responseInfo(action, scene);
    return Answer(nullptr, action, scene, chosen, "NPC Response");
}

// Whether `actor` is "talking" by the test the run function waits on.
bool Talking(void *actor) {
    return actor && (*reinterpret_cast<TalkingFn **>(actor))[TALKING_SLOT](actor);
}

// While our picked option runs: each change in what the NPC slot waits on (0x415954), with the time since the pick.
void TraceWaits(void *action, void *scene) {
    PlayerCharacter *player = *g_player;
    if (!player || !g_pickedAt || g_chosen.action != action || g_chosen.answered) return;
    NiPointer<TESObjectREFR> npc = ActionActor(action, scene);
    UInt32 flags = At<UInt32>(action, ACTION_FLAGS);
    UInt32 waits = (flags & PLAYER_DONE ? 1 : 0) | (flags & NPC_SAID ? 2 : 0) | (Talking(player) ? 4 : 0) |
                   (At<UInt32>(player, PLAYER_NO_WAIT) & 2 ? 8 : 0) | (Talking(npc) ? 16 : 0);
    if (waits == g_lastWaits) return;
    g_lastWaits = waits;
    _MESSAGE("dialogue menu: +%llu ms: player line %s, NPC line %s, player talking %d (no-wait flag %d), NPC talking %d",
             GetTickCount64() - g_pickedAt, waits & 1 ? "done" : "pending", waits & 2 ? "said" : "not said",
             (waits & 4) != 0, (waits & 8) != 0, (waits & 16) != 0);
}

// A Player Dialogue action's run: remember it as the running one.
UInt64 Run(void *action, void *scene, void *third, void *fourth) {
    g_running = action;
    g_runningScene = scene;
    TraceWaits(action, scene);
    return g_run(action, scene, third, fourth);
}

// End the player's conversation as Papyrus Scene.Stop does, on the game's thread.
class LeaveTask : public ITaskDelegate {
public:
    void Run() override {
        PlayerCharacter *player = *g_player;
        BGSScene *scene = player ? player->GetCurrentScene() : nullptr;
        if (!scene) {
            _MESSAGE("dialogue menu: leave: the player is in no scene");
            return;
        }
        StopScene(scene);
        At<UInt32>(scene, SCENE_FLAGS) |= SCENE_STOPPING;
        _MESSAGE("dialogue menu: left the talk (stopped scene %08X)", reinterpret_cast<TESForm *>(scene)->formID);
    }
};

// The call at `site`'s target when it still calls `vanilla`; null otherwise.
template <class Fn>
Fn Target(uintptr_t site, uintptr_t vanilla) {
    return CallsTarget(site, vanilla) ? reinterpret_cast<Fn>(vanilla) : nullptr;
}

// ---- The menu's natives (f4se.plugins.F3NV in the menu's movie) ----

// GetDialogueOptions(): [{text, said, failed}] of the running action's options; [] when it has none of ours.
class GetOptionsNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        GFxMovieRoot *movie = args->movie->movieRoot;
        movie->CreateArray(args->result);
        void *scene = nullptr, *action = g_hooked ? WaitingAction(&scene) : nullptr;
        if (!action) return;
        std::lock_guard<std::mutex> hold(g_dialogueLock);
        ReadAllLinks();
        NiPointer<TESObjectREFR> npc = ActionActor(action, scene);
        Census census;
        g_menu.action = action;
        g_menu.options = npc ? ListOptions(action, npc, &census) : std::vector<Option>();
        if (g_menu.options.empty() && g_noneLogged != action) LogNoOptions(scene, npc, census);
        g_noneLogged = g_menu.options.empty() ? action : nullptr;
        for (UInt32 i = 0; i < g_menu.options.size(); i++) {
            const Option &o = g_menu.options[i];
            GFxValue entry, text, said(o.said), failed(o.failed);
            movie->CreateObject(&entry);
            movie->CreateString(&text, o.prompt.c_str());
            entry.SetMember("text", &text);
            entry.SetMember("said", &said);
            entry.SetMember("failed", &failed);
            args->result->PushBack(&entry);
            _MESSAGE("dialogue menu: option %u: %08X '%s' -> topic %08X%s", i, o.info->formID, o.prompt.c_str(),
                     o.answer->formID, o.said ? " (said)" : "");
        }
        if (!g_menu.options.empty()) _MESSAGE("dialogue menu: %u options listed", UInt32(g_menu.options.size()));
    }
};

// SelectDialogueOption(index): pick listed option `index`; false when it is not listed or the action has moved on.
class SelectNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        args->result->SetBool(false);
        if (args->numArgs < 1) return;
        UInt32 index = UInt32(Num(args->args[0]));
        void *scene = nullptr, *action = WaitingAction(&scene);
        {
            std::lock_guard<std::mutex> hold(g_dialogueLock);
            if (!action || action != g_menu.action || index >= g_menu.options.size()) return;
            g_chosen = {action, index, g_menu.options[index], false};
            g_pickedAt = GetTickCount64();
            g_lastWaits = ~0u;
        }
        SelectOption(*g_player, index + FIRST_OURS);
        args->result->SetBool(true);
    }
};

// LeaveDialogue(): end the talk (the menu's Tab, Esc and [Leave] when no option of ours is up).
class LeaveNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        args->result->SetBool(g_dialogueTasks != nullptr);
        if (g_dialogueTasks) g_dialogueTasks->AddTask(new LeaveTask);
    }
};

// The DialogueMenu running `movie` and its holder's shader target at `slot`; nulls when either is missing.
void *HolderTarget(GFxMovieView *movie, size_t slot, IMenu **menu) {
    *menu = *g_ui ? (*g_ui)->GetMenuByMovie(movie) : nullptr;
    void *target = *menu ? At<void *>(*menu, slot) : nullptr;
    return target && *static_cast<uintptr_t *>(target) == SHADER_TARGET_VTABLE.GetUIntPtr() ? target : nullptr;
}

// ShadeList(on): the game's translucent menu background behind the Question holder, where the list lives, on or
// off. A fill inside a HUD-colored holder draws opaque (its alpha only darkens it), so the backdrop comes from here.
class ShadeNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        bool on = args->numArgs > 0 && args->args[0].GetBool();
        IMenu *menu = nullptr;
        void *target = HolderTarget(args->movie, MENU_QUESTION_TARGET, &menu);
        if (target && on) EnableShadedBackground(target, MENU_NO_COLOR_BACKGROUND, FULL_QUAD);
        if (target && !on) At<UInt32>(target, TARGET_FX_FLAGS) &= ~FX_BACKGROUND_QUAD;
        if (!target) _MESSAGE("dialogue menu: no shader target for the list's background");
        args->result->SetBool(target != nullptr);
    }
};

// TintFailed(): the Negative holder, where the menu puts its failed skill checks, in the game's own speech-challenge
// Hard tint. The game re-tints the holders on each SetButtonText, so the menu calls this after them.
class TintFailedNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        IMenu *menu = nullptr;
        void *target = HolderTarget(args->movie, MENU_NEGATIVE_TARGET, &menu);
        if (target) TintChallenge(menu, target, CHALLENGE_HARD, false);
        else _MESSAGE("dialogue menu: no shader target for failed skill checks");
        args->result->SetBool(target != nullptr);
    }
};

// Log(text): a line from the menu in F3NV.log.
class LogNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        if (args->numArgs > 0 && args->args[0].IsString()) _MESSAGE("dialogue menu: %s", args->args[0].GetString());
    }
};

}  // namespace

bool RegisterDialogueMenu(GFxMovieView *view, GFxValue *plugin) {
    GFxMovieRoot *movie = view ? view->movieRoot : nullptr;
    if (!movie || !plugin) return false;
    RegisterFunction<GetOptionsNative>(plugin, movie, "GetDialogueOptions");
    RegisterFunction<SelectNative>(plugin, movie, "SelectDialogueOption");
    RegisterFunction<LogNative>(plugin, movie, "Log");
    RegisterFunction<LeaveNative>(plugin, movie, "LeaveDialogue");
    RegisterFunction<ShadeNative>(plugin, movie, "ShadeList");
    RegisterFunction<TintFailedNative>(plugin, movie, "TintFailed");
    return true;
}

bool HookDialogue(void *tasks) {
    g_dialogueTasks = static_cast<F4SETaskInterface *>(tasks);
    if (GetModuleHandleA("XDI.dll")) {
        _MESSAGE("dialogue menu: XDI.dll is loaded; leaving dialogue to XDI");
        return false;
    }
    g_optionInfo = Target<OptionInfoFn>(PLAYER_SLOT_CALL.GetUIntPtr(), OptionInfo.GetUIntPtr());
    bool npc = CallsTarget(NPC_SLOT_CALL.GetUIntPtr(), OptionInfo.GetUIntPtr());
    g_responseInfo = Target<ResponseFn>(RESPONSE_CALL.GetUIntPtr(), ResponseInfo.GetUIntPtr());
    auto *slot = reinterpret_cast<RunFn *>(PLAYER_DIALOGUE_VTABLE.GetUIntPtr() + RUN_SLOT * sizeof(void *));
    if (!g_optionInfo || !npc || !g_responseInfo) {
        _MESSAGE("dialogue menu: a call site no longer calls the vanilla function (player %d, NPC %d, response %d); "
                 "not hooked", g_optionInfo != nullptr, npc, g_responseInfo != nullptr);
        return false;
    }
    g_speechPatch = !std::memcmp(reinterpret_cast<void *>(PLAYER_SPEAKS.GetUIntPtr()), SPEAKS, sizeof(SPEAKS)) &&
                    *reinterpret_cast<UInt8 *>(CAMERA_TO_PLAYER.GetUIntPtr()) == CAMERA_PLAYER;
    g_hooked = g_branchTrampoline.Write5Call(PLAYER_SLOT_CALL.GetUIntPtr(), uintptr_t(PlayerSlot)) &&
               g_branchTrampoline.Write5Call(NPC_SLOT_CALL.GetUIntPtr(), uintptr_t(NpcSlot)) &&
               g_branchTrampoline.Write5Call(RESPONSE_CALL.GetUIntPtr(), uintptr_t(Response));
    if (g_hooked) {
        g_run = *slot;
        SafeWrite64(uintptr_t(slot), UInt64(&Run));
    }
    _MESSAGE("dialogue menu: %s, player line skip %s, wheel zoom %s",
             g_hooked ? "hooked" : "not hooked (no trampoline space)", g_speechPatch ? "ready" : "unavailable (code differs)",
             g_hooked && HookWheel() ? "off the camera while choosing" : "unchanged (code differs)");
    return g_hooked;
}

}  // namespace condition
