// F3NVTest -- the test instance's control channel. Test-only, never shipped.
//
// A named pipe (F3NV_TEST_PIPE, default \\.\pipe\f3nv_test) speaking the same
// JSON-line protocol as tools/live/game_bridge.py's Bridge client:
//   {"id":1,"cmd":"console","args":{"command":"coc QASmoke","ref":"00000014"}}
//   -> {"id":1,"ok":true,"result":{"output":"..."}}
// Every game call runs on the main thread through F4SE's task queue.
// See: docs/fork/fo4_story_tests.md#instance

#include "json.h"

#include <windows.h>

#include <atomic>
#include <cstdlib>
#include <future>
#include <iterator>
#include <sstream>
#include <memory>
#include <thread>

using JValue = tesruntime::Json;

namespace
{
    constexpr DWORD kMainThreadWaitMs = 20000;
    // Saves loaded since launch (F4SE's kPostLoadGame): `load` waits for it to rise, as a load in the same
    // cell may pass without a loading menu the status polls catch.
    std::atomic<int> g_loads{ 0 };

    std::string PipeName()
    {
        char buf[256] = {};
        const DWORD n = GetEnvironmentVariableA("F3NV_TEST_PIPE", buf, sizeof(buf));
        return n && n < sizeof(buf) ? std::string(buf) : std::string(R"(\\.\pipe\f3nv_test)");
    }

    // Runs `fn` on the main thread and returns what it returned, or null when it
    // did not finish in time. `fn` owns everything it touches: a late task (a
    // `coc` holds the main thread through the load) must not write to this stack.
    std::optional<JValue> OnMain(std::function<JValue()> fn)
    {
        auto done = std::make_shared<std::promise<JValue>>();
        auto future = done->get_future();
        F4SE::GetTaskInterface()->AddTask([fn = std::move(fn), done]() { done->set_value(fn()); });
        if (future.wait_for(std::chrono::milliseconds(kMainThreadWaitMs)) != std::future_status::ready)
            return std::nullopt;
        return future.get();
    }

    std::string Hex(std::uint32_t id)
    {
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%08X", id);
        return buf;
    }

    // The `ref` argument's FormID (a number, or hex text), or 0.
    std::uint32_t RefArg(const JValue& args)
    {
        const JValue& ref = args["ref"];
        if (ref.isString())
            return static_cast<std::uint32_t>(std::strtoul(ref.asString().c_str(), nullptr, 16));
        return ref.isNumber() ? ref.asU32() : 0;
    }

    // Compiles and runs one console line as the console does; the text it printed.
    // Command handlers print only in console mode, a thread-local flag the
    // console menu sets around each line, so this sets it too. The log drops
    // new text once it holds 0xFFFE characters, so it is emptied first.
    std::string RunConsole(const std::string& command, RE::TESObjectREFR* ref)
    {
        auto* log = RE::ConsoleLog::GetSingleton();
        if (log)
            log->buffer.Set("", 0);
        auto* factory = RE::ConcreteFormFactory<RE::Script>::GetFormFactory();
        auto* script = factory ? factory->Create() : nullptr;
        if (!script)
            return "ERROR no Script form factory";
        script->SetText(command);
        auto* tls = RE::TLS::GetSingleton();
        const bool wasConsole = tls->consoleMode;
        tls->consoleMode = true;
        RE::ScriptCompiler compiler;
        script->CompileAndRun(&compiler, RE::COMPILER_NAME::kSystemWindow, ref);
        tls->consoleMode = wasConsole;
        delete script;
        return log && log->buffer.c_str() ? std::string(log->buffer.c_str()) : std::string();
    }

    // MessageBoxMenu::currentMessage on 1.11 (CommonLibF4's header has the older 0xE8).
    constexpr std::uintptr_t kCurrentMessage = 0xF0;

    // A button label as the case names it: no leading `$` (the translation key's mark).
    std::string Plain(const char* label)
    {
        return std::string(label && *label == '$' ? label + 1 : label ? label : "");
    }

