// F3NV: our dialogue menu in place of XDI (docs/fork/fo4_dialogue_menu_plan.md#test-build).
//
// An option is a player INFO that names an answer topic (the links in Data\F4SE\Plugins\F3NV_Menus\*.txt); its
// answer is that topic's first passing INFO, chosen by the engine's own picker, so nothing pairs options and answers
// by position. The menu movie (Interface/DialogueMenu.swf, built by fo4_import.dialogue_menu) asks for the running
// Player Dialogue action's options and picks one as option index + 5. The engine then asks three call sites for the
// INFOs of the picked option; index 5 and up are ours, below 5 go to the engine's functions as before.
//
// Fallout4.exe 1.11.240, read in Fallout4.exe.unpacked.exe; the plan's engine table lists each address.
#include "condition.h"

#include "f4se/GameData.h"
#include "f4se/GameReferences.h"
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

RelocAddr<OptionInfoFn> OptionInfo(0x416600);
RelocAddr<ResponseFn> ResponseInfo(0x414180);
RelocAddr<PickFn> Pick(0x698DB0);
RelocAddr<PassesFn> Passes(0x69F490);
RelocAddr<PromptFn> Prompt(0x69E740);
RelocAddr<SaidFn> MarkSaid(0x69F8D0);
RelocAddr<AliasFn> AliasHandle(0x671FA0);
RelocAddr<HandleFn> HandleRef(0x21E550);
RelocAddr<SelectFn> SelectOption(0xD76130);
// The player-slot and NPC-slot calls to OptionInfo (in 0x415280), and the NPC Response call to ResponseInfo.
RelocAddr<uintptr_t> PLAYER_SLOT_CALL(0x41568A), NPC_SLOT_CALL(0x415A21), RESPONSE_CALL(0x413DA8);
RelocAddr<uintptr_t> PLAYER_DIALOGUE_VTABLE(0x2488978);
const size_t RUN_SLOT = 21;
// The player starting to say the picked option (`mov rcx, rax` before the call at 0x4158E9); `jmp 0x4158F2` takes
// the said path without saying it. The camera's switch to the player (its 1 at 0x832665 + 7; 2 keeps it on the NPC).
RelocAddr<uintptr_t> PLAYER_SPEAKS(0x4158D2), CAMERA_TO_PLAYER(0x83266C);
const UInt8 SPEAKS[] = {0x48, 0x8B, 0xC8}, SILENT[] = {0xEB, 0x1E, 0x90};
const UInt8 CAMERA_PLAYER = 1, CAMERA_SPEAKER = 2;

// ---- Engine layouts ----
// BGSScene: its quest. Scene action: its alias, its four player topics, its chosen option (4: none).
const size_t SCENE_QUEST = 0xA8, ACTION_ALIAS = 0x08, ACTION_TOPICS = 0x20, ACTION_OPTION = 0xE0;
// TESTopic: its INFOs, their order (u16 head at +2, next of INFO i at 4 * i + 4), their count. TESTopicInfo: said.
const size_t TOPIC_INFOS = 0x50, TOPIC_ORDER = 0x58, TOPIC_COUNT = 0x60, INFO_SAID = 0x43;
// PlayerCharacter: the chosen response an NPC Response action answers.
const size_t PLAYER_RESPONSE = 0xD3C;
const UInt32 NO_OPTION = 4, FIRST_OURS = 5, SLOTS = 4;
const UInt16 END = 0xFFFF;
const char *LINKS = "Data\\F4SE\\Plugins\\F3NV_Menus\\";

template <class T>
T &At(void *base, size_t offset) {
    return *reinterpret_cast<T *>(static_cast<UInt8 *>(base) + offset);
}

