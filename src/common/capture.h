#pragma once

#include <cstdint>

#include "gpu/ext.h"

namespace mohea {

// Screenshots of the frame as shown (with the remaster, or the original), at the render size, in screenshots\ beside
// the exe: F12 one PNG, F11 starts and stops a clip of PNGs at 15 a second, for GIFs and videos

// GameInfo::message: F11 and F12
void CaptureMessage(uint32_t msg, uintptr_t wp, intptr_t lp);
// each present, on the render thread: res is shown this time, in the pixel shader resource state
void CaptureFrame(gpu::Context& c, ID3D12Resource* res, D3D12_RESOURCE_STATES& state, DXGI_FORMAT fmt, uint32_t w,
                  uint32_t h);
// GameInfo::ui: "REC" while a clip records, a moment's notice after a screenshot
void CaptureUi();

}  // namespace mohea
