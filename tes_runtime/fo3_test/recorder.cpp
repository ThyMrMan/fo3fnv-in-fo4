// F3Recorder: the Fallout 3 side of the story-run answer key. A FOSE plugin,
// test-only and never shipped, that writes one timeline of what the opening
// does: cells, the actors in the player's cell (position, heading, package,
// AI procedure, sitting, talking, the line a SayTo is saying), the talking
// activators beside them, and every quest's running flag and stage.
//
// It is a spike: it measures which of these Fallout 3 lets a plugin read.
// Every read is guarded; a reader that faults is logged once and turned off,
// so a wrong layout shows in the timeline instead of crashing the game.
//
// Layouts and addresses come from the FOSE 1.3 beta 2 source (references\FOSE)
// and match only the two runtimes it supports: 1.7.0.3 and the German no-gore
// 1.7.0.3. The process and SayTo layouts come from JIP LN NVSE (New Vegas);
// they are what the timeline checks.
//
// Environment:
//   F3_RECORD       the timeline file (default: f3_timeline.log beside the exe)
//   F3_RECORD_MENU  console lines, ';'-separated, run once at the main menu
//   F3_RECORD_CELL  console lines run once the player is first in a cell
//
// See: docs/fork/fo4_story_tests.md#baseline

#include <windows.h>

#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

// ---------------------------------------------------------------------------
// FOSE's plugin ABI (PluginAPI.h, CommandTable.h)
// ---------------------------------------------------------------------------

struct FOSEInterface {
    std::uint32_t foseVersion;
    std::uint32_t runtimeVersion;
    std::uint32_t editorVersion;
    std::uint32_t isEditor;
    void* registerCommand;
    void* setOpcodeBase;
    void* (*QueryInterface)(std::uint32_t id);
};

struct PluginInfo {
    std::uint32_t infoVersion;
    const char* name;
    std::uint32_t version;
};

using EvalFn = bool (*)(void* thisObj, void* arg1, void* arg2, double* result);

struct CommandInfo {
    const char* longName;
    const char* shortName;
    std::uint32_t opcode;
    const char* helpText;
    std::uint16_t needsParent;
    std::uint16_t numParams;
    void* params;
    void* execute;
    void* parse;
    EvalFn eval;
    std::uint32_t flags;
};

struct FOSECommandTableInterface {
    std::uint32_t version;
    const CommandInfo* (*Start)();
    const CommandInfo* (*End)();
    const CommandInfo* (*GetByOpcode)(std::uint32_t opcode);
    const CommandInfo* (*GetByName)(const char* name);
};

constexpr std::uint32_t kInterfaceCommandTable = 5;
constexpr std::uint32_t kRuntime17 = 0x01070030;
constexpr std::uint32_t kRuntime17NoGore = 0x01070031;
constexpr std::uint32_t kFose13 = 0x01030000;

// ---------------------------------------------------------------------------
// Fallout 3 layouts (FOSE GameForms.h / GameObjects.h / GameData.h)
// ---------------------------------------------------------------------------

constexpr std::uint8_t kTypeTalkingActivator = 0x16;
constexpr std::uint8_t kTypeCell = 0x39;
constexpr std::uint8_t kTypeACHR = 0x3B;
constexpr std::uint8_t kTypeACRE = 0x3C;
constexpr std::uint8_t kTypeTopic = 0x45;
constexpr std::uint8_t kTypeInfo = 0x46;
constexpr std::uint8_t kTypeQuest = 0x47;
constexpr std::uint8_t kTypePackage = 0x49;

constexpr std::uintptr_t kFormType = 0x04;
constexpr std::uintptr_t kFormId = 0x0C;
constexpr std::uintptr_t kRefBase = 0x1C;
constexpr std::uintptr_t kRefRotZ = 0x28;
constexpr std::uintptr_t kRefPos = 0x2C;
constexpr std::uintptr_t kRefCell = 0x3C;
constexpr std::uintptr_t kRefExtraHead = 0x44;  // ExtraDataList at 0x40, its first BSExtraData at +4
constexpr std::uintptr_t kActorProcess = 0x60;  // MobileObject::unk60 (HighProcess*)
constexpr std::uintptr_t kProcessPackage = 0x04;  // BaseProcess::currentPackage.package (JIP)
constexpr std::uintptr_t kCellObjects = 0xAC;
constexpr std::uintptr_t kPlayerTopic = 0x604;
constexpr std::uintptr_t kDataQuests = 0xD4;
constexpr std::uintptr_t kQuestRunning = 0x3C;
constexpr std::uintptr_t kQuestStage = 0x60;
constexpr std::uintptr_t kQuestEditorId = 0x64;  // String {char*, UInt16 len, UInt16 size}
constexpr std::uint8_t kExtraSayTo = 0x75;  // ExtraSayToTopicInfo, 0x18 in FO3: INFO, topic, quest from 0C, by type

