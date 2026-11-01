// Remaster: the port's own last passes over each frame, through the SDK's renderer extension (gpu/ext.h, Present):
//   fxaa    FXAA anti-aliasing, after Timothy Lottes' FXAA, skipping flat areas so the HUD's text stays sharp
//   bright  the light above a threshold, at a quarter of the size
//   blur    a 9 tap Gaussian in 5 linear taps, across then down, twice: the bloom
//   finish  contrast adaptive sharpening (after AMD FidelityFX CAS), the bloom, colour grading, vignette and film grain;
//           in the comparison the original frame stays on the left of a white line
// The game's own frame is untouched: F9 shows it again at once.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <iterator>
#include <memory>

#include <imgui.h>
#include <toml++/toml.hpp>

#include "app/app.h"
#include "capture.h"
#include "core/log.h"
#include "credits.h"
#include "gpu/ext.h"
#include "remaster.h"

namespace mohea {

bool g_remaster = true;
bool g_fxaa = true;
uint32_t g_sharpen = 50;
uint32_t g_bloom = 35;
uint32_t g_color = 50;
uint32_t g_vignette = 35;
uint32_t g_grain = 20;

namespace {

using Microsoft::WRL::ComPtr;

constexpr DXGI_FORMAT kFormat = DXGI_FORMAT_B8G8R8A8_UNORM;
constexpr float kBloomThreshold = 0.62f;
constexpr double kToastSeconds = 2.0;

std::atomic<bool> g_compare{false};
std::atomic<double> g_toast_at{-1};
// F9's original is the console's look: the texture pack (HD textures, key icons) goes too, and the player's own
// custom_textures comes back after it, and into the settings file whatever F9 shows at the end
bool g_user_textures = true;
bool g_pack_hidden = false;

void HidePack(bool hide) {
    app::Settings& s = app::Get();
    if (hide && !g_pack_hidden) {
        g_user_textures = s.custom_textures;
        s.custom_textures = false;
    } else if (!hide && g_pack_hidden) {
        s.custom_textures = g_user_textures;
    }
    g_pack_hidden = hide;
}

double Now() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

float Percent(uint32_t v) { return float(std::min<uint32_t>(v, 100)) / 100.0f; }

// one source, an entry point per pass; the cbuffer is Pass's eight floats, the samplers the SDK's blit ones
const char* kHlsl = R"(
cbuffer P : register(b1) { float4 a; float4 b; };
Texture2D t0 : register(t0);
Texture2D t1 : register(t1);
Texture2D t2 : register(t2);
SamplerState ls : register(s0);
SamplerState ps : register(s1);
struct O { float4 p : SV_Position; float2 uv : TEXCOORD0; };
O vs(uint id : SV_VertexID) {
    O o;
    o.uv = float2((id << 1) & 2, id & 2);
    o.p = float4(o.uv * float2(2, -2) + float2(-1, 1), 0, 1);
    return o;
}
float Luma(float3 c) { return dot(c, float3(0.299, 0.587, 0.114)); }
float3 Tap(Texture2D t, float2 uv) { return t.SampleLevel(ls, uv, 0).rgb; }
float2 Texel(Texture2D t) {
    float w, h;
    t.GetDimensions(w, h);
    return 1 / float2(w, h);
}
float4 fxaa(O i) : SV_Target {
    float2 px = Texel(t0);
    float3 m = Tap(t0, i.uv);
    float3 nw = Tap(t0, i.uv + float2(-1, -1) * px), ne = Tap(t0, i.uv + float2(1, -1) * px);
    float3 sw = Tap(t0, i.uv + float2(-1, 1) * px), se = Tap(t0, i.uv + float2(1, 1) * px);
    float lm = Luma(m), lnw = Luma(nw), lne = Luma(ne), lsw = Luma(sw), lse = Luma(se);
    float lmin = min(lm, min(min(lnw, lne), min(lsw, lse)));
    float lmax = max(lm, max(max(lnw, lne), max(lsw, lse)));
    if (lmax - lmin < max(0.0312, lmax * 0.125)) return float4(m, 1);
    float2 dir = float2((lsw + lse) - (lnw + lne), (lnw + lsw) - (lne + lse));
    float reduce = max((lnw + lne + lsw + lse) * (0.25 / 8), 1.0 / 128);
    dir = clamp(dir / (min(abs(dir.x), abs(dir.y)) + reduce), -8, 8) * px;
    float3 two = 0.5 * (Tap(t0, i.uv + dir * (1.0 / 3 - 0.5)) + Tap(t0, i.uv + dir * (2.0 / 3 - 0.5)));
    float3 four = two * 0.5 + 0.25 * (Tap(t0, i.uv - dir * 0.5) + Tap(t0, i.uv + dir * 0.5));
    float l4 = Luma(four);
    return float4(l4 < lmin || l4 > lmax ? two : four, 1);
}
float4 bright(O i) : SV_Target {
    float2 px = Texel(t0);
    float3 c = Tap(t0, i.uv + float2(-1, -1) * px) + Tap(t0, i.uv + float2(1, -1) * px) +
               Tap(t0, i.uv + float2(-1, 1) * px) + Tap(t0, i.uv + float2(1, 1) * px);
    c *= 0.25;
    float k = saturate((Luma(c) - a.x) / (1 - a.x));
    return float4(c * k * k, 1);
}
float4 blur(O i) : SV_Target {
    float2 d = a.zw * Texel(t0);
    float3 c = Tap(t0, i.uv) * 0.2270270270;
    c += (Tap(t0, i.uv + d * 1.3846153846) + Tap(t0, i.uv - d * 1.3846153846)) * 0.3162162162;
    c += (Tap(t0, i.uv + d * 3.2307692308) + Tap(t0, i.uv - d * 3.2307692308)) * 0.0702702703;
    return float4(c, 1);
}
float Noise(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }
float4 finish(O i) : SV_Target {
    float2 px = Texel(t0);
    float3 c = Tap(t0, i.uv);
    if (a.x > 0) {
        float3 l = Tap(t0, i.uv - float2(px.x, 0)), r = Tap(t0, i.uv + float2(px.x, 0));
        float3 u = Tap(t0, i.uv - float2(0, px.y)), d = Tap(t0, i.uv + float2(0, px.y));
        float3 mn = min(c, min(min(l, r), min(u, d)));
        float3 mx = max(c, max(max(l, r), max(u, d)));
        float3 amp = sqrt(saturate(min(mn, 1 - mx) / max(mx, 0.0001)));
        float3 w = -amp / lerp(8.0, 5.0, a.x);
        c = saturate((c + (l + r + u + d) * w) / (1 + 4 * w));
    }
    c += Tap(t1, i.uv) * a.y;
    if (a.z > 0) {
        float l = Luma(c);
        c = saturate(lerp(c, lerp(l.xxx, c, 1.2), a.z));
        // the game is dark: a gamma below 1 lifts the shadows and keeps the whites, where a contrast curve buried them
        c = pow(c, lerp(1.0, 0.8, a.z));
        c *= lerp(float3(1, 1, 1), float3(1.03, 1.0, 0.95), a.z);
    }
    if (a.w > 0) c *= lerp(1.0, 1 - smoothstep(0.25, 0.8, length(i.uv - 0.5)), a.w * 0.45);
    if (b.x > 0) {
        float n = Noise(i.uv / Texel(t0) + b.y) - 0.5;
        c += n * 0.08 * b.x * (1 - abs(Luma(c) * 2 - 1) * 0.5);
    }
    if (i.uv.x < b.z) c = t2.SampleLevel(ps, i.uv, 0).rgb;
    if (abs(i.uv.x - b.z) < px.x * 1.5) c = 1;
    return float4(saturate(c), 1);
}
)";

// a render target of the extension's own, with its RTV
struct Buffer {
    ComPtr<ID3D12Resource> res;
    D3D12_RESOURCE_STATES state = D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
    D3D12_CPU_DESCRIPTOR_HANDLE rtv{};
    uint32_t w = 0, h = 0;
};

class Remaster : public gpu::Extension {
public:
    ID3D12Resource* Present(gpu::Context& c, gpu::Target& t, DXGI_FORMAT& fmt) override {
        ID3D12Resource* shown = Remastered(c, t);
        if (shown) {
            fmt = kFormat;
            CaptureFrame(c, shown, out_.state, kFormat, t.w, t.h);
        } else {
            if (t.res) c.Transition(t.res.Get(), t.state, D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
            CaptureFrame(c, t.res.Get(), t.state, t.fmt, t.w, t.h);
        }
        return shown;
    }

private:
    // the passes over the frame: the last one's buffer, or null to show the frame as it is
    ID3D12Resource* Remastered(gpu::Context& c, gpu::Target& t) {
        if (!g_remaster || !t.res || t.depth || !Ensure(c, t.w, t.h)) return nullptr;
        c.Transition(t.res.Get(), t.state, D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
        ID3D12Resource* frame = t.res.Get();
        ID3D12Resource* cur = frame;
        DXGI_FORMAT cur_fmt = t.fmt;
        if (g_fxaa) {
            Draw(c, "fxaa", aa_, {cur, nullptr, nullptr}, {cur_fmt, kFormat, kFormat}, {});
            cur = aa_.res.Get();
            cur_fmt = kFormat;
        }
        float bloom = Percent(g_bloom);
        if (bloom > 0) {
            Draw(c, "bright", bloom_[0], {cur, nullptr, nullptr}, {cur_fmt, kFormat, kFormat}, {kBloomThreshold});
            // across then down, the second time twice as wide
            for (float spread : {1.0f, 2.0f}) {
                Draw(c, "blur", bloom_[1], {bloom_[0].res.Get(), nullptr, nullptr}, {kFormat, kFormat, kFormat},
                     {0, 0, spread, 0});
                Draw(c, "blur", bloom_[0], {bloom_[1].res.Get(), nullptr, nullptr}, {kFormat, kFormat, kFormat},
                     {0, 0, 0, spread});
            }
        }
        Draw(c, "finish", out_, {cur, bloom > 0 ? bloom_[0].res.Get() : nullptr, frame}, {cur_fmt, kFormat, t.fmt},
             {Percent(g_sharpen), bloom * 0.6f, Percent(g_color), Percent(g_vignette), Percent(g_grain),
              float(frame_++ % 64), g_compare ? 0.5f : -1.0f, 0});
        return out_.res.Get();
    }

    struct Sources {
        ID3D12Resource* res[3];
    };
    struct Formats {
        DXGI_FORMAT fmt[3];
    };
    struct Params {
        float p[8];
    };

    void Draw(gpu::Context& c, const char* entry, Buffer& dst, Sources src, Formats f, Params p) {
        c.Transition(dst.res.Get(), dst.state, D3D12_RESOURCE_STATE_RENDER_TARGET);
        c.Pass(kHlsl, entry, kFormat, dst.rtv, dst.w, dst.h, src.res, f.fmt, p.p, -1);
        c.Transition(dst.res.Get(), dst.state, D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    }

    bool Make(gpu::Context& c, Buffer& b, uint32_t w, uint32_t h, uint32_t slot) {
        if (b.res) c.Release(std::move(b.res));
        D3D12_HEAP_PROPERTIES hp{D3D12_HEAP_TYPE_DEFAULT};
        D3D12_RESOURCE_DESC d{};
        d.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
        d.Width = w;
        d.Height = h;
        d.DepthOrArraySize = 1;
        d.MipLevels = 1;
        d.Format = kFormat;
        d.SampleDesc.Count = 1;
        d.Flags = D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;
        b.state = D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
        if (FAILED(c.Device()->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &d, b.state, nullptr,
                                                       IID_PPV_ARGS(&b.res)))) {
            return false;
        }
        b.rtv = rtv_heap_->GetCPUDescriptorHandleForHeapStart();
        b.rtv.ptr += size_t(slot) * c.Device()->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
        c.Device()->CreateRenderTargetView(b.res.Get(), nullptr, b.rtv);
        b.w = w;
        b.h = h;
        return true;
    }

    // the buffers for a w x h frame, made again when its size changes; false when they can't be made
    bool Ensure(gpu::Context& c, uint32_t w, uint32_t h) {
        if (w == w_ && h == h_) return ok_;
        w_ = w;
        h_ = h;
        if (!rtv_heap_) {
            D3D12_DESCRIPTOR_HEAP_DESC hd{D3D12_DESCRIPTOR_HEAP_TYPE_RTV, 4, D3D12_DESCRIPTOR_HEAP_FLAG_NONE, 0};
            if (FAILED(c.Device()->CreateDescriptorHeap(&hd, IID_PPV_ARGS(&rtv_heap_)))) return ok_ = false;
        }
        uint32_t qw = std::max(w / 4, 1u), qh = std::max(h / 4, 1u);
        ok_ = Make(c, aa_, w, h, 0) && Make(c, out_, w, h, 1) && Make(c, bloom_[0], qw, qh, 2) &&
              Make(c, bloom_[1], qw, qh, 3);
        if (ok_) {
            LOGI("remaster: %ux%u frame, bloom at %ux%u", w, h, qw, qh);
        } else {
            LOGE("remaster: buffers for a %ux%u frame could not be made, showing the original", w, h);
        }
        return ok_;
    }

    ComPtr<ID3D12DescriptorHeap> rtv_heap_;
    Buffer aa_, out_, bloom_[2];
    uint32_t w_ = 0, h_ = 0;
    bool ok_ = false;
    uint64_t frame_ = 0;
};

const char* ModeName() {
    if (!g_remaster) return "ORIGINAL";
    return g_compare ? "COMPARACION: SIN EFECTOS | REMASTER" : "REMASTER";
}

void Label(ImDrawList* draw, ImFont* font, float size, ImVec2 at, const char* text, float alpha) {
    draw->AddText(font, size, ImVec2(at.x + 2, at.y + 2), IM_COL32(0, 0, 0, int(200 * alpha)), text);
    draw->AddText(font, size, at, IM_COL32(235, 225, 205, int(255 * alpha)), text);
}

}  // namespace

void RemasterInit() { gpu::SetExtension(std::make_unique<Remaster>()); }

void RemasterSave(void* table) {
    if (g_pack_hidden) static_cast<toml::table*>(table)->insert_or_assign("custom_textures", g_user_textures);
}

void RemasterMessage(uint32_t msg, uintptr_t wp, intptr_t lp) {
    if (msg != WM_KEYDOWN || wp != VK_F9 || (lp & (1 << 30))) return;  // pressed now, not held
    if (!g_remaster) {
        g_remaster = true;
        g_compare = false;
    } else if (!g_compare) {
        g_compare = true;
    } else {
        g_remaster = false;
        g_compare = false;
    }
    HidePack(!g_remaster);
    g_toast_at = Now();
    LOGI("remaster: %s", ModeName());
}

void RemasterUi() {
    ImDrawList* draw = ImGui::GetForegroundDrawList();
    ImFont* font = CreditsFont();
    ImVec2 screen = ImGui::GetIO().DisplaySize;
    float size = screen.y * 0.035f;
    if (g_remaster && g_compare) {
        // the pack is on in both halves: the left one only lacks the passes
        Label(draw, font, size, ImVec2(screen.x * 0.03f, screen.y * 0.04f), "SIN EFECTOS", 1);
        const char* right = "REMASTER";
        float w = font->CalcTextSizeA(size, screen.x, 0, right).x;
        Label(draw, font, size, ImVec2(screen.x * 0.97f - w, screen.y * 0.04f), right, 1);
    }
    double t = Now() - g_toast_at;
    if (t < 0 || t > kToastSeconds) return;
    const char* text = ModeName();
    float w = font->CalcTextSizeA(size, screen.x, 0, text).x;
    Label(draw, font, size, ImVec2(screen.x * 0.5f - w * 0.5f, screen.y * 0.12f), text,
          float(std::min(1.0, (kToastSeconds - t) * 2)));
}

}  // namespace mohea