    // A Flash number (int, uint or number) as an int; `fallback` when it is not one.
    int AsInt(const Scaleform::GFx::Value& value, int fallback)
    {
        return value.IsInt()      ? value.GetInt()
               : value.IsUInt()   ? static_cast<int>(value.GetUInt())
               : value.IsNumber() ? static_cast<int>(value.GetNumber())
                                  : fallback;
    }

    // Selects the open message box's button labeled `text` (any case) in its movie's button
    // list; the caller presses Enter, as a player does. Calling the code-side press directly
    // left the movie mid-press, and it dismissed the next box at once.
    // Its labels and the list's selection read back, or an "error".
    JValue SelectButton(const std::string& text)
    {
        JValue out = JValue::Object();
        auto* ui = RE::UI::GetSingleton();
        auto menu = ui ? ui->GetMenu("MessageBoxMenu") : nullptr;
        auto* message = menu ? *reinterpret_cast<RE::MessageBoxData**>(
                                   reinterpret_cast<std::uintptr_t>(menu.get()) + kCurrentMessage)
                             : nullptr;
        if (!message) {
            out.set("error", JValue(std::string("E_NOMENU no message box open")));
            return out;
        }
        out.set("body", JValue(Plain(message->bodyText.c_str())));
        JValue labels = JValue::Array();
        int pick = -1;
        for (std::uint32_t i = 0; i < message->buttonText.size(); ++i) {
            const std::string label = Plain(message->buttonText[i].c_str());
            labels.push(JValue(label));
            if (pick < 0 && _stricmp(label.c_str(), text.c_str()) == 0)
                pick = static_cast<int>(i);
        }
        out.set("buttons", labels);
        if (pick < 0) {
            out.set("error", JValue("E_NOBUTTON no button " + text + " in " + labels.dump()));
            return out;
        }
        Scaleform::GFx::Value list;
        if (!menu->menuObj.GetMember("List_mc", &list) || !list.IsObject()) {
            out.set("error", JValue(std::string("E_FLASH the message box movie has no List_mc")));
            return out;
        }
        list.SetMember("selectedIndex", Scaleform::GFx::Value(static_cast<std::int32_t>(pick)));
        Scaleform::GFx::Value selected;
        list.GetMember("selectedIndex", &selected);
        out.set("wanted", JValue(pick));
        out.set("selected", JValue(AsInt(selected, -1)));
        return out;
    }

    // UIMessageQueue::AddMessage on 1.11 (CommonLibF4 lists the ID for next-gen only).
    constexpr std::uint64_t kAddMessage = 2284929;

    // Each menu's Done: the code function its Done button calls (its Flash's BGSCodeObj.<name>()).
    std::optional<std::string> DoneFunction(const std::string& name)
    {
        if (name == "LooksMenu")
            return "ConfirmAndCloseMenu";
        if (name == "SPECIALMenu")
            return "tryCloseMenu";
        return std::nullopt;
    }

    // Why the open menu's Done button is greyed out, as its Flash greys it (SPECIALMenu: points
    // left to spend, or no name); "" when it is not.
    std::string DoneBlocked(const RE::IMenu& menu)
    {
        Scaleform::GFx::Value left, list, entries, first, text;
        if (menu.menuObj.GetMember("pointsRemaining", &left) && AsInt(left, 0) != 0)
            return std::to_string(AsInt(left, 0)) + " SPECIAL points left to spend";
        const bool named = !menu.menuObj.GetMember("List_mc", &list) || !list.GetMember("entryList", &entries) ||
                           !entries.GetElement(0, &first) || !first.GetMember("text", &text) || !text.IsString() ||
                           std::string(text.GetString()).find_first_not_of(' ') != std::string::npos;
        return named ? "" : "no name";
    }

