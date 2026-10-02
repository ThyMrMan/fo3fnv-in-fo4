#include "stats_sheet.h"

#include <windows.h>

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

#include "activation.h"
#include "actor_stats.h"
#include "conversation.h"
#include "dialogue_state.h"
#include "leveling.h"
#include "levelup_menu.h"
#include "log.h"
#include "main_thread.h"
#include "main_tick.h"
#include "menu.h"
#include "menu_layout.h"
#include "menu_widgets.h"
#include "paths.h"
#include "scope.h"
#include "script_tables.h"
#include "stats_layout.h"

namespace tesruntime::mw {

namespace {

namespace sl = stats_layout;

// MorrowindRuntime.ini's [CharacterSheet]: the windows stay off unless
// Enabled=1, and Hotkey is a virtual-key code in decimal. K by default: bound
// to nothing in Skyrim's own controlmap.txt (every letter it leaves free is
// G, H, K, U, Y, B and N).
// See: docs/commentary/morrowind_runtime.md#character-sheet
constexpr const char* kIniName = "MorrowindRuntime.ini";
constexpr const char* kIniSection = "CharacterSheet";
constexpr int kDefaultHotkey = 'K';
int g_hotkey = kDefaultHotkey;

// The tick's period, and how many ticks pass between reads of the skills.
constexpr int kTickMs = 33;
constexpr int kSampleEvery = 10;

// Rows the wheel moves per notch.
constexpr int kWheelRows = 3;

constexpr const char* kPlayer = "player";

// Skyrim's actor values for Health, Magicka and Fatigue, and their GMST names.
constexpr const char* kDynamicValues[] = {"Health", "Magicka", "Stamina"};
constexpr const char* kDynamicGmst[][2] = {
    {"sHealth", "Health"}, {"sMagic", "Magicka"}, {"sFatigue", "Fatigue"}};

// The eight attributes and 27 skills by TES3 index: GMST name, and the text
// Morrowind.esm gives it, for a chain that stages none.
constexpr const char* kAttributeGmst[][2] = {
    {"sAttributeStrength", "Strength"}, {"sAttributeIntelligence", "Intelligence"},
    {"sAttributeWillpower", "Willpower"}, {"sAttributeAgility", "Agility"},
    {"sAttributeSpeed", "Speed"}, {"sAttributeEndurance", "Endurance"},
    {"sAttributePersonality", "Personality"}, {"sAttributeLuck", "Luck"}};
constexpr const char* kSkillGmst[][2] = {
    {"sSkillBlock", "Block"}, {"sSkillArmorer", "Armorer"},
    {"sSkillMediumarmor", "Medium Armor"}, {"sSkillHeavyarmor", "Heavy Armor"},
    {"sSkillBluntweapon", "Blunt Weapon"}, {"sSkillLongblade", "Long Blade"},
    {"sSkillAxe", "Axe"}, {"sSkillSpear", "Spear"},
    {"sSkillAthletics", "Athletics"}, {"sSkillEnchant", "Enchant"},
    {"sSkillDestruction", "Destruction"}, {"sSkillAlteration", "Alteration"},
    {"sSkillIllusion", "Illusion"}, {"sSkillConjuration", "Conjuration"},
    {"sSkillMysticism", "Mysticism"}, {"sSkillRestoration", "Restoration"},
    {"sSkillAlchemy", "Alchemy"}, {"sSkillUnarmored", "Unarmored"},
    {"sSkillSecurity", "Security"}, {"sSkillSneak", "Sneak"},
    {"sSkillAcrobatics", "Acrobatics"}, {"sSkillLightarmor", "Light Armor"},
    {"sSkillShortblade", "Short Blade"}, {"sSkillMarksman", "Marksman"},
    {"sSkillMercantile", "Mercantile"}, {"sSkillSpeechcraft", "Speechcraft"},
    {"sSkillHandtohand", "Hand-to-hand"}};
constexpr int kSkillCount = 27;
constexpr const char* kSpecializationGmst[][2] = {
    {"sSpecializationCombat", "Combat"}, {"sSpecializationMagic", "Magic"},
    {"sSpecializationStealth", "Stealth"}};

constexpr Rect kSkillView{sl::kSkillViewX, sl::kSkillViewY, sl::kSkillViewW,
                          sl::kSkillViewH};
constexpr Rect kSkillScroll{sl::kSkillScrollX, sl::kSkillScrollY,
                            sl::kSkillScrollW, sl::kSkillScrollH};
constexpr Rect kBarFill[] = {
    {sl::kBarFill0X, sl::kBarFill0Y, sl::kBarFill0W, sl::kBarFill0H},
    {sl::kBarFill1X, sl::kBarFill1Y, sl::kBarFill1W, sl::kBarFill1H},
    {sl::kBarFill2X, sl::kBarFill2Y, sl::kBarFill2W, sl::kBarFill2H}};

// Where a row's one line sits in its 18 px row, as the movie placed it.
constexpr int kTextShift = (sl::kRowH - layout::kFontPx) / 2 - layout::kTextGutter;

// One line of the skill list: a heading in the header color, or a name with
// its value. A blank line separates groups.
struct Row {
    std::string name;
    std::string value;
    bool heading = false;
};

std::vector<Row> g_rows;
int g_scroll = 0;
bool g_captionDirty = false;
bool g_keyWasDown = false;
int g_untilSample = 0;
ThumbDrag g_drag;

CustomMenu& Menu() {
    static CustomMenu menu("MorrowindStatsMenu", "morrowind_stats");
    return menu;
}

std::string Path(const std::string& name, const char* property) {
    return "_root." + name + property;
}

std::string Indexed(const char* name, int index, const char* property) {
    return Path(name + std::to_string(index), property);
}

std::string Gmst(const char* const (&entry)[2]) {
    return GmstText(entry[0], entry[1]);
}

void SetText(const std::string& path, const std::string& text) {
    Menu().SetText(path.c_str(), text.c_str());
}

// ------------------------------------------------------------- the panes

// A bar's value and fill: the movie draws it full and a black cover hides
// the part past the value, as the dialogue window's disposition bar does.
void PushBar(int row) {
    const float current = Hooks().dynamicStat ? Hooks().dynamicStat(kPlayer, row) : 0;
    const float fraction = Hooks().statPercent
                               ? Hooks().statPercent(kPlayer, kDynamicValues[row])
                               : 1.0f;
    const float most = fraction > 0.001f ? current / fraction : current;
    SetText(Indexed("BarLabel", row, ".text"), Gmst(kDynamicGmst[row]));
    SetText(Indexed("BarValue", row, ".text"),
            std::to_string(static_cast<int>(std::lround(current))) + "/" +
                std::to_string(static_cast<int>(std::lround(most))));
    const Rect& fill = kBarFill[row];
    const double filled = fill.w * std::clamp(static_cast<double>(fraction), 0.0, 1.0);
    const double rest = fill.w - filled;
    const std::string cover = "BarCover" + std::to_string(row);
    Menu().SetNumber(Path(cover, "._x").c_str(), fill.x + filled);
    Menu().SetNumber(Path(cover, "._width").c_str(), std::max(rest, 1.0));
    Menu().SetNumber(Path(cover, "._visible").c_str(), rest > 0.5 ? 1 : 0);
}

void PushInfo() {
    const std::string rows[][2] = {
        {GmstText("sLevel", "Level"),
         std::to_string(Hooks().playerLevel ? Hooks().playerLevel() : 1)},
        {GmstText("sReputation", "Reputation"), std::to_string(State().reputation)},
        {GmstText("sBounty", "Bounty"),
         std::to_string(static_cast<int>(PlayerCrimeLevelNow()))}};
    for (int row = 0; row < sl::kInfoRows; ++row) {
        SetText(Indexed("InfoName", row, ".text"), rows[row][0]);
        SetText(Indexed("InfoValue", row, ".text"), rows[row][1]);
    }
}

void PushAttributes() {
    for (int i = 0; i < sl::kAttributeRows; ++i) {
        SetText(Indexed("AttrName", i, ".text"), Gmst(kAttributeGmst[i]));
        SetText(Indexed("AttrValue", i, ".text"),
                std::to_string(static_cast<int>(ActorAttribute(kPlayer, i))));
    }
}

// Each specialization's skills under its heading, by name, as OpenMW groups
// the stats window's skills; then the factions the player belongs to.
void BuildRows() {
    g_rows.clear();
    for (int spec = 0; spec < kSpecializationCount; ++spec) {
        std::vector<Row> skills;
        for (int i = 0; i < kSkillCount; ++i) {
            const SkillDef* def = FindSkill(i);
            if (!def || def->specialization != spec) continue;
            skills.push_back({Gmst(kSkillGmst[i]),
                              std::to_string(static_cast<int>(ActorSkill(kPlayer, i)))});
        }
        std::sort(skills.begin(), skills.end(),
                  [](const Row& a, const Row& b) { return a.name < b.name; });
        if (!g_rows.empty()) g_rows.push_back({});
        g_rows.push_back({Gmst(kSpecializationGmst[spec]), "", true});
        g_rows.insert(g_rows.end(), skills.begin(), skills.end());
    }
    bool first = true;
    for (const auto& [key, membership] : State().Factions()) {
        if (membership.rank < 0 || membership.expelled) continue;
        if (first) {
            g_rows.push_back({});
            g_rows.push_back({GmstText("sFaction", "Faction"), "", true});
            first = false;
        }
        const std::string id = SplitStateKey(key).second;
        const FactionDef* def = FindFaction(id);
        const bool ranked = def && membership.rank < static_cast<int>(def->rankNames.size());
        g_rows.push_back({def && !def->id.empty() ? def->id : id,
                          ranked ? def->rankNames[membership.rank]
                                 : std::to_string(membership.rank + 1)});
    }
}

int ListRange() {
    return std::max(0, static_cast<int>(g_rows.size()) * sl::kRowH - kSkillView.h);
}

// Places the pooled row fields over the visible rows; a row only partly in
// the view is hidden, as the dialogue window's topic list does.
void PushRows() {
    const int first = g_scroll / sl::kRowH;
    for (int field = 0; field < sl::kSkillFields; ++field) {
        const int index = first + field;
        const int top = kSkillView.y + index * sl::kRowH - g_scroll;
        const bool shown = index < static_cast<int>(g_rows.size()) &&
                           top >= kSkillView.y &&
                           top + sl::kRowH <= kSkillView.y + kSkillView.h;
        const std::string name = "SkillName" + std::to_string(field);
        const std::string value = "SkillValue" + std::to_string(field);
        Menu().SetNumber(Path(name, "._visible").c_str(), shown ? 1 : 0);
        Menu().SetNumber(Path(value, "._visible").c_str(), shown ? 1 : 0);
        if (!shown) continue;
        const Row& row = g_rows[static_cast<std::size_t>(index)];
        SetText(Path(name, ".text"), row.name);
        SetText(Path(value, ".text"), row.value);
        Menu().SetNumber(Path(name, ".textColor").c_str(),
                         row.heading ? layout::kColorHeader : layout::kColorNormal);
        Menu().SetNumber(Path(name, "._y").c_str(), top + kTextShift);
        Menu().SetNumber(Path(value, "._y").c_str(), top + kTextShift);
    }
    const int range = ListRange();
    PushScrollbar(Menu(), kSkillScroll, "_root.SkillScroll", "_root.SkillThumb",
                  range > 0, range > 0 ? static_cast<double>(g_scroll) / range : 0);
}

// The caption plate's gap around the name, once the field has measured it.
void PushCaption() {
    double width = 0;
    if (!Menu().GetNumber("_root.Title.textWidth", &width)) return;
    const double gap = width + 2 * sl::kCaptionPad;
    const double left = sl::kCaptionX + (sl::kCaptionW - gap) / 2;
    Menu().SetNumber("_root.Cover._x", left);
    Menu().SetNumber("_root.Cover._width", gap);
    Menu().SetNumber("_root.CapLeft._x", left - 2);
    Menu().SetNumber("_root.CapRight._x", left + gap);
    g_captionDirty = false;
}

void PushAll() {
    SetText("_root.Title.text", PlayerName());
    g_captionDirty = true;
    for (int row = 0; row < sl::kBarRows; ++row) PushBar(row);
    PushInfo();
    PushAttributes();
    BuildRows();
    g_scroll = std::clamp(g_scroll, 0, ListRange());
    PushRows();
}

void Scroll(int pixels) {
    g_scroll = std::clamp(g_scroll + pixels, 0, ListRange());
    PushRows();
}

// ------------------------------------------------------------- the input

void OnClick(double x, double y) {
    const int range = ListRange();
    if (!kSkillScroll.Contains(x, y) || range <= 0) return;
    const double fraction = static_cast<double>(g_scroll) / range;
    if (g_drag.Begin(kSkillScroll, x, y, fraction)) return;
    const int page = kSkillView.h / sl::kRowH;
    Scroll(sl::kRowH * ScrollClick(kSkillScroll, y, fraction, page));
}

void OnHover(double, double y) {
    if (!g_drag.Active()) return;
    const int to = static_cast<int>(std::lround(g_drag.Fraction(y) * ListRange()));
    if (to != g_scroll) Scroll(to - g_scroll);
}

void OnWheel(double x, double y, double delta) {
    if (kSkillView.Contains(x, y) || kSkillScroll.Contains(x, y)) {
        Scroll(-static_cast<int>(delta) * kWheelRows * sl::kRowH);
    }
}

void OnTick() {
    if (g_captionDirty) PushCaption();
}

// ------------------------------------------------------------- the tick

// The hotkey, only while this game window has the keyboard: the key state
// is the whole desktop's.
bool HotkeyDown() {
    DWORD process = 0;
    GetWindowThreadProcessId(GetForegroundWindow(), &process);
    return process == GetCurrentProcessId() &&
           (GetAsyncKeyState(g_hotkey) & 0x8000) != 0;
}

// Out in the world with nothing open: no menu pausing the game, no
// conversation, a game loaded.
bool InGameplay() {
    return Hooks().playerInWorld && Hooks().playerInWorld() &&
           Hooks().gamePaused && !Hooks().gamePaused() && !ConversationOpen();
}

// K toggles the window; out in the world the skills are read now and then,
// and a pending level-up opens its step before anything else.
void Tick() {
    const bool down = HotkeyDown();
    const bool pressed = down && !g_keyWasDown;
    g_keyWasDown = down;
    if (Menu().IsOpen()) {
        if (pressed) Menu().Close();
        return;
    }
    if (LevelUpOpen() || !InGameplay()) return;
    if (--g_untilSample <= 0) {
        g_untilSample = kSampleEvery;
        SampleLeveling();
        if (PendingLevelUps() > 0) {
            OpenLevelUp();
            return;
        }
    }
    if (pressed) {
        PushAll();
        Menu().Open();
    }
}

int IniInt(const char* key, int fallback) {
    const std::string ini = SidecarDir() + kIniName;
    return static_cast<int>(GetPrivateProfileIntA(kIniSection, key, fallback, ini.c_str()));
}

}  // namespace

void InstallCharacterSheet() {
    if (IniInt("Enabled", 0) == 0) {
        Log("sheet: off (%s [%s] Enabled=1 turns it on)", kIniName, kIniSection);
        return;
    }
    g_hotkey = IniInt("Hotkey", kDefaultHotkey);
    const bool stats = Menu().Install();
    const bool levelUp = InstallLevelUpMenu();
    MenuInput input;
    input.click = OnClick;
    input.hover = OnHover;
    input.release = []() { g_drag.End(); };
    input.wheel = OnWheel;
    input.cancel = []() { Menu().Close(); };
    input.opened = PushAll;
    input.closed = []() { g_drag.End(); };
    input.tick = OnTick;
    Menu().SetInput(input);
    const bool ticking = stats && levelUp && CanPostToMainThread() &&
                         StartTick(PostToMainThread, kTickMs, Tick);
    Log("sheet: stats window %s, level-up %s, hotkey %d %s", stats ? "ok" : "FAILED",
        levelUp ? "ok" : "FAILED", g_hotkey, ticking ? "watching" : "NOT watching");
}

bool StatsSheetOpen() { return Menu().IsOpen(); }

}  // namespace tesruntime::mw
