// Flash helpers shared by the menus F3NV hooks (pipboy.cpp, transfer.cpp, hardcore.cpp): reading values, finding a
// menu's instance by its BGSCodeObj, and logging an object's members when a menu is not laid out as expected.
#include "condition.h"

namespace condition {

namespace {

// Logs each member it visits by name and GFx type.
class MemberLog : public GFxValue::ObjectInterface::ObjVisitor {
public:
    void Visit(const char *member, GFxValue *value) override {
        _MESSAGE("  member %s (type %d)", member, value->GetType());
    }
};

}  // namespace

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
