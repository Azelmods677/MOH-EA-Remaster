// Diagnostics for making the port. With auto_capture = true in settings.toml three frames are captured over the boot
// logos, which are movies, into out\build\release\capture: what F3 does by hand with XBE_CAPTURE_DIR set (the SDK's
// frame capture writes every draw with its states and shaders, each target and the textures read).
#include <chrono>
#include <cstdlib>
#include <iterator>

#include "diagnostics.h"
#include "gpu/backend.h"

namespace mohea {

bool g_auto_capture = false;

namespace {

// seconds after the game's first frame: the EA logo (about 2 to 5 s), the THX logo (about 5 to 9 s), then the menu
constexpr double kCaptureAt[] = {3.0, 6.5, 10.0};

}  // namespace

void DiagnosticsInit() {
    // the SDK reads the folder once, at the first capture, from the C runtime's environment
    if (g_auto_capture && !_wgetenv(L"XBE_CAPTURE_DIR")) _wputenv_s(L"XBE_CAPTURE_DIR", L"capture");
}

void DiagnosticsFrame() {
    if (!g_auto_capture) return;
    using Clock = std::chrono::steady_clock;
    static const Clock::time_point start = Clock::now();
    static size_t next = 0;
    double t = std::chrono::duration<double>(Clock::now() - start).count();
    if (next < std::size(kCaptureAt) && t >= kCaptureAt[next]) {
        gpu::g_capture = true;  // the renderer captures the next frame it presents
        next++;
    }
}

}  // namespace mohea
