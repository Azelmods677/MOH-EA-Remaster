#pragma once

#include <cstdint>

namespace input {
struct Pad;
}

namespace mohea {

// settings.toml options: mouse_sensitivity in percent (100 = default), invert_mouse
extern uint32_t g_mouse_sensitivity;
extern bool g_invert_mouse;

// GameInfo::window: the game window, for focus, the cursor and raw mouse input
void ControlsWindow(void* hwnd);
// GameInfo::message: raw mouse motion and wheel, cursor capture while the game has focus
bool ControlsMessage(void* hwnd, uint32_t msg, uintptr_t wp, intptr_t lp, intptr_t* result);
// GameInfo::pad: keyboard and mouse added to controller port 1
void ControlsPad(int port, input::Pad& pad);

}  // namespace mohea