    // Runs the open menu `name`'s code function `function` by name, as its Flash does
    // (BGSCodeObj.<function>()): {"result": its answer when boolean}; an "error" when the menu is
    // not open or has no such function.
    JValue CallMenu(const std::string& name, const std::string& function)
    {
        JValue out = JValue::Object();
        auto* ui = RE::UI::GetSingleton();
        auto menu = ui ? ui->GetMenu(RE::BSFixedString(name)) : nullptr;
        if (!menu) {
            out.set("error", JValue("E_NOMENU " + name + " is not open"));
            return out;
        }
        Scaleform::GFx::Value code, answer;
        if (!menu->menuObj.GetMember("BGSCodeObj", &code) || !code.IsObject() ||
            !code.Invoke(function.c_str(), &answer)) {
            out.set("error", JValue("E_NOFUNC " + name + " has no code function " + function));
            return out;
        }
        if (answer.IsBoolean())
            out.set("result", JValue(answer.GetBoolean()));
        return out;
    }

    // A case's word as a Flash argument: an int when it is one, else a string (kept alive by `word`).
    Scaleform::GFx::Value FlashArg(const std::string& word)
    {
        char* end = nullptr;
        const long n = std::strtol(word.c_str(), &end, 10);
        return !word.empty() && *end == '\0' ? Scaleform::GFx::Value(static_cast<std::int32_t>(n))
                                             : Scaleform::GFx::Value(word.c_str());
    }

    // A Flash value as JSON: a boolean, number or string, and arrays and plain objects `depth` levels down
    // (a menu's option list); null for anything else.
    JValue FromFlash(const Scaleform::GFx::Value& value, int depth = 2)
    {
        if (value.IsBoolean())
            return JValue(value.GetBoolean());
        if (value.IsString())
            return JValue(std::string(value.GetString()));
        if (value.IsNumber())
            return JValue(value.GetNumber());
        if (value.IsInt() || value.IsUInt())
            return JValue(AsInt(value, 0));
        if (depth > 0 && value.IsArray()) {
            JValue items = JValue::Array();
            Scaleform::GFx::Value item;
            for (std::uint32_t i = 0; i < value.GetArraySize(); ++i)
                items.push(value.GetElement(i, &item) ? FromFlash(item, depth - 1) : JValue());
            return items;
        }
        if (depth > 0 && value.IsObject() && !value.IsDisplayObject()) {
            JValue fields = JValue::Object();
            value.VisitMembers([&](const char* name, const Scaleform::GFx::Value& member) {
                fields.set(name, FromFlash(member, depth - 1));
            });
            return fields;
        }
        return JValue();
    }

    // One step of an `invoke` path from `owner`: its member `part`, or, for a number, its display
    // child of that name, else at that index (a list's rows are text fields named "0", "1"...).
    bool Step(Scaleform::GFx::Value& owner, const std::string& part, Scaleform::GFx::Value& next)
    {
        if (part.find_first_not_of("0123456789") != std::string::npos)
            return owner.GetMember(part, &next) && next.IsObject();
        const Scaleform::GFx::Value name(part.c_str()), at(static_cast<std::int32_t>(std::stoi(part)));
        return (owner.Invoke("getChildByName", &next, &name, 1) && next.IsObject()) ||
               (owner.Invoke("getChildAt", &next, &at, 1) && next.IsObject());
    }

