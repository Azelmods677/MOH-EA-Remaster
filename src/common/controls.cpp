// PC controls: keyboard and mouse played as the console controller on port 1. The SDK reads only controllers
// (core/input.cpp), so the keys and the mouse are added to port 1's report, which also makes port 1 count as plugged in.
// The bindings follow the game's own "Sharp Shooter" layout (Options, Controller Settings):
//
//   action                  controller          keyboard and mouse
//   move, strafe            left stick          W A S D
//   turn, look              right stick         mouse
//   fire                    right trigger       left button
//   aim                     left trigger        right button
//   jump, stand             Y                   Space
//   crouch, prone           X                   C, left Ctrl
//   change weapon           B                   Q, wheel
//   action, reload          A                   R, E
//   adrenaline              black               F
//   medkit                  white               H
//   mission map             Back                Tab, M
//   pause                   Start               Esc
//   grenade                 d-pad up            G
//   recall squad            d-pad down          T
//   position squad          left stick click    Z
//   melee                   right stick click   V, middle button
//   menus                   d-pad, A, B         arrows, Enter (A), Backspace (B)
//
// The mouse turns through the right stick: each poll's motion becomes a stick push. A true mouse look, adding the
// motion to the camera angles, needs the game's camera code found first. While playing the cursor is hidden and kept
// in the window; Esc (pause) shows it until Esc again or a click in the game.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>

#include <imgui.h>

#include "controls.h"
#include "core/input.h"

namespace mohea {

uint32_t g_mouse_sensitivity = 100;
bool g_invert_mouse = false;

namespace {

std::atomic<HWND> g_window{nullptr};   // the window the messages come to
std::atomic<HWND> g_root{nullptr};     // its top level window, for focus
std::atomic<int64_t> g_mouse_x{0}, g_mouse_y{0};  // raw motion since the last poll
std::atomic<uint64_t> g_wheel_until{0};           // change weapon held until then
std::atomic<bool> g_captured{false};
// Esc (pause) shows the cursor and stops the mouse look; Esc again or a click in the game hides it
std::atomic<bool> g_released{false};
// keys and buttons held according to the window's messages: input that reaches the window as messages only (remappers,
// automation) moves the game too, not just what GetAsyncKeyState sees
std::atomic<bool> g_held[256];

// pad.buttons bits, as core/input.h orders them
constexpr uint16_t kUp = 1 << 0, kDown = 1 << 1, kLeft = 1 << 2, kRight = 1 << 3, kStart = 1 << 4, kBack = 1 << 5,
                   kLeftThumb = 1 << 6, kRightThumb = 1 << 7;
// pad.analog slots
enum { kA, kB, kX, kY, kBlack, kWhite, kLeftTrigger, kRightTrigger };

// a mouse step past the game's stick dead zone, then this much per count; a pause shorter than kHoldMs keeps the last
// push, so two polls in one frame don't flicker
constexpr int kDeadZone = 6000;
constexpr int kPerCount = 600;
constexpr uint64_t kHoldMs = 25;
constexpr uint64_t kWheelMs = 120;

bool Focused() {
    HWND root = g_root;
    return root && GetForegroundWindow() == root;
}

bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) || g_held[vk & 0xFF]; }

void Hold(int vk, bool down) { g_held[vk & 0xFF] = down; }

void ReleaseAll() {
    for (auto& held : g_held) held = false;
}

// a full push either way; with neither key held the controller's own stick is kept
void KeyAxis(int16_t& stick, int negative, int positive) {
    if (!Down(negative) && !Down(positive)) return;
    stick = int16_t((Down(positive) ? 32767 : 0) - (Down(negative) ? 32767 : 0));
}

void Press(input::Pad& pad, int slot, bool down) {
    if (down) pad.analog[slot] = 0xFF;
}

// one axis of mouse motion into a stick push, holding the last push briefly between polls
struct MouseAxis {
    int16_t last = 0;
    uint64_t moved = 0;
    void Apply(int16_t& stick, int64_t counts, uint64_t now) {
        if (counts) {
            double push = kDeadZone + std::abs(double(counts)) * kPerCount * g_mouse_sensitivity / 100.0;
            last = int16_t(std::min(push, 32767.0) * (counts > 0 ? 1 : -1));
            moved = now;
        } else if (now - moved > kHoldMs) {
            last = 0;
        }
        if (last) stick = last;
    }
};

void Capture(bool on) {
    HWND window = g_window;
    if (!window) return;
    if (on) {
        RECT r;
        GetClientRect(window, &r);
        MapWindowPoints(window, nullptr, reinterpret_cast<POINT*>(&r), 2);
        ClipCursor(&r);
    } else {
        ClipCursor(nullptr);
    }
    g_captured = on;
}

}  // namespace

void ControlsWindow(void* hwnd) {
    HWND window = static_cast<HWND>(hwnd);
    g_window = window;
    g_root = GetAncestor(window, GA_ROOT);
    // relative mouse motion, without the cursor's acceleration and screen edges
    RAWINPUTDEVICE mouse{0x01, 0x02, 0, window};  // generic desktop, mouse
    RegisterRawInputDevices(&mouse, 1, sizeof(mouse));
    // ImGui sees the window's messages first and would set the arrow back every frame: the cursor is ours
    ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_NoMouseCursorChange;
}

