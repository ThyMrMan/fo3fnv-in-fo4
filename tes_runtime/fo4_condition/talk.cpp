// F3NV: an FNV Goodbye line ends the player's talk when it ends (docs/fork/fo4_pipeline.md#goodbye-ends-talk).
//
// Fallout4.exe 1.11.240. When a scene ends, the game ends the player's talk (MenuTopicManager, 0x30E6E50) through
// its end-the-talk function 0xBB0720 (calls at 0x637693 and 0x637A06), but that function does nothing while the
// player's own current scene is another one. Our answer and goodbye scenes hold only the NPC, and a line flagged End
// Running Scene (every converted Goodbye) skips the talk's other exit (0xC7C0CA, 0x4FF08A), so the talk stays up
// until the speaker's dialogue timer runs out (about 15 s, 2026-11-12), and the game holds a quest that a result
// script starts until then. The speaker's own update ends a talk with 0xBB0720(manager, speaker, the player's
// current scene, true) (0xC7CB1B); the native F3NV_Talk.EndTalk, run by a Goodbye line's End fragment, makes that
// call on the game's thread, unless the player is in another live scene (a talk the result script started).
#include "condition.h"

#include "f4se/GameForms.h"
#include "f4se/GameReferences.h"
#include "f4se/GameThreads.h"
#include "f4se/PapyrusArgs.h"
#include "f4se/PapyrusNativeFunctions.h"
#include "f4se/PluginAPI.h"

namespace condition {

namespace {

const char *TALK_SCRIPT = "F3NV_Talk";

// The game's end-the-talk function: the talk's speaker, the player's current scene (the call does nothing when it is
// another scene than the player's), and whether the dialogue menu closes too.
using EndTalkFn = void (*)(void *manager, TESObjectREFR *speaker, BGSScene *scene, bool closeMenu);
// A reference handle's reference.
using HandleFn = NiPointer<TESObjectREFR> *(*)(NiPointer<TESObjectREFR> *out, UInt32 *handle);

RelocPtr<void *> TopicManager(0x30E6E50);
RelocAddr<EndTalkFn> EndTalkNative(0xBB0720);
RelocAddr<HandleFn> HandleRef(0x21E550);

// MenuTopicManager: the speaker's handle, and whether a talk with the player runs. BGSScene: its run flags, playing
// in bit 0 (Papyrus Scene.IsPlaying, 0x111AD10).
const size_t MANAGER_SPEAKER = 0x14, MANAGER_TALKING = 0x4C, SCENE_RUN_FLAGS = 0x28;
const UInt32 SCENE_PLAYING = 1;

F4SETaskInterface *g_talkTasks = nullptr;

template <class T>
T &Field(void *base, size_t offset) {
    return *reinterpret_cast<T *>(static_cast<UInt8 *>(base) + offset);
}

UInt32 FormIDOf(void *form) {
    return form ? static_cast<TESForm *>(form)->formID : 0;
}

bool Playing(BGSScene *scene) {
    return scene && (Field<UInt32>(scene, SCENE_RUN_FLAGS) & SCENE_PLAYING);
}

// End the talk with the speaker `speakerID` on the game's thread, when it still runs with that speaker and the player
// is in no live scene other than the goodbye line's `goodbyeID`.
class EndTalkTask : public ITaskDelegate {
public:
    EndTalkTask(UInt32 speakerID, UInt32 goodbyeID) : speakerID_(speakerID), goodbyeID_(goodbyeID) {}

    void Run() override {
        void *manager = *TopicManager;
        PlayerCharacter *player = *g_player;
        if (!manager || !player || !Field<UInt8>(manager, MANAGER_TALKING)) {
            _MESSAGE("goodbye of %08X: no talk runs", speakerID_);
            return;
        }
        UInt32 handle = Field<UInt32>(manager, MANAGER_SPEAKER);
        NiPointer<TESObjectREFR> speaker;
        HandleRef(&speaker, &handle);
        BGSScene *scene = player->GetCurrentScene();
        UInt32 sceneID = FormIDOf(scene);
        if (!speaker || speaker->formID != speakerID_ || (Playing(scene) && sceneID != goodbyeID_)) {
            _MESSAGE("goodbye of %08X: talk left up (speaker %08X, player scene %08X playing %d, goodbye scene %08X)",
                     speakerID_, FormIDOf(speaker), sceneID, Playing(scene), goodbyeID_);
            return;
        }
        EndTalkNative(manager, speaker, scene, true);
        _MESSAGE("goodbye of %08X: talk ended (player scene %08X playing %d, goodbye scene %08X; talk runs %d)",
                 speakerID_, sceneID, Playing(scene), goodbyeID_, Field<UInt8>(manager, MANAGER_TALKING));
    }

private:
    UInt32 speakerID_, goodbyeID_;
};

// Papyrus: `speaker`'s Goodbye line has ended; end its talk with the player on the game's next task.
void EndTalk(StaticFunctionTag *, TESObjectREFR *speaker) {
    if (!speaker || !g_talkTasks) return;
    g_talkTasks->AddTask(new EndTalkTask(speaker->formID, FormIDOf(speaker->GetCurrentScene())));
}

}  // namespace

void RegisterTalk(VirtualMachine *vm, void *tasks) {
    g_talkTasks = static_cast<F4SETaskInterface *>(tasks);
    vm->RegisterFunction(
        new NativeFunction1<StaticFunctionTag, void, TESObjectREFR *>("EndTalk", TALK_SCRIPT, EndTalk, vm));
}

}  // namespace condition