struct Option {
    TESForm *info;
    TESForm *answer;
    std::string prompt;
    bool said;
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
// Option INFO FormID -> answer topic FormID, read once the data has loaded.
std::unordered_map<UInt32, UInt32> g_links;
bool g_linksRead = false;
// The Player Dialogue action the engine ran last, and its scene.
std::atomic<void *> g_running{nullptr}, g_runningScene{nullptr};
OptionInfoFn g_optionInfo = nullptr;
ResponseFn g_responseInfo = nullptr;
RunFn g_run = nullptr;
bool g_hooked = false, g_speechPatch = false, g_playerSpeaks = true;

// `plugin`'s object id `id` (hex) as a loaded FormID; 0 when the plugin is not loaded.
UInt32 Resolve(const std::string &plugin, const std::string &id) {
    const ModInfo *mod = *g_dataHandler ? (*g_dataHandler)->LookupModByName(plugin.c_str()) : nullptr;
    return mod && mod->IsActive() ? mod->GetFormID(std::strtoul(id.c_str(), nullptr, 16)) : 0;
}

// One links file: lines of option plugin, option id, answer plugin, answer id, tab-separated; # starts a comment.
void ReadLinks(const std::string &path) {
    std::ifstream in(path);
    std::string line;
    UInt32 read = 0, kept = 0;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::vector<std::string> f;
        for (size_t at = 0, tab; at <= line.size(); at = tab + 1) {
            tab = line.find('\t', at);
            tab = tab == std::string::npos ? line.size() : tab;
            f.push_back(line.substr(at, tab - at));
        }
        if (f.size() < 4) continue;
        read++;
        UInt32 option = Resolve(f[0], f[1]), answer = Resolve(f[2], f[3]);
        TESForm *info = option ? LookupFormByID(option) : nullptr, *topic = answer ? LookupFormByID(answer) : nullptr;
        if (info && topic && info->formType == kFormType_INFO && topic->formType == kFormType_DIAL)
            g_links[option] = answer, kept++;
    }
    _MESSAGE("dialogue menu: %s: %u links, %u resolved", path.c_str(), read, kept);
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
    do ReadLinks(std::string(LINKS) + found.cFileName);
    while (FindNextFileA(find, &found));
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

// The linked options of `action` that pass for the player talking to `npc` and whose answer topic has a line.
std::vector<Option> ListOptions(void *action, TESObjectREFR *npc) {
    std::vector<Option> out;
    TESObjectREFR *player = *g_player;
    for (UInt32 slot = 0; slot < SLOTS; slot++)
        for (TESForm *info : Infos(At<TESForm *>(action, ACTION_TOPICS + slot * sizeof(void *)))) {
            auto link = g_links.find(info->formID);
            TESForm *answer = link == g_links.end() ? nullptr : LookupFormByID(link->second);
            bool flag = false;
            if (!answer || !Passes(info, &flag, player, npc) || !Pick(answer, npc, player)) continue;
            out.push_back({info, answer, Prompt(info), At<UInt8>(info, INFO_SAID) != 0});
        }
    return out;
}

// The running Player Dialogue action of the player's scene, waiting for a pick; null when there is none.
void *WaitingAction(void **scene) {
    PlayerCharacter *player = *g_player;
    void *action = g_running.load();
    *scene = g_runningScene.load();
    if (!player || !action || !*scene || player->GetCurrentScene() != *scene) return nullptr;
    return At<UInt32>(action, ACTION_OPTION) == NO_OPTION ? action : nullptr;
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

// A Player Dialogue action's run: remember it as the running one.
UInt64 Run(void *action, void *scene, void *third, void *fourth) {
    g_running = action;
    g_runningScene = scene;
    return g_run(action, scene, third, fourth);
}

// The call at `site`'s target when it still calls `vanilla`; null otherwise.
template <class Fn>
Fn Target(uintptr_t site, uintptr_t vanilla) {
    return CallsTarget(site, vanilla) ? reinterpret_cast<Fn>(vanilla) : nullptr;
}

// ---- The menu's natives (f4se.plugins.F3NV in the menu's movie) ----

// GetDialogueOptions(): [{text, said}] of the running action's options; [] when it has none of ours.
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
        g_menu.action = action;
        g_menu.options = npc ? ListOptions(action, npc) : std::vector<Option>();
        for (UInt32 i = 0; i < g_menu.options.size(); i++) {
            const Option &o = g_menu.options[i];
            GFxValue entry, text, said(o.said);
            movie->CreateObject(&entry);
            movie->CreateString(&text, o.prompt.c_str());
            entry.SetMember("text", &text);
            entry.SetMember("said", &said);
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
        }
        SelectOption(*g_player, index + FIRST_OURS);
        args->result->SetBool(true);
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
    return true;
}

bool HookDialogue() {
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
    _MESSAGE("dialogue menu: %s, player line skip %s", g_hooked ? "hooked" : "not hooked (no trampoline space)",
             g_speechPatch ? "ready" : "unavailable (code differs)");
    return g_hooked;
}

}  // namespace condition