    // `invoke` text "<menu> <path>[()] [args...]": on the open menu's movie object, calls the public
    // Flash method at the dotted `path` (with "()" or int/string args), as its own buttons do;
    // "<path>=<value>" sets that member; a bare path reads it. {"result": the answer or value}; an
    // "error" when the menu is not open or the path does not resolve.
    JValue InvokeMenu(const std::string& text)
    {
        JValue out = JValue::Object();
        std::istringstream in(text);
        std::string name, path;
        in >> name >> path;
        const std::vector<std::string> words{ std::istream_iterator<std::string>(in), {} };
        auto* ui = RE::UI::GetSingleton();
        auto menu = ui && !name.empty() ? ui->GetMenu(RE::BSFixedString(name)) : nullptr;
        if (!menu) {
            out.set("error", JValue("E_NOMENU " + name + " is not open"));
            return out;
        }
        const auto eq = path.find('=');
        const std::string value = eq == std::string::npos ? "" : path.substr(eq + 1);
        std::string target = path.substr(0, eq);
        const bool parens = target.size() > 2 && target.compare(target.size() - 2, 2, "()") == 0;
        if (parens)
            target.resize(target.size() - 2);
        const char* mode = eq != std::string::npos ? "set " : parens || !words.empty() ? "call " : "read ";
        Scaleform::GFx::Value owner = menu->menuObj, answer;
        std::istringstream parts(target);
        std::string member;
        for (std::string part; std::getline(parts, part, '.'); member = part) {
            Scaleform::GFx::Value next;
            if (!member.empty() && !Step(owner, member, next)) {
                out.set("error", JValue("E_NOPATH " + name + " has no object " + member + " in " + target));
                return out;
            }
            if (!member.empty())
                owner = next;
        }
        std::vector<Scaleform::GFx::Value> args;
        for (const auto& word : words)
            args.push_back(FlashArg(word));
        const bool ok = *mode == 's'   ? owner.SetMember(member, FlashArg(value)) && owner.GetMember(member, &answer)
                        : *mode == 'c' ? owner.Invoke(member.c_str(), &answer, args.data(), args.size())
                                       : owner.GetMember(member, &answer);
        if (!ok) {
            out.set("error", JValue("E_NOPATH " + name + " could not " + mode + target));
            return out;
        }
        out.set("result", FromFlash(answer));
        return out;
    }

    // `call` text "<menu> <function>": CallMenu.
    JValue CallMenuText(const std::string& text)
    {
        const auto space = text.rfind(' ');
        if (space == std::string::npos) {
            JValue out = JValue::Object();
            out.set("error", JValue("E_ARGS call needs \"<menu> <function>\", got \"" + text + "\""));
            return out;
        }
        return CallMenu(text.substr(0, space), text.substr(space + 1));
    }

    // Closes the open menu `name` as its Done does: its own Done function ("done": its name),
    // which answers false while the menu is busy (LooksMenu loading the edited actor's face:
    // "E_BUSY"); E_DISABLED while its Done button is greyed out; a menu without one gets a hide
    // message. An "error" when not open.
    JValue CloseMenu(const std::string& name)
    {
        JValue out = JValue::Object();
        auto* ui = RE::UI::GetSingleton();
        auto menu = ui ? ui->GetMenu(RE::BSFixedString(name)) : nullptr;
        if (!menu) {
            out.set("error", JValue("E_NOMENU " + name + " is not open"));
            return out;
        }
        if (const auto done = DoneFunction(name)) {
            const auto blocked = DoneBlocked(*menu);
            auto called = blocked.empty() ? CallMenu(name, *done) : JValue::Object();
            if (!blocked.empty())
                out.set("error", JValue("E_DISABLED " + name + "'s Done is greyed out: " + blocked));
            else if (called.has("error"))
                out.set("error", called["error"]);
            else if (called.has("result") && !called["result"].asBool())
                out.set("error", JValue("E_BUSY " + name + "'s Done put up nothing (busy)"));
            else
                out.set("done", JValue(*done));
            return out;
        }
        static REL::Relocation<void (*)(RE::UIMessageQueue*, const RE::BSFixedString&, RE::UI_MESSAGE_TYPE)>
            add{ REL::ID(kAddMessage) };
        add(RE::UIMessageQueue::GetSingleton(), RE::BSFixedString(name), RE::UI_MESSAGE_TYPE::kHide);
        out.set("closed", JValue(name));
        return out;
    }

