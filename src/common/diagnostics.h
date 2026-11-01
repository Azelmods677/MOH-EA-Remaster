#pragma once

namespace mohea {

// settings.toml option: capture frames over the boot logos (movies) without pressing F3
extern bool g_auto_capture;

// GameInfo::init: the capture folder, before the renderer first asks for it
void DiagnosticsInit();
// GameInfo::ui, each frame: asks for the timed captures
void DiagnosticsFrame();

}  // namespace mohea
