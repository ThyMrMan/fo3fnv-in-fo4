// Run archive (docs/fork/fo4_condition.md#run-archive): while the Trace mod is on (Data\F3NV_Trace.esl), each
// launch copies the previous run's logs into that run's folder under My Games\Fallout4\F3NV\Runs and opens a
// folder for this run holding the Data files it loads (name, size, write time), which tools.validate.fo4_runs
// matches to builds. Runs before the Papyrus VM opens its log, so Papyrus.0.log is still the previous run's.
#include "condition.h"

#include <shlobj.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

const char *TRACE_PLUGIN = "F3NV_Trace.esl";
const char *DATA_FILES = "data_files.tsv";

fs::path MyGames() {
    char path[MAX_PATH];
    if (FAILED(SHGetFolderPathA(nullptr, CSIDL_MYDOCUMENTS, nullptr, SHGFP_TYPE_CURRENT, path))) return {};
    return fs::path(path) / "My Games" / "Fallout4";
}

fs::path GameData() {
    char path[MAX_PATH];
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    return fs::path(path).parent_path() / "Data";
}

// The newest run folder in `runs` (names sort by time), or empty when none.
fs::path NewestRun(const fs::path &runs) {
    std::error_code ec;
    fs::path newest;
    for (auto &entry : fs::directory_iterator(runs, ec))
        if (entry.is_directory() && (newest.empty() || entry.path().filename() > newest.filename()))
            newest = entry.path();
    return newest;
}

// Copy into `to` each file of `from` named `prefix`*`suffix` written after `since`; how many.
int CopyNewer(const fs::path &from, const std::string &prefix, const std::string &suffix,
              fs::file_time_type since, const fs::path &to) {
    std::error_code ec;
    int copied = 0;
    for (auto &entry : fs::directory_iterator(from, ec)) {
        std::string name = entry.path().filename().string();
        bool named = name.size() >= prefix.size() + suffix.size() && !name.compare(0, prefix.size(), prefix) &&
                     !name.compare(name.size() - suffix.size(), suffix.size(), suffix);
        if (!named || !entry.is_regular_file() || entry.last_write_time(ec) <= since) continue;
        if (fs::copy_file(entry.path(), to / name, fs::copy_options::overwrite_existing, ec)) ++copied;
    }
    return copied;
}

// This launch's folder name: the local time, YYYY-MM-DD_HHMMSS.
std::string Now() {
    SYSTEMTIME t;
    GetLocalTime(&t);
    char name[32];
    snprintf(name, sizeof name, "%04u-%02u-%02u_%02u%02u%02u", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute,
             t.wSecond);
    return name;
}

// `run`'s data_files.tsv: each top-level file of `data` with its size and write time (FILETIME ticks).
void WriteDataFiles(const fs::path &data, const fs::path &run) {
    std::error_code ec;
    std::ofstream out(run / DATA_FILES, std::ios::binary);
    for (auto &entry : fs::directory_iterator(data, ec)) {
        if (!entry.is_regular_file(ec)) continue;
        out << entry.path().filename().string() << '\t' << entry.file_size(ec) << '\t'
            << entry.last_write_time(ec).time_since_epoch().count() << '\n';
    }
}

}  // namespace

namespace condition {

std::string ArchiveRun() {
    fs::path data = GameData(), games = MyGames();
    std::error_code ec;
    if (games.empty() || !fs::exists(data / TRACE_PLUGIN, ec)) return "";
    fs::path runs = games / "F3NV" / "Runs", previous = NewestRun(runs);
    std::string done;
    if (!previous.empty()) {
        auto since = fs::last_write_time(previous / DATA_FILES, ec);
        int logs = CopyNewer(games / "Logs" / "Script", "Papyrus.", ".log", since, previous) +
                   CopyNewer(games / "F4SE", "F3NV", ".log", since, previous) +
                   CopyNewer(games / "F4SE", "crash-", ".log", since, previous);
        done = std::to_string(logs) + " logs into " + previous.filename().string() + ", ";
    }
    fs::path run = runs / Now();
    fs::create_directories(run, ec);
    WriteDataFiles(data, run);
    return done + "this run " + run.string();
}

}  // namespace condition