    JValue OpenMenus()
    {
        JValue menus = JValue::Array();
        auto* ui = RE::UI::GetSingleton();
        if (!ui)
            return menus;
        for (const auto& menu : ui->menuStack) {
            if (menu)
                menus.push(JValue(std::string(menu->menuName.c_str())));
        }
        return menus;
    }

    // `form` text "<plugin> <object id hex>": the record's runtime FormID wherever the plugin
    // loads (a light plugin's id is its own 0x000-0xFFF), and its form type; E_NOFORM when absent.
    JValue FormOf(const std::string& text)
    {
        JValue out = JValue::Object();
        const auto space = text.rfind(' ');
        auto* data = RE::TESDataHandler::GetSingleton();
        auto* form = space == std::string::npos || !data
                         ? nullptr
                         : data->LookupForm(static_cast<std::uint32_t>(std::stoul(text.substr(space + 1), nullptr, 16)),
                                            text.substr(0, space));
        if (!form) {
            out.set("error", JValue("E_NOFORM no form " + text));
            return out;
        }
        out.set("form", JValue(Hex(form->GetFormID())));
        out.set("type", JValue(std::string(form->GetFormTypeString())));
        return out;
    }

    // [x, y, z] as a JSON array.
    JValue Point(const RE::NiPoint3& p)
    {
        JValue out = JValue::Array();
        for (const float v : { p.x, p.y, p.z }) {
            out.push(JValue(static_cast<double>(v)));
        }
        return out;
    }

    // A trigger's box or shape: ExtraPrimitive (BSExtraData, then its BGSPrimitive*), or null.
    const RE::BGSPrimitive* PrimitiveOf(const RE::TESObjectREFR* ref)
    {
        const auto* extra = ref->extraList ? ref->extraList->GetByType(RE::EXTRA_DATA_TYPE::kPrimitive) : nullptr;
        return extra ? *reinterpret_cast<RE::BGSPrimitive* const*>(reinterpret_cast<const std::byte*>(extra) +
                                                                   sizeof(RE::BSExtraData))
                     : nullptr;
    }

    // `where` text "<FormID hex>", or "" for the player: the reference's position, its heading
    // (z angle, degrees), its bounds (min, max: unrotated, around its position; a trigger's box radii,
    // else the object's own bounds),
    // whether its 3D is loaded, and its cell; E_NOFORM when not a reference.
    JValue Where(const std::string& text)
    {
        JValue out = JValue::Object();
        RE::TESObjectREFR* ref = text.empty() ? RE::PlayerCharacter::GetSingleton() : nullptr;
        if (!text.empty()) {
            auto* form = RE::TESForm::GetFormByID(static_cast<std::uint32_t>(std::stoul(text, nullptr, 16)));
            ref = form ? form->As<RE::TESObjectREFR>() : nullptr;
        }
        if (!ref) {
            out.set("error", JValue("E_NOFORM no reference " + text));
            return out;
        }
        const auto pos = ref->GetPosition();
        out.set("x", JValue(static_cast<double>(pos.x)));
        out.set("y", JValue(static_cast<double>(pos.y)));
        out.set("z", JValue(static_cast<double>(pos.z)));
        out.set("angle", JValue(static_cast<double>(ref->data.angle.z) * 57.29577951308232));
        const auto* primitive = PrimitiveOf(ref);
        const RE::NiPoint3 radii = primitive ? primitive->radii : RE::NiPoint3{};
        out.set("primitive", JValue(primitive ? static_cast<double>(primitive->type.underlying()) : 0.0));
        out.set("min", Point(primitive ? RE::NiPoint3{ -radii.x, -radii.y, -radii.z } : ref->GetBoundMin()));
        out.set("max", Point(primitive ? radii : ref->GetBoundMax()));
        out.set("loaded", JValue(ref->Get3D() != nullptr));
        auto* cell = ref->GetParentCell();
        out.set("cell", JValue(cell ? Hex(cell->GetFormID()) : std::string()));
        return out;
    }

