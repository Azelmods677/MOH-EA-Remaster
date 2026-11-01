#pragma once

#include <cstdint>

struct ImFont;

namespace mohea {

// the credit's font (Impact), or ImGui's own before the window is up
ImFont* CreditsFont();
// GameInfo::window: the credit's font, added before the renderer builds ImGui's font atlas
void CreditsWindow();
// GameInfo::ui: the port's credit over the first seconds of the game, and on the game's Credits screen
void CreditsUi(double fps);
// GameInfo::file_read: the Credits screen is up while the game reads scrns\credits.big from inside mohfe.viv
void CreditsFileRead(const wchar_t* path, uint64_t offset, uint32_t bytes);

}  // namespace mohea
