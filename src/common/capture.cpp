// Screenshots and clips. The shown frame is copied into a readback buffer and read four presents later, once the GPU
// is past it (the renderer keeps three frames in flight and waits for a frame's slot before reusing it); a worker
// thread writes the PNGs with WIC, so the render thread only copies rows.
#include "capture.h"

#include <objbase.h>
#include <wincodec.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <deque>
#include <filesystem>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <imgui.h>

#include "app/app.h"
#include "core/log.h"
#include "credits.h"

namespace mohea {

namespace {

namespace fs = std::filesystem;
using Microsoft::WRL::ComPtr;

constexpr uint64_t kReadAfter = 4;        // presents: past the renderer's three frames in flight
constexpr double kClipInterval = 1.0 / 15, kClipSeconds = 8, kNoticeSeconds = 1.5;
constexpr uint32_t kClipMaxWidth = 1280;  // wider clip frames are halved: a clip is for GIFs and videos

std::atomic<bool> g_shot{false};
std::atomic<bool> g_clip{false};
std::atomic<double> g_clip_started{0}, g_notice_at{-1};

double Now() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

fs::path ExeFolder() {
    wchar_t path[MAX_PATH];
    DWORD n = GetModuleFileNameW(nullptr, path, MAX_PATH);
    return n && n < MAX_PATH ? fs::path(path).parent_path() : fs::current_path();
}

std::string Stamp() {
    std::time_t now = std::time(nullptr);
    std::tm tm{};
    localtime_s(&tm, &now);
    char text[32];
    std::strftime(text, sizeof(text), "%Y%m%d_%H%M%S", &tm);
    return text;
}

// a frame read back: BGRA rows, alpha set; shown_w is its width on screen (the renderer stretches a 4:3 frame to 16:9
// when the display is wide), which the PNG gets
struct Picture {
    fs::path path;
    std::vector<uint8_t> px;
    uint32_t w = 0, h = 0;
    bool halve = false;
    uint32_t shown_w = 0;
};

// the PNG writer's queue
std::mutex g_lock;
std::condition_variable g_wake;
std::deque<Picture> g_queue;

void Halve(Picture& p) {
    uint32_t w = p.w / 2, h = p.h / 2;
    std::vector<uint8_t> out(size_t(w) * h * 4);
    for (uint32_t y = 0; y < h; y++)
        for (uint32_t x = 0; x < w; x++)
            for (int c = 0; c < 4; c++) {
                const uint8_t* s = &p.px[(size_t(y * 2) * p.w + x * 2) * 4 + c];
                size_t row = size_t(p.w) * 4;
                out[(size_t(y) * w + x) * 4 + c] = uint8_t((s[0] + s[4] + s[row] + s[row + 4] + 2) / 4);
            }
    p.px = std::move(out);
    p.w = w;
    p.h = h;
}

bool WritePng(IWICImagingFactory* wic, const Picture& p) {
    ComPtr<IWICBitmap> bitmap;
    ComPtr<IWICBitmapScaler> scaler;
    ComPtr<IWICBitmapSource> rgb;
    ComPtr<IWICStream> file;
    ComPtr<IWICBitmapEncoder> encoder;
    ComPtr<IWICBitmapFrameEncode> frame;
    WICPixelFormatGUID format = GUID_WICPixelFormat24bppBGR;
    uint32_t w = p.shown_w ? p.shown_w : p.w;
    HRESULT hr = wic->CreateBitmapFromMemory(p.w, p.h, GUID_WICPixelFormat32bppBGRA, p.w * 4, UINT(p.px.size()),
                                             const_cast<BYTE*>(p.px.data()), &bitmap);
    if (SUCCEEDED(hr)) hr = wic->CreateBitmapScaler(&scaler);
    if (SUCCEEDED(hr)) hr = scaler->Initialize(bitmap.Get(), w, p.h, WICBitmapInterpolationModeHighQualityCubic);
    if (SUCCEEDED(hr)) hr = WICConvertBitmapSource(GUID_WICPixelFormat24bppBGR, scaler.Get(), &rgb);
    if (SUCCEEDED(hr)) hr = wic->CreateStream(&file);
    if (SUCCEEDED(hr)) hr = file->InitializeFromFilename(p.path.c_str(), GENERIC_WRITE);
    if (SUCCEEDED(hr)) hr = wic->CreateEncoder(GUID_ContainerFormatPng, nullptr, &encoder);
    if (SUCCEEDED(hr)) hr = encoder->Initialize(file.Get(), WICBitmapEncoderNoCache);
    if (SUCCEEDED(hr)) hr = encoder->CreateNewFrame(&frame, nullptr);
    if (SUCCEEDED(hr)) hr = frame->Initialize(nullptr);
    if (SUCCEEDED(hr)) hr = frame->SetSize(w, p.h);
    if (SUCCEEDED(hr)) hr = frame->SetPixelFormat(&format);
    if (SUCCEEDED(hr)) hr = frame->WriteSource(rgb.Get(), nullptr);
    if (SUCCEEDED(hr)) hr = frame->Commit();
    if (SUCCEEDED(hr)) hr = encoder->Commit();
    return SUCCEEDED(hr);
}

void Writer() {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    ComPtr<IWICImagingFactory> wic;
    CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wic));
    for (;;) {
        Picture p;
        {
            std::unique_lock lock(g_lock);
            g_wake.wait(lock, [] { return !g_queue.empty(); });
            p = std::move(g_queue.front());
            g_queue.pop_front();
        }
        if (p.halve) {
            Halve(p);
            p.shown_w /= 2;
        }
        std::error_code ec;
        fs::create_directories(p.path.parent_path(), ec);
        if (!wic || !WritePng(wic.Get(), p)) LOGE("capture: %s not written", p.path.string().c_str());
    }
}

