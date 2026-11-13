// Flash helpers shared by the menus F3NV hooks (pipboy.cpp, transfer.cpp, hardcore.cpp): reading values, finding a
// menu's instance by its BGSCodeObj, and logging an object's members when a menu is not laid out as expected; and
// the natives every movie of ours may call (f4se.plugins.F3NV: TextureExists, for f3ui's Images).
#include "condition.h"

#include "f4se/GameStreams.h"

#include <windows.h>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <fstream>
#include <mutex>
#include <string>
#include <unordered_set>

namespace condition {

namespace {

// `path` lowercased with backslashes, as a BA2's name table holds it.
std::string Key(std::string path) {
    std::replace(path.begin(), path.end(), '/', '\\');
    std::transform(path.begin(), path.end(), path.begin(), [](unsigned char c) { return char(std::tolower(c)); });
    return path;
}

// Every name in archive `file`'s name table (BTDX: magic, version, type, file count, name table offset; then per
// file a 16-bit length and the name), into `names`.
void ReadNames(const std::string &file, std::unordered_set<std::string> *names) {
    std::ifstream in(file, std::ios::binary);
    char magic[4] = {};
    UInt32 version = 0, count = 0;
    char type[4] = {};
    UInt64 table = 0;
    in.read(magic, 4).read(reinterpret_cast<char *>(&version), 4).read(type, 4);
    in.read(reinterpret_cast<char *>(&count), 4).read(reinterpret_cast<char *>(&table), 8);
    if (!in || memcmp(magic, "BTDX", 4) || !table) return;
    in.seekg(std::streamoff(table));
    std::string name;
    for (UInt32 i = 0; i < count && in; i++) {
        UInt16 length = 0;
        in.read(reinterpret_cast<char *>(&length), 2);
        name.resize(length);
        if (length) in.read(&name[0], length);
        if (in) names->insert(Key(name));
    }
}

// Whether a BA2 in Data lists `path`, the archives' name tables read once. The game's resource stream cannot open a
// texture (DX10) archive's files, so TextureExists asks the tables (played 2026-11-12: every icon in
// FalloutNV - Textures.ba2 reported missing).
bool Archived(const std::string &path) {
    static std::unordered_set<std::string> names;
    static std::once_flag read;
    std::call_once(read, [] {
        WIN32_FIND_DATAA found;
        HANDLE at = FindFirstFileA("Data\\*.ba2", &found);
        for (bool more = at != INVALID_HANDLE_VALUE; more; more = FindNextFileA(at, &found) != 0)
            ReadNames(std::string("Data\\") + found.cFileName, &names);
        if (at != INVALID_HANDLE_VALUE) FindClose(at);
        _MESSAGE("TextureExists: %u names in the archives", UInt32(names.size()));
    });
    return names.count(Key(path)) > 0;
}

// Logs each member it visits by name and GFx type.
class MemberLog : public GFxValue::ObjectInterface::ObjVisitor {
public:
    void Visit(const char *member, GFxValue *value) override {
        _MESSAGE("  member %s (type %d)", member, value->GetType());
    }
};

// TextureExists(path): whether the game has Textures\<path> (the path f4se.MountImage takes): a loose file or one in
// a general archive, opened as F4SE opens a translation file, or a name in a BA2's table (Archived). MountImage itself
// reports true for a missing file. See docs/fork/swf_framework.md#images
class TextureExistsNative : public GFxFunctionHandler {
public:
    void Invoke(Args *args) override {
        bool found = false;
        if (args->numArgs > 0 && args->args[0].IsString()) {
            std::string path = Key(std::string("Textures\\") + args->args[0].GetString());
            BSResourceNiBinaryStream stream(path.c_str());
            found = stream.IsValid() || Archived(path);
        }
        args->result->SetBool(found);
    }
};

}  // namespace

void RegisterImageNatives(GFxMovieRoot *movie, GFxValue *plugin) {
    RegisterFunction<TextureExistsNative>(plugin, movie, "TextureExists");
}

double Num(const GFxValue &v) {
    switch (v.GetType()) {
        case GFxValue::kType_Int: return v.GetInt();
        case GFxValue::kType_UInt: return v.GetUInt();
        case GFxValue::kType_Number: return v.GetNumber();
        case GFxValue::kType_Bool: return v.GetBool() ? 1.0 : 0.0;
        default: return 0.0;
    }
}

bool Get(GFxValue &obj, const char *name, GFxValue *out) {
    return obj.IsObject() && obj.GetMember(name, out);
}

void LogMembers(GFxValue &obj) {
    MemberLog log;
    if (obj.IsObject()) obj.VisitMembers(&log);
}

bool FindMenu(GFxMovieRoot *movie, std::initializer_list<const char *> bases, const char *needs, std::string *base,
              GFxValue *root, GFxValue *code) {
    for (const char *path : bases) {
        GFxValue part;
        std::string at(path);
        if (movie->GetVariable(code, (at + ".BGSCodeObj").c_str()) && code->IsObject() &&
            (!needs || (movie->GetVariable(&part, (at + "." + needs).c_str()) && part.IsObject())) &&
            movie->GetVariable(root, path)) {
            *base = at;
            return true;
        }
    }
    base->clear();
    return false;
}

}  // namespace condition