struct Globals {
    std::uintptr_t player;
    std::uintptr_t dataHandler;
};

// The console's own run path in 1.7.0.3 English (ConsoleManager's line handler
// at 0x62B620, matched call for call against New Vegas's at 0x71C3A4): a
// temporary Script is constructed, marked temporary, given the text and run in
// the ConsoleManager's script context (its first field, as in NVSE: both keep
// COFileName at +0x810). FOSE 1.3 beta 2 leaves its console interface out.
struct ConsoleCalls {
    std::uintptr_t construct, markTemporary, setText, run, destruct, manager;
};
constexpr ConsoleCalls kConsole17{0x517010, 0x4553B0, 0x517450, 0x518D30, 0x519960, 0x1075D18};
constexpr std::size_t kScriptSize = 0x54;  // FOSE GameForms.h: STATIC_ASSERT(sizeof(Script) == 0x54)
using ThisCall = void(__thiscall*)(void*);
using SetTextCall = void(__thiscall*)(void*, const char*);
using RunCall = bool(__thiscall*)(void*, void*, int, void*);

// ---------------------------------------------------------------------------
// Guarded reads: a bad pointer returns false instead of faulting
// ---------------------------------------------------------------------------

bool ReadBytes(std::uintptr_t addr, void* out, std::size_t size) {
    if (addr < 0x10000) return false;
    __try {
        std::memcpy(out, reinterpret_cast<const void*>(addr), size);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

std::uintptr_t Ptr(std::uintptr_t addr) {
    std::uintptr_t value = 0;
    return ReadBytes(addr, &value, sizeof value) ? value : 0;
}

std::uint8_t TypeOf(std::uintptr_t form) {
    std::uint8_t type = 0;
    return ReadBytes(form + kFormType, &type, 1) ? type : 0;
}

std::uint32_t IdOf(std::uintptr_t form) {
    std::uint32_t id = 0;
    return form && ReadBytes(form + kFormId, &id, sizeof id) ? id : 0;
}

// The form at `form` when it is of `type`, else 0.
std::uintptr_t Typed(std::uintptr_t form, std::uint8_t type) {
    return form && TypeOf(form) == type ? form : 0;
}

bool CallEval(EvalFn fn, std::uintptr_t ref, std::uintptr_t arg, double* out) {
    __try {
        return fn(reinterpret_cast<void*>(ref), reinterpret_cast<void*>(arg), nullptr, out);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// Each item of the tList whose first node sits at `node`.
std::vector<std::uintptr_t> ListItems(std::uintptr_t node) {
    std::vector<std::uintptr_t> items;
    for (int guard = 0; node && guard < 200000; ++guard) {
        std::uintptr_t pair[2] = {0, 0};
        if (!ReadBytes(node, pair, sizeof pair)) break;
        if (pair[0]) items.push_back(pair[0]);
        node = pair[1];
    }
    return items;
}

std::string EditorId(std::uintptr_t quest) {
    struct { std::uintptr_t data; std::uint16_t len, size; } str{};
    char text[129] = {};
    if (!ReadBytes(quest + kQuestEditorId, &str, sizeof str) || !str.data) return "";
    std::size_t len = str.len < 128 ? str.len : 128;
    return ReadBytes(str.data, text, len) ? std::string(text, len) : "";
}

// ---------------------------------------------------------------------------
// The timeline
// ---------------------------------------------------------------------------

FILE* g_out = nullptr;
DWORD g_startTick = 0;

void Emit(const char* format, ...) {
    if (!g_out) return;
    std::fprintf(g_out, "%lu|", static_cast<unsigned long>(GetTickCount() - g_startTick));
    va_list args;
    va_start(args, format);
    std::vfprintf(g_out, format, args);
    va_end(args);
    std::fputc('\n', g_out);
}

// A reader that faulted once is reported and switched off.
struct Reader {
    const char* name;
    bool off;
};

bool Usable(Reader& reader, bool ok) {
    if (!ok && !reader.off) {
        reader.off = true;
        Emit("fault|%s", reader.name);
    }
    return !reader.off;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

struct ActorState {
    std::uint32_t base = 0, package = 0, info = 0;
    int procedure = -1, sitting = -1, talking = -1;
    int pos[4] = {0, 0, 0, 0};
    DWORD posTick = 0;
    bool seen = false;
};

struct QuestState {
    int running = -1, stage = -1;
};

Globals g_globals{};
const ConsoleCalls* g_console = nullptr;
EvalFn g_getSitting = nullptr, g_isTalking = nullptr, g_getProcedure = nullptr, g_getStage = nullptr;
Reader g_readPackage{"package", false}, g_readSitting{"GetSitting", false}, g_readTalking{"IsTalking", false};
Reader g_readProcedure{"GetCurrentAIProcedure", false}, g_readStage{"GetStage", false};
std::unordered_map<std::uint32_t, ActorState> g_actors;
std::unordered_map<std::uintptr_t, QuestState> g_quests;
std::uint32_t g_cell = 0, g_topic = 0;
bool g_menuRan = false, g_cellRan = false;
DWORD g_menuSince = 0;

// Runs one console line the way the console does; false when it faulted or had no context.
bool RunLine(const char* line) {
    std::uintptr_t manager = Ptr(g_console->manager);
    void* context = reinterpret_cast<void*>(manager ? Ptr(manager) : 0);
    if (!context) return false;
    alignas(8) unsigned char script[kScriptSize + 0x40] = {};
    __try {
        reinterpret_cast<ThisCall>(g_console->construct)(script);
        reinterpret_cast<ThisCall>(g_console->markTemporary)(script);
        reinterpret_cast<SetTextCall>(g_console->setText)(script, line);
        reinterpret_cast<RunCall>(g_console->run)(script, context, 1, nullptr);
        reinterpret_cast<ThisCall>(g_console->destruct)(script);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

void RunLines(const char* env) {
    const char* text = std::getenv(env);
    if (!text) return;
    if (!g_console) {
        Emit("fault|no console path for this runtime");
        return;
    }
    std::string all(text), line;
    for (std::size_t start = 0; start <= all.size();) {
        std::size_t end = all.find(';', start);
        line = all.substr(start, end == std::string::npos ? std::string::npos : end - start);
        if (!line.empty()) {
            Emit("cmd|%s", line.c_str());
            std::fflush(g_out);
            if (!RunLine(line.c_str())) Emit("fault|console line %s", line.c_str());
        }
        if (end == std::string::npos) break;
        start = end + 1;
    }
}

int EvalInt(EvalFn fn, Reader& reader, std::uintptr_t ref, std::uintptr_t arg) {
    double value = 0;
    if (!fn || reader.off) return -1;
    return Usable(reader, CallEval(fn, ref, arg, &value)) ? static_cast<int>(value) : -1;
}

// The INFO and topic a SayTo is saying on `ref`, from its ExtraSayToTopicInfo.
void SayTo(std::uintptr_t ref, std::uintptr_t* info, std::uintptr_t* topic) {
    *info = *topic = 0;
    std::uintptr_t extra = Ptr(ref + kRefExtraHead);
    for (int guard = 0; extra && guard < 256; ++guard) {
        std::uint8_t type = 0;
        if (!ReadBytes(extra + 4, &type, 1)) return;
        if (type == kExtraSayTo) {
            for (std::uintptr_t field = 0x0C; field <= 0x14; field += 4) {
                std::uintptr_t form = Ptr(extra + field);
                if (!*info) *info = Typed(form, kTypeInfo);
                if (!*topic) *topic = Typed(form, kTypeTopic);
            }
            return;
        }
        extra = Ptr(extra + 8);
    }
}

std::uint32_t PackageOf(std::uintptr_t ref) {
    if (g_readPackage.off) return 0;
    std::uintptr_t process = Ptr(ref + kActorProcess);
    std::uintptr_t package = process ? Ptr(process + kProcessPackage) : 0;
    Usable(g_readPackage, !package || TypeOf(package) == kTypePackage);
    return g_readPackage.off ? 0 : IdOf(package);
}

void Changed(const char* kind, std::uint32_t ref, int& held, int now) {
    if (now != held) {
        held = now;
        Emit("%s|%08X|%d", kind, ref, now);
    }
}

void SamplePosition(std::uintptr_t ref, std::uint32_t id, ActorState& state) {
    float pos[3] = {0, 0, 0}, rotZ = 0;
    if (!ReadBytes(ref + kRefPos, pos, sizeof pos) || !ReadBytes(ref + kRefRotZ, &rotZ, sizeof rotZ)) return;
    int now[4] = {static_cast<int>(pos[0]), static_cast<int>(pos[1]), static_cast<int>(pos[2]),
                  static_cast<int>(std::lround(rotZ * 57.29578f)) % 360};
    DWORD tick = GetTickCount();
    if (std::memcmp(now, state.pos, sizeof now) == 0 || tick - state.posTick < 500) return;
    std::memcpy(state.pos, now, sizeof now);
    state.posTick = tick;
    Emit("pos|%08X|%d|%d|%d|%d", id, now[0], now[1], now[2], now[3]);
}

void SampleActor(std::uintptr_t ref, bool isActor) {
    std::uint32_t id = IdOf(ref);
    ActorState& state = g_actors[id];
    if (!state.seen) {
        state.seen = true;
        state.base = IdOf(Ptr(ref + kRefBase));
        Emit("actor|%08X|%08X", id, state.base);
    }
    SamplePosition(ref, id, state);
    std::uintptr_t info = 0, topic = 0;
    SayTo(ref, &info, &topic);
    if (IdOf(info) != state.info) {
        state.info = IdOf(info);
        Emit("sayto|%08X|%08X|%08X", id, state.info, IdOf(topic));
    }
    if (!isActor) return;
    Changed("talk", id, state.talking, EvalInt(g_isTalking, g_readTalking, ref, 0));
    std::uint32_t package = PackageOf(ref);
    if (package != state.package) {
        state.package = package;
        Emit("pkg|%08X|%08X", id, package);
    }
    Changed("proc", id, state.procedure, EvalInt(g_getProcedure, g_readProcedure, ref, 0));
    Changed("sit", id, state.sitting, EvalInt(g_getSitting, g_readSitting, ref, 0));
}

void SampleCell(std::uintptr_t player) {
    std::uintptr_t cell = Typed(Ptr(player + kRefCell), kTypeCell);
    if (IdOf(cell) != g_cell) {
        g_cell = IdOf(cell);
        Emit("cell|%08X", g_cell);
    }
    SampleActor(player, true);
    for (std::uintptr_t ref : ListItems(cell ? cell + kCellObjects : 0)) {
        std::uint8_t type = TypeOf(ref);
        if (type == kTypeACHR || type == kTypeACRE)
            SampleActor(ref, true);
        else if (TypeOf(Ptr(ref + kRefBase)) == kTypeTalkingActivator)
            SampleActor(ref, false);
    }
    std::uint32_t topic = IdOf(Typed(Ptr(player + kPlayerTopic), kTypeTopic));
    if (topic != g_topic) {
        g_topic = topic;
        Emit("ptopic|%08X", topic);
    }
}

int QuestStage(std::uintptr_t quest) {
    if (g_getStage) return EvalInt(g_getStage, g_readStage, 0, quest);
    std::uint8_t stage = 0;
    return ReadBytes(quest + kQuestStage, &stage, 1) ? stage : -1;
}

void SampleQuests() {
    std::uintptr_t data = Ptr(g_globals.dataHandler);
    for (std::uintptr_t quest : ListItems(data ? data + kDataQuests : 0)) {
        if (TypeOf(quest) != kTypeQuest) continue;
        QuestState& state = g_quests[quest];
        std::uint8_t flags = 0;
        int running = ReadBytes(quest + kQuestRunning, &flags, 1) ? flags & 1 : -1;
        int stage = QuestStage(quest);
        if (running == state.running && stage == state.stage) continue;
        std::string name = EditorId(quest);
        if (running != state.running) Emit("quest|%s|%08X|%d", name.c_str(), IdOf(quest), running);
        if (stage != state.stage) Emit("stage|%s|%08X|%d", name.c_str(), IdOf(quest), stage);
        state.running = running;
        state.stage = stage;
    }
}

void Tick() {
    std::uintptr_t player = Ptr(g_globals.player);
    if (!player || !Ptr(player + kRefCell)) {
        if (!g_menuSince) {
            g_menuSince = GetTickCount();
            Emit("menu|player %08X", static_cast<unsigned>(player));
            std::fflush(g_out);
        }
        if (!g_menuRan && GetTickCount() - g_menuSince > 3000) {
            g_menuRan = true;
            RunLines("F3_RECORD_MENU");
            std::fflush(g_out);
        }
        return;
    }
    SampleCell(player);
    SampleQuests();
    if (!g_cellRan) {
        g_cellRan = true;
        RunLines("F3_RECORD_CELL");
    }
    std::fflush(g_out);
}

// ---------------------------------------------------------------------------
// The tick: the game's PeekMessageA, between frames on the main thread. The
// exe calls it through its import table only from WinMain's message loop.
// ---------------------------------------------------------------------------

using PeekFn = BOOL(WINAPI*)(LPMSG, HWND, UINT, UINT, UINT);
PeekFn g_realPeek = nullptr;
DWORD g_lastTick = 0;
bool g_inTick = false;

BOOL WINAPI PeekHook(LPMSG msg, HWND wnd, UINT first, UINT last, UINT remove) {
    DWORD now = GetTickCount();
    if (!g_inTick && now - g_lastTick >= 100) {
        g_inTick = true;
        g_lastTick = now;
        Tick();
        g_inTick = false;
    }
    return g_realPeek(msg, wnd, first, last, remove);
}

// The exe's import slot for `dll`!`name`, or null.
void** ImportSlot(const char* dll, const char* name) {
    auto base = reinterpret_cast<std::uint8_t*>(GetModuleHandleA(nullptr));
    auto dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    auto nt = reinterpret_cast<IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
    auto dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    for (auto imp = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + dir.VirtualAddress); imp->Name; ++imp) {
        if (_stricmp(reinterpret_cast<char*>(base + imp->Name), dll) != 0) continue;
        auto names = reinterpret_cast<IMAGE_THUNK_DATA*>(base + imp->OriginalFirstThunk);
        auto slots = reinterpret_cast<void**>(base + imp->FirstThunk);
        for (int i = 0; names[i].u1.AddressOfData; ++i) {
            if (IMAGE_SNAP_BY_ORDINAL(names[i].u1.Ordinal)) continue;
            auto byName = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base + names[i].u1.AddressOfData);
            if (std::strcmp(reinterpret_cast<char*>(byName->Name), name) == 0) return &slots[i];
        }
    }
    return nullptr;
}

bool HookPeek() {
    void** slot = ImportSlot("user32.dll", "PeekMessageA");
    DWORD old = 0;
    if (!slot || !VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) return false;
    g_realPeek = reinterpret_cast<PeekFn>(*slot);
    *slot = reinterpret_cast<void*>(&PeekHook);
    VirtualProtect(slot, sizeof *slot, old, &old);
    return true;
}

EvalFn Eval(FOSECommandTableInterface* table, const char* name) {
    const CommandInfo* info = table ? table->GetByName(name) : nullptr;
    if (!info || !info->eval) Emit("fault|no eval for %s", name);
    return info ? info->eval : nullptr;
}

void OpenTimeline() {
    char path[MAX_PATH] = {};
    const char* chosen = std::getenv("F3_RECORD");
    if (!chosen) {
        GetModuleFileNameA(nullptr, path, MAX_PATH);
        char* slash = std::strrchr(path, '\\');
        std::strcpy(slash ? slash + 1 : path, "f3_timeline.log");
        chosen = path;
    }
    g_out = std::fopen(chosen, "w");
    g_startTick = GetTickCount();
}

}  // namespace

extern "C" {

__declspec(dllexport) bool FOSEPlugin_Query(const FOSEInterface* fose, PluginInfo* info) {
    info->infoVersion = 1;
    info->name = "F3Recorder";
    info->version = 1;
    bool runtime = fose->runtimeVersion == kRuntime17 || fose->runtimeVersion == kRuntime17NoGore;
    return !fose->isEditor && runtime && fose->foseVersion >= kFose13;
}

__declspec(dllexport) bool FOSEPlugin_Load(const FOSEInterface* fose) {
    bool noGore = fose->runtimeVersion == kRuntime17NoGore;
    g_globals = noGore ? Globals{0x01077104, 0x01069DCC} : Globals{0x0107A104, 0x0106CDCC};
    OpenTimeline();
    Emit("start|runtime %08X|fose %08X", fose->runtimeVersion, fose->foseVersion);
    g_console = noGore ? nullptr : &kConsole17;
    auto table = static_cast<FOSECommandTableInterface*>(fose->QueryInterface(kInterfaceCommandTable));
    g_getSitting = Eval(table, "GetSitting");
    g_isTalking = Eval(table, "IsTalking");
    g_getProcedure = Eval(table, "GetCurrentAIProcedure");
    g_getStage = Eval(table, "GetStage");
    if (!HookPeek()) Emit("fault|no PeekMessageA import");
    std::fflush(g_out);
    return true;
}

}  // extern "C"
