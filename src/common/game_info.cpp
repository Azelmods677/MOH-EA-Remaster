#include "app/app.h"
#include "assault.h"
#include "capture.h"
#include "controls.h"
#include "credits.h"
#include "diagnostics.h"
#include "remaster.h"

namespace {

// after the settings load: the remaster's renderer extension, before the renderer is made
void Init() {
    mohea::DiagnosticsInit();
    mohea::RemasterInit();
}

// the game window is up: controls and the credit's font
void WindowUp(void* hwnd) {
    mohea::ControlsWindow(hwnd);
    mohea::CreditsWindow();
}

// window messages: F9 for the remaster, F11 and F12 for captures, then the controls
bool Message(void* hwnd, uint32_t msg, uintptr_t wp, intptr_t lp, intptr_t* result) {
    mohea::RemasterMessage(msg, wp, lp);
    mohea::CaptureMessage(msg, wp, lp);
    return mohea::ControlsMessage(hwnd, msg, wp, lp, result);
}

// each frame inside ImGui's: the credit, the remaster's labels, the capture notices, and the timed diagnostic captures
void Frame(double fps) {
    mohea::CreditsUi(fps);
    mohea::RemasterUi();
    mohea::CaptureUi();
    mohea::DiagnosticsFrame();
}

}  // namespace

// what the runtime asks of the game; strings must be set, hooks may stay null
const app::GameInfo app::kGame = {
    .title = L"Medal of Honor: European Assault",  // window and splash
    .short_title = L"MoH: European Assault",       // message boxes
    .name = L"MOHEA",                     // window classes, crash dumps, handover event
    .log = "mohea",                       // log file prefix
    .settings = "settings.toml",          // settings file beside the exe
    .splash = L"splash",                  // optional splash.png or splash.bmp beside the exe
    .missing = L"Put the game in the assets folder: its disc image (.iso), or default.xbe with its folders beside it.",
    .images = {{"default.xbe", "MOHEA"}},  // each recompiled xbe and its exe, for title launches
    .options = {                          // game settings kept in the settings file
        {"mouse_sensitivity", nullptr, &mohea::g_mouse_sensitivity},
        {"invert_mouse", &mohea::g_invert_mouse, nullptr},
        {"auto_capture", &mohea::g_auto_capture, nullptr},
        {"assault_mode", &mohea::g_assault, nullptr},
        {"extra_enemies", nullptr, &mohea::g_extra_enemies},
        {"extra_allies", nullptr, &mohea::g_extra_allies},
        {"remaster", &mohea::g_remaster, nullptr},
        {"remaster_fxaa", &mohea::g_fxaa, nullptr},
        {"remaster_sharpen", nullptr, &mohea::g_sharpen},
        {"remaster_bloom", nullptr, &mohea::g_bloom},
        {"remaster_color", nullptr, &mohea::g_color},
        {"remaster_vignette", nullptr, &mohea::g_vignette},
        {"remaster_grain", nullptr, &mohea::g_grain},
    },
    .load = nullptr,                      // reads more from the settings file's toml::table
    .save = mohea::RemasterSave,          // writes more into it
    .init = Init,                         // after the settings load, before the window and boot
    .loaded = nullptr,                    // image in memory, before its entry point runs
    .window = WindowUp,                   // the game window is up
    .message = Message,                   // window messages first; true takes one
    .ui = Frame,                          // ImGui drawing each frame
    .pad = mohea::ControlsPad,            // changes a polled pad: keyboard and mouse on port 1
    .rumble = nullptr,                    // changes a rumble before it is set
    .file_read = mohea::CreditsFileRead,  // a game file read: the Credits screen opening inside mohfe.viv
};