bool ControlsMessage(void*, uint32_t msg, uintptr_t wp, intptr_t lp, intptr_t* result) {
    bool overlay = ImGui::GetCurrentContext() && ImGui::GetIO().WantCaptureMouse;  // the SDK's menu wants the cursor
    switch (msg) {
    case WM_INPUT: {
        RAWINPUT raw;
        UINT size = sizeof(raw);
        if (GetRawInputData(reinterpret_cast<HRAWINPUT>(lp), RID_INPUT, &raw, &size, sizeof(RAWINPUTHEADER)) == UINT(-1))
            break;
        if (raw.header.dwType != RIM_TYPEMOUSE || !Focused() || overlay || g_released) break;
        if (!(raw.data.mouse.usFlags & MOUSE_MOVE_ABSOLUTE)) {
            g_mouse_x += raw.data.mouse.lLastX;
            g_mouse_y += raw.data.mouse.lLastY;
        }
        if (raw.data.mouse.usButtonFlags & RI_MOUSE_WHEEL) g_wheel_until = GetTickCount64() + kWheelMs;
        break;  // the default handling still runs
    }
    case WM_ACTIVATE:
        if (LOWORD(wp) == WA_INACTIVE) ReleaseAll();
        Capture(LOWORD(wp) != WA_INACTIVE && !overlay && !g_released);
        break;
    case WM_KILLFOCUS:
        ReleaseAll();  // no key up comes for what was held when the focus went
        break;
    case WM_SIZE:
    case WM_MOVE:
        if (g_captured) Capture(true);
        break;
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        Hold(int(wp), true);
        if (wp == VK_ESCAPE && !(lp & (1 << 30))) {  // pressed now, not held
            g_released = !g_released;
            Capture(!g_released && !overlay);
        }
        break;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        Hold(int(wp), false);
        break;
    case WM_LBUTTONDOWN:
        Hold(VK_LBUTTON, true);
        if (g_released && !overlay) {
            g_released = false;
            Capture(true);
        }
        break;
    case WM_LBUTTONUP:
        Hold(VK_LBUTTON, false);
        break;
    case WM_RBUTTONDOWN:
    case WM_RBUTTONUP:
        Hold(VK_RBUTTON, msg == WM_RBUTTONDOWN);
        break;
    case WM_MBUTTONDOWN:
    case WM_MBUTTONUP:
        Hold(VK_MBUTTON, msg == WM_MBUTTONDOWN);
        break;
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT && Focused()) {
            bool shown = overlay || g_released;
            if (!shown && !g_captured) Capture(true);
            if (shown && g_captured) Capture(false);
            SetCursor(shown ? LoadCursorW(nullptr, IDC_ARROW) : nullptr);
            *result = TRUE;
            return true;
        }
        break;
    }
    return false;
}

void ControlsPad(int port, input::Pad& pad) {
    if (port != 0) return;
    pad.connected = true;
    if (!Focused()) return;  // keys typed into other windows don't play
    if (ImGui::GetCurrentContext() && ImGui::GetIO().WantCaptureKeyboard) return;

    uint64_t now = GetTickCount64();
    KeyAxis(pad.lx, 'A', 'D');
    KeyAxis(pad.ly, 'S', 'W');  // up is positive, as on the console

    static MouseAxis turn, look;
    int64_t dy = g_mouse_y.exchange(0);
    turn.Apply(pad.rx, g_mouse_x.exchange(0), now);
    look.Apply(pad.ry, g_invert_mouse ? dy : -dy, now);  // the mouse reports down as positive

    if (Down(VK_UP) || Down('G')) pad.buttons |= kUp;
    if (Down(VK_DOWN) || Down('T')) pad.buttons |= kDown;
    if (Down(VK_LEFT)) pad.buttons |= kLeft;
    if (Down(VK_RIGHT)) pad.buttons |= kRight;
    if (Down(VK_ESCAPE)) pad.buttons |= kStart;
    if (Down(VK_TAB) || Down('M')) pad.buttons |= kBack;
    if (Down('Z')) pad.buttons |= kLeftThumb;
    if (Down('V') || Down(VK_MBUTTON)) pad.buttons |= kRightThumb;

    Press(pad, kA, Down('R') || Down('E') || Down(VK_RETURN));
    Press(pad, kB, Down('Q') || Down(VK_BACK) || now < g_wheel_until);
    Press(pad, kX, Down('C') || Down(VK_LCONTROL));
    Press(pad, kY, Down(VK_SPACE));
    Press(pad, kBlack, Down('F'));
    Press(pad, kWhite, Down('H'));
    Press(pad, kLeftTrigger, Down(VK_RBUTTON));
    Press(pad, kRightTrigger, Down(VK_LBUTTON));
}

}  // namespace mohea