void Queue(Picture p) {
    static std::once_flag started;
    std::call_once(started, [] { std::thread(Writer).detach(); });
    {
        std::lock_guard lock(g_lock);
        g_queue.push_back(std::move(p));
    }
    g_wake.notify_one();
}

// a readback buffer and the frame copied into it
struct Slot {
    ComPtr<ID3D12Resource> buf;
    D3D12_PLACED_SUBRESOURCE_FOOTPRINT fp{};
    uint64_t bytes = 0;
    uint32_t w = 0, h = 0;
    bool rgba = false;  // R8G8B8A8: red and blue swap on the way out
    bool busy = false;
    bool halve = false;
    uint64_t present = 0;
    fs::path path;
};
Slot g_slots[6];
uint64_t g_presents = 0;
double g_clip_last = 0;
uint32_t g_clip_frame = 0;
fs::path g_clip_folder;

// the rows out of a slot whose copy the GPU finished
void Read(Slot& s) {
    void* mapped = nullptr;
    D3D12_RANGE range{0, size_t(s.bytes)};
    if (SUCCEEDED(s.buf->Map(0, &range, &mapped))) {
        // as BlitFrame shows it: 16:9 on a wide display, else 4:3
        uint32_t shown_w = uint32_t(s.h * (app::Widescreen() ? 16.0 / 9.0 : 4.0 / 3.0) + 0.5);
        Picture p{s.path, std::vector<uint8_t>(size_t(s.w) * s.h * 4), s.w, s.h, s.halve, shown_w};
        const uint8_t* src = static_cast<const uint8_t*>(mapped) + s.fp.Offset;
        for (uint32_t y = 0; y < s.h; y++) {
            uint8_t* row = &p.px[size_t(y) * s.w * 4];
            std::memcpy(row, src + size_t(y) * s.fp.Footprint.RowPitch, size_t(s.w) * 4);
            for (uint32_t x = 0; x < s.w; x++) {
                if (s.rgba) std::swap(row[x * 4], row[x * 4 + 2]);
                row[x * 4 + 3] = 255;
            }
        }
        D3D12_RANGE none{0, 0};
        s.buf->Unmap(0, &none);
        Queue(std::move(p));
    }
    s.busy = false;
}