    // The save list entry named `name` (no `.fos`, any case), or null.
    RE::BGSSaveLoadFileEntry* SaveEntry(RE::BGSSaveLoadManager* mgr, const std::string& name)
    {
        for (auto* entry : mgr->saveGameList) {
            std::string file = entry && entry->fileName ? entry->fileName : "";
            if (const auto dot = file.rfind('.'); dot != std::string::npos && _stricmp(file.c_str() + dot, ".fos") == 0)
                file.resize(dot);
            if (_stricmp(file.c_str(), name.c_str()) == 0)
                return entry;
        }
        return nullptr;
    }

    // Queues the load of save `name` as the Load menu does: the manager loads its queued entry from the
    // main loop, outside this task. The console's `load` loads at once, inside the F4SE task, and hung
    // there ("Reverting game..." and nothing after). See: docs/fork/fo4_test_layers_plan.md#s3
    JValue QueueLoad(const std::string& name)
    {
        JValue out = JValue::Object();
        auto* mgr = RE::BGSSaveLoadManager::GetSingleton();
        if (!mgr) {
            out.set("error", JValue(std::string("E_NOSAVE no save/load manager")));
            return out;
        }
        if (!mgr->isSaveListBuilt)
            mgr->BuildSaveGameList(mgr->currentPlayerID);
        auto* entry = SaveEntry(mgr, name);
        if (!entry) {
            std::string seen;
            for (auto* other : mgr->saveGameList)
                seen += std::string(seen.empty() ? "" : ", ") + (other && other->fileName ? other->fileName : "?");
            out.set("error", JValue("E_NOSAVE no save " + name + " among " + std::to_string(mgr->saveGameList.size()) +
                                    " (player " + std::to_string(mgr->currentPlayerID) + "): " + seen));
            return out;
        }
        mgr->queuedEntryToLoad = entry;
        mgr->QueueSaveLoadTask(RE::BGSSaveLoadManager::QUEUED_TASK::kLoadGame);
        out.set("queued", JValue(std::string(entry->fileName)));
        return out;
    }

    JValue Status()
    {
        JValue out = JValue::Object();
        out.set("menus", OpenMenus());
        auto* player = RE::PlayerCharacter::GetSingleton();
        out.set("player", JValue(player != nullptr));
        auto* cell = player ? player->GetParentCell() : nullptr;
        out.set("cell", JValue(cell ? Hex(cell->GetFormID()) : std::string()));
        out.set("cell_name", JValue(cell ? std::string(cell->GetFormEditorID()) : std::string()));
        out.set("loads", JValue(static_cast<double>(g_loads.load())));
        return out;
    }

    JValue Handle(const std::string& cmd, const JValue& args, std::string& error)
    {
        JValue result = JValue::Object();
        if (cmd == "ping") {
            result.set("pong", JValue(true));
            return result;
        }
        if (cmd != "status" && cmd != "console" && cmd != "button" && cmd != "close" && cmd != "call" &&
            cmd != "invoke" && cmd != "form" && cmd != "where" && cmd != "load") {
            error = "E_UNKNOWN unknown command " + cmd;
            return result;
        }
        const std::uint32_t ref = RefArg(args);
        const std::string command = args["command"].asString();
        const std::string text = args["text"].asString();
        auto answer = OnMain([cmd, command, text, ref]() {
            if (cmd == "status")
                return Status();
            if (cmd == "button")
                return SelectButton(text);
            if (cmd == "close")
                return CloseMenu(text);
            if (cmd == "call")
                return CallMenuText(text);
            if (cmd == "invoke")
                return InvokeMenu(text);
            if (cmd == "form")
                return FormOf(text);
            if (cmd == "where")
                return Where(text);
            if (cmd == "load")
                return QueueLoad(text);
            auto* form = ref ? RE::TESForm::GetFormByID(ref) : nullptr;
            JValue out = JValue::Object();
            out.set("output", JValue(RunConsole(command, form ? form->As<RE::TESObjectREFR>() : nullptr)));
            return out;
        });
        if (!answer)
            error = "E_LOADING main thread did not run the request in time (still queued)";
        else if ((*answer)["error"].isString())
            error = (*answer)["error"].asString();
        return answer ? *answer : result;
    }

