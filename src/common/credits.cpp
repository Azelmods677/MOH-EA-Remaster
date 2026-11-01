// The port's credit, over the first seconds of the game and on the game's Credits screen, with the SDK's ImGui
// overlay: none of the game's files or screens are changed. The game's own EA and THX logos and credits still play.
#include <atomic>
#include <cctype>
#include <chrono>
#include <cstring>
#include <cwchar>
#include <fstream>
#include <iterator>
#include <mutex>
#include <string>
#include <vector>

#include <imgui.h>

#include "core/log.h"
#include "credits.h"

namespace mohea {

namespace {

constexpr double kShowSeconds = 7.0, kFadeSeconds = 1.5;
constexpr const char* kFontFile = "C:\\Windows\\Fonts\\impact.ttf";
constexpr float kFontPixels = 64.0f;

struct Line {
    const char* text;
    float height;  // share of the screen height
};
constexpr Line kLines[] = {
    {"MEDAL OF HONOR: EUROPEAN ASSAULT", 0.040f},
    {"Port nativo para PC", 0.032f},
    {"por AzelModsX677", 0.050f},
};

ImFont* g_font = nullptr;

// the Credits screen is the last menu screen the game read from mohfe.viv; the movies other screens load inside
// themselves don't count
std::atomic<bool> g_credits_screen{false};
constexpr const char* kInnerMovies[] = {"helpbar", "mcfx", "boot", "bgplaque", "dialoguewindow"};

// where each menu screen lies inside mohfe.viv
struct Screen {
    uint64_t begin, end;
    bool credits;
};
std::vector<Screen> g_screens;
std::once_flag g_screens_read;

uint32_t BigEndian(const unsigned char* p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; }

// mohfe.viv is an EA BIG archive: "BIGF", then at 8 the file count and at 12 the header size, both big endian, then
// for each file its offset and size (big endian) and its zero ended name ("scrns\credits.big")
void ReadScreens(const wchar_t* path) {
    std::ifstream f(path, std::ios::binary);
    unsigned char head[16];
    if (!f.read(reinterpret_cast<char*>(head), sizeof(head)) || std::memcmp(head, "BIGF", 4) != 0) return;
    uint32_t count = BigEndian(head + 8), size = BigEndian(head + 12);
    std::vector<unsigned char> toc(size);
    f.seekg(0);
    if (size < 16 || !f.read(reinterpret_cast<char*>(toc.data()), size)) return;
    for (size_t p = 16, i = 0; i < count && p + 8 < toc.size(); i++) {
        uint32_t offset = BigEndian(&toc[p]), bytes = BigEndian(&toc[p + 4]);
        std::string name;
        for (p += 8; p < toc.size() && toc[p]; p++) name += char(std::tolower(toc[p]));
        p++;
        if (name.rfind("scrns\\", 0) != 0) continue;
        bool inner = false;
        for (const char* movie : kInnerMovies) inner |= name.find(movie) != std::string::npos;
        if (!inner) g_screens.push_back({offset, uint64_t(offset) + bytes, name == "scrns\\credits.big"});
    }
    LOGI("credits: %zu menu screens in mohfe.viv", g_screens.size());
}

constexpr Line kScreenLines[] = {
    {"PC Port", 0.030f},
    {"AzelModsX677", 0.042f},
};

}  // namespace

ImFont* CreditsFont() { return g_font ? g_font : ImGui::GetFont(); }

namespace {

void DrawLines(const Line* lines, size_t count, float top, float alpha) {
    ImDrawList* draw = ImGui::GetForegroundDrawList();
    ImFont* font = CreditsFont();
    ImVec2 screen = ImGui::GetIO().DisplaySize;
    float y = screen.y * top;
    for (size_t i = 0; i < count; i++) {
        float size = screen.y * lines[i].height;
        ImVec2 extent = font->CalcTextSizeA(size, screen.x, 0.0f, lines[i].text);
        ImVec2 at(screen.x * 0.5f - extent.x * 0.5f, y);
        draw->AddText(font, size, ImVec2(at.x + 3, at.y + 3), IM_COL32(0, 0, 0, int(200 * alpha)), lines[i].text);
        draw->AddText(font, size, at, IM_COL32(235, 225, 205, int(255 * alpha)), lines[i].text);
        y += extent.y * 1.15f;
    }
}

}  // namespace

// path ends with name, any case
bool EndsWith(const wchar_t* path, const wchar_t* name) {
    size_t length = std::wcslen(path), n = std::wcslen(name);
    return length >= n && _wcsicmp(path + length - n, name) == 0;
}

void CreditsFileRead(const wchar_t* path, uint64_t offset, uint32_t) {
    // menus stream their music all the time: only a level's own file means the menus are gone
    if (EndsWith(path, L"level_a.str")) g_credits_screen = false;
    if (!EndsWith(path, L"mohfe.viv")) return;
    std::call_once(g_screens_read, ReadScreens, path);
    for (const Screen& s : g_screens)
        if (offset >= s.begin && offset < s.end) {
            if (s.credits != g_credits_screen) LOGI("credits: Credits screen %s", s.credits ? "open" : "closed");
            g_credits_screen = s.credits;
            return;
        }
}

void CreditsWindow() {
    ImGuiIO& io = ImGui::GetIO();
    // the SDK's menu keeps the default font: it is added first, so it stays the default
    if (io.Fonts->Fonts.empty()) io.Fonts->AddFontDefault();
    g_font = io.Fonts->AddFontFromFileTTF(kFontFile, kFontPixels);
}

void CreditsUi(double) {
    if (g_credits_screen) DrawLines(kScreenLines, std::size(kScreenLines), 0.76f, 1.0f);

    using Clock = std::chrono::steady_clock;
    static const Clock::time_point start = Clock::now();  // the first frame the game shows
    double t = std::chrono::duration<double>(Clock::now() - start).count();
    if (t > kShowSeconds + kFadeSeconds) return;
    float alpha = t < kShowSeconds ? 1.0f : float(1.0 - (t - kShowSeconds) / kFadeSeconds);
    DrawLines(kLines, std::size(kLines), 0.72f, alpha);
}

}  // namespace mohea
