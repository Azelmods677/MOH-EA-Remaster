#pragma once

#include <cstdint>

namespace mohea {

// "Remaster": the port's own last passes over each frame. settings.toml options:
//   remaster           on or off (F9 cycles on, a comparison with the original on the left, and off: the console's
//                      look, without the texture pack either)
//   remaster_fxaa      FXAA anti-aliasing
//   remaster_sharpen   contrast adaptive sharpening, 0 to 100
//   remaster_bloom     glow around bright light, 0 to 100
//   remaster_color     colour grading: saturation, contrast and a warm tone, 0 to 100
//   remaster_vignette  darker corners, 0 to 100
//   remaster_grain     film grain, 0 to 100
extern bool g_remaster, g_fxaa;
extern uint32_t g_sharpen, g_bloom, g_color, g_vignette, g_grain;

// GameInfo::init: the renderer extension, before the renderer is made
void RemasterInit();
// GameInfo::save: the player's custom_textures, which F9's original turns off while it shows
void RemasterSave(void* table);
// GameInfo::message: F9
void RemasterMessage(uint32_t msg, uintptr_t wp, intptr_t lp);
// GameInfo::ui: the mode's name for a moment after F9, and the comparison's labels
void RemasterUi();

}  // namespace mohea