    std::string Respond(const std::string& line)
    {
        std::string parseError;
        const JValue req = JValue::Parse(line, &parseError);
        JValue resp = JValue::Object();
        resp.set("id", req["id"]);
        std::string error = parseError.empty() ? std::string() : "E_PROTOCOL " + parseError;
        JValue result = error.empty() ? Handle(req["cmd"].asString(), req["args"], error) : JValue();
        resp.set("ok", JValue(error.empty()));
        if (error.empty()) {
            resp.set("result", result);
        } else {
            const auto space = error.find(' ');
            resp.set("code", JValue(error.substr(0, space)));
            resp.set("error", JValue(error.substr(space + 1)));
        }
        return resp.dump() + "\n";
    }

    void Serve(HANDLE pipe)
    {
        std::string pending;
        char buf[4096];
        DWORD got = 0;
        while (ReadFile(pipe, buf, sizeof(buf), &got, nullptr) && got) {
            pending.append(buf, got);
            for (auto nl = pending.find('\n'); nl != std::string::npos; nl = pending.find('\n')) {
                const std::string reply = Respond(pending.substr(0, nl));
                pending.erase(0, nl + 1);
                DWORD wrote = 0;
                WriteFile(pipe, reply.data(), static_cast<DWORD>(reply.size()), &wrote, nullptr);
            }
        }
    }

    // Serves each client on its own thread, so a status check can run beside a case run.
    void PipeLoop()
    {
        const std::string name = PipeName();
        REX::INFO("listening on {}", name);
        for (;;) {
            HANDLE pipe = CreateNamedPipeA(name.c_str(), PIPE_ACCESS_DUPLEX,
                                           PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                                           PIPE_UNLIMITED_INSTANCES, 1 << 20, 1 << 20, 0, nullptr);
            if (pipe == INVALID_HANDLE_VALUE) {
                Sleep(1000);
                continue;
            }
            if (!ConnectNamedPipe(pipe, nullptr) && GetLastError() != ERROR_PIPE_CONNECTED) {
                CloseHandle(pipe);
                continue;
            }
            std::thread([pipe]() {
                Serve(pipe);
                DisconnectNamedPipe(pipe);
                CloseHandle(pipe);
            }).detach();
        }
    }

    bool InitPlugin(const F4SE::LoadInterface* a_f4se)
    {
        static std::atomic<bool> started{ false };
        if (started.exchange(true))
            return true;
        F4SE::Init(a_f4se);
        if (auto* messaging = F4SE::GetMessagingInterface())
            messaging->RegisterListener([](F4SE::MessagingInterface::Message* msg) {
                if (msg && msg->type == F4SE::MessagingInterface::kPostLoadGame)
                    g_loads.fetch_add(1);
            });
        std::thread(PipeLoop).detach();
        return true;
    }
}

F4SE_PLUGIN_QUERY(const F4SE::QueryInterface* a_f4se, F4SE::PluginInfo* a_info)
{
    if (const auto data = F4SE::PluginVersionData::GetSingleton()) {
        a_info->infoVersion = F4SE::PluginInfo::kVersion;
        a_info->name = data->GetPluginName().data();
        a_info->version = data->GetPluginVersion().pack();
    }
    return a_f4se->RuntimeVersion() >= REL::Version(F4SE::RUNTIME_1_10_163);
}

F4SE_PLUGIN_LOAD(const F4SE::LoadInterface* a_f4se)
{
    return InitPlugin(a_f4se);
}

F4SE_PLUGIN_PRELOAD(const F4SE::LoadInterface* a_f4se)
{
    return InitPlugin(a_f4se);
}