// copies res into a free slot, false when none is free or the format is not 8 bit colour
bool Copy(gpu::Context& c, ID3D12Resource* res, D3D12_RESOURCE_STATES& state, DXGI_FORMAT fmt, uint32_t w, uint32_t h,
          fs::path path, bool halve) {
    bool rgba = fmt == DXGI_FORMAT_R8G8B8A8_UNORM || fmt == DXGI_FORMAT_R8G8B8A8_UNORM_SRGB;
    if (!rgba && fmt != DXGI_FORMAT_B8G8R8A8_UNORM && fmt != DXGI_FORMAT_B8G8R8A8_UNORM_SRGB) {
        LOG_FIRST(4, "capture: the frame's format %d is not 8 bit colour", int(fmt));
        return false;
    }
    Slot* s = nullptr;
    for (Slot& slot : g_slots)
        if (!slot.busy) {
            s = &slot;
            break;
        }
    if (!s) return false;
    D3D12_RESOURCE_DESC td = res->GetDesc();
    UINT rows = 0;
    UINT64 row_bytes = 0, total = 0;
    D3D12_PLACED_SUBRESOURCE_FOOTPRINT fp{};
    c.Device()->GetCopyableFootprints(&td, 0, 1, 0, &fp, &rows, &row_bytes, &total);
    if (!s->buf || s->bytes < total) {
        if (s->buf) c.Release(std::move(s->buf));
        D3D12_HEAP_PROPERTIES hp{D3D12_HEAP_TYPE_READBACK};
        D3D12_RESOURCE_DESC bd{};
        bd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
        bd.Width = total;
        bd.Height = 1;
        bd.DepthOrArraySize = 1;
        bd.MipLevels = 1;
        bd.SampleDesc.Count = 1;
        bd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        if (FAILED(c.Device()->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &bd, D3D12_RESOURCE_STATE_COPY_DEST,
                                                       nullptr, IID_PPV_ARGS(&s->buf)))) {
            LOGE("capture: no readback buffer of %llu bytes", static_cast<unsigned long long>(total));
            return false;
        }
        s->bytes = total;
    }
    c.Transition(res, state, D3D12_RESOURCE_STATE_COPY_SOURCE);
    D3D12_TEXTURE_COPY_LOCATION dst{s->buf.Get(), D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT};
    dst.PlacedFootprint = fp;
    D3D12_TEXTURE_COPY_LOCATION src{res, D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX};
    src.SubresourceIndex = 0;
    c.List()->CopyTextureRegion(&dst, 0, 0, 0, &src, nullptr);
    c.Transition(res, state, D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    s->fp = fp;
    s->w = std::min<uint32_t>(w, uint32_t(td.Width));
    s->h = std::min<uint32_t>(h, td.Height);
    s->rgba = rgba;
    s->halve = halve;
    s->present = g_presents;
    s->path = std::move(path);
    s->busy = true;
    return true;
}

void Notice(const char* text, float alpha) {
    ImDrawList* draw = ImGui::GetForegroundDrawList();
    ImFont* font = CreditsFont();
    ImVec2 screen = ImGui::GetIO().DisplaySize;
    float size = screen.y * 0.03f;
    float w = font->CalcTextSizeA(size, screen.x, 0, text).x;
    ImVec2 at(screen.x * 0.97f - w, screen.y * 0.93f);
    draw->AddText(font, size, ImVec2(at.x + 2, at.y + 2), IM_COL32(0, 0, 0, int(200 * alpha)), text);
    draw->AddText(font, size, at, IM_COL32(235, 225, 205, int(255 * alpha)), text);
}

}  // namespace

void CaptureMessage(uint32_t msg, uintptr_t wp, intptr_t lp) {
    if (msg != WM_KEYDOWN || (lp & (1 << 30))) return;  // pressed now, not held
    if (wp == VK_F12) g_shot = true;
    if (wp == VK_F11) {
        bool on = !g_clip;
        if (on) g_clip_started = Now();
        g_clip = on;
        LOGI("capture: clip %s", on ? "started" : "stopped");
    }
}

void CaptureFrame(gpu::Context& c, ID3D12Resource* res, D3D12_RESOURCE_STATES& state, DXGI_FORMAT fmt, uint32_t w,
                  uint32_t h) {
    g_presents++;
    for (Slot& s : g_slots)
        if (s.busy && g_presents - s.present >= kReadAfter) Read(s);
    if (!res) return;
    if (g_shot.exchange(false)) {
        fs::path path = ExeFolder() / "screenshots" / ("MOHEA_" + Stamp() + "_" + std::to_string(g_presents) + ".png");
        if (Copy(c, res, state, fmt, w, h, path, false)) {
            LOGI("capture: %s", path.filename().string().c_str());
            g_notice_at = Now();
        }
    }
    double now = Now();
    if (g_clip && now - g_clip_started > kClipSeconds) {
        g_clip = false;
        LOGI("capture: clip stopped after %.0f s", kClipSeconds);
    }
    if (!g_clip) {
        g_clip_folder.clear();
        return;
    }
    if (g_clip_folder.empty()) {
        g_clip_folder = ExeFolder() / "screenshots" / ("clip_" + Stamp());
        g_clip_frame = 0;
        g_clip_last = 0;
    }
    if (now - g_clip_last < kClipInterval) return;
    char name[16];
    std::snprintf(name, sizeof(name), "%04u.png", g_clip_frame);
    if (Copy(c, res, state, fmt, w, h, g_clip_folder / name, w > kClipMaxWidth)) {
        g_clip_frame++;
        g_clip_last = now;
    }
}

void CaptureUi() {
    if (g_clip) {
        float blink = std::fmod(Now(), 1.0) < 0.5 ? 1.0f : 0.4f;
        Notice("REC", blink);
        return;
    }
    double t = Now() - g_notice_at;
    if (t >= 0 && t < kNoticeSeconds) Notice("CAPTURA GUARDADA", float(std::min(1.0, (kNoticeSeconds - t) * 2)));
}

}  // namespace mohea
