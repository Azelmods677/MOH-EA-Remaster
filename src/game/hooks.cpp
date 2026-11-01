// Hooks for default.xbe. A strong definition replaces the recompiled function at that address, and __imp__ reaches
// the original, for example:
//
// X86_EXTERN_FUNC(__imp__sub_00012345);
// X86_FUNC(sub_00012345) {
//     __imp__sub_00012345(ctx, base);  // the original
// }
#include <algorithm>
#include <string>

#include "xdk/hle.h"

#include "../common/assault.h"
#include "core/log.h"
#include "kernel/memory.h"

namespace {

// committed guest memory past the null page: the image, and the pool and contiguous memory above 0x80000000, where the
// game keeps its spawners
bool GuestPointer(uint32_t va, uint32_t size = 4) {
    return va >= 0x10000 && mem::IsCommitted(va) && mem::IsCommitted(va + size - 1);
}

// a guest dword, 0 when the address cannot be one
uint32_t Read(uint8_t* base, uint32_t va) { return GuestPointer(va) ? *reinterpret_cast<uint32_t*>(base + va) : 0; }

// a guest string up to 128 characters, empty when the address cannot be one
std::string GuestText(uint8_t* base, uint32_t va) {
    std::string text;
    for (uint32_t i = 0; i < 128 && GuestPointer(va + i, 1) && base[va + i]; i++) text += char(base[va + i]);
    return text;
}

// the game's property names are CRC-32 hashes, sub_00194DB0: crc32("Team") = 0x64D20921
uint32_t PropertyHash(const std::string& name) {
    uint32_t crc = 0xFFFFFFFF;
    for (unsigned char c : name) {
        crc ^= c;
        for (int k = 0; k < 8; k++) crc = crc & 1 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
    }
    return ~crc;
}

// soldiers (Modo Asalto, src/common/assault.cpp)
constexpr uint32_t kSoldiersMax = 0x3A0330;        // the level's maximum of soldiers alive
constexpr uint32_t kSoldiersAlive = 0x3A0334;
// thiscall (property table, hash), the table at a definition + 8
constexpr uint32_t kPropertyLookup = 0x36790;      // the value
constexpr uint32_t kPropertyType = 0x36980;        // 2 and 8 hold text
constexpr uint32_t kPropertyText = 0x36820;        // the text, "" when missing
constexpr uint32_t kTeamAffiliation = 0x64D20921;  // "Team", the property "Unknown team affiliation" warns about
constexpr uint32_t kSpawnRequest = 0x396B0;
// the two callers, both with a spawner as the first argument: sub_000FC0C0 (soldiers spawners make while playing) and
// sub_000A1390 (the level's placed soldiers, with an often empty class, counting its spawns at [spawner + 0x40])
constexpr uint32_t kSpawnerRequestReturn = 0xFC1D1;
constexpr uint32_t kPlacedRequestReturn = 0xA1596;

// GameObjectFactory::AllocateGameObject (sub_000EF230, thiscall on a factory): its maximum at +4, the objects in use at
// +8, and null once they are equal, which sub_00038B70 writes through ([soldier + 0x14B4]). The factories a soldier
// takes from are noted while the game makes one, and a copy is only asked for while each has room to spare
constexpr uint32_t kFactoryMax = 4, kFactoryUsed = 8;
thread_local bool g_spawning = false;
uint32_t g_factories[8] = {};

void NoteFactory(uint32_t factory) {
    for (uint32_t& f : g_factories) {
        if (f == factory) return;
        if (!f) {
            f = factory;
            LOGI("assault: soldiers take objects from the factory at %08X", factory);
            return;
        }
    }
}

// room for a copy and for what the level and the fighting still make: an eighth of each factory, 8 at least
bool FactoriesHaveRoom(uint8_t* base) {
    for (uint32_t f : g_factories) {
        if (!f) break;
        uint32_t max = Read(base, f + kFactoryMax), used = Read(base, f + kFactoryUsed);
        if (used + std::max(8u, max / 8) >= max) return false;
    }
    return true;
}

// a text property of a definition, as sub_0003ADA0 reads one: its type, then its text
std::string PropertyText(X86Context& ctx, uint8_t* base, uint32_t definition, const std::string& name) {
    uint32_t hash = PropertyHash(name);
    ctx.ecx = definition + 8;
    uint32_t type = kernel::CallGuest(ctx, kPropertyType, {hash});
    if (type != 2 && type != 8) return {};
    return GuestText(base, kernel::CallGuest(ctx, kPropertyText, {hash}));
}

}  // namespace

// The object allocator: which factories a soldier's making takes from
X86_EXTERN_FUNC(__imp__sub_000EF230);
X86_FUNC(sub_000EF230) {
    uint32_t factory = ctx.ecx;
    __imp__sub_000EF230(ctx, base);
    if (g_spawning) NoteFactory(factory);
}

// Spawn request, cdecl (spawner, placement, class prefix): it spawns at once (sub_00038B70) while fewer than the
// maximum are alive, else queues the request (sub_00037510). Modo Asalto asks again for the soldiers of the two
// spawner callers, only while one fits now: the game's queue holds 15 and stays for the level's own soldiers. The
// level's own maximum stays (raising it ran the object factories dry: a crash at the 45th soldier), and the copies
// leave kAssaultReserve of it to the level. The copies don't go through the callers, so the spawners' own counts and
// limits are untouched, and they are free soldiers: the player's squad and scripted soldiers are never copied.
X86_EXTERN_FUNC(__imp__sub_000396B0);
X86_FUNC(sub_000396B0) {
    static thread_local bool copying = false;
    const uint32_t* stack = X86_PTR(uint32_t, ctx.esp);
    uint32_t back = stack[0], spawner = stack[1], placement = stack[2], cls = stack[3];
    g_spawning = true;
    __imp__sub_000396B0(ctx, base);
    g_spawning = false;
    if (copying) return;
    std::string prefix = GuestText(base, cls);
    const char* name = prefix.empty() ? "(sin clase)" : prefix.c_str();
    if (back != kSpawnerRequestReturn && back != kPlacedRequestReturn) {
        LOG_FIRST(16, "assault: spawn %s from %08X left single", name, back);
        return;
    }
    uint32_t result = ctx.eax, ecx = ctx.ecx;
    // the side, as sub_00038B70 reads it: the spawner's definition (0xA0E80 returns [[spawner + 0xC] + 4]), then
    // its team affiliation, 1 Allies and 2 Axis. Its squad and archetype too, under the class prefix: the player's
    // buddies come from spawn points like JP_NPCSpawnPoint_BeckSquad_01, with Archetypes\PlayerSquad.xdd
    mohea::Side side = mohea::Side::Unknown;
    std::string squad, archetype;
    uint32_t definition = Read(base, Read(base, spawner + 0xC) + 4);
    if (GuestPointer(definition)) {
        ctx.ecx = definition + 8;
        uint32_t team = kernel::CallGuest(ctx, kPropertyLookup, {kTeamAffiliation});
        side = team == 1 ? mohea::Side::Ally : team == 2 ? mohea::Side::Enemy : mohea::Side::Unknown;
        squad = PropertyText(ctx, base, definition, prefix + "Squad");
        archetype = PropertyText(ctx, base, definition, prefix + "Archetype_Resource");
    }
    ctx.ecx = ecx;
    int copies = mohea::AssaultCopies(side, name, squad.c_str(), archetype.c_str());
    LOG_FIRST(96, "assault: spawn %s from %08X side %d squad '%s' archetype '%s' alive %u of %u, %d more", name, back,
              int(side), squad.c_str(), archetype.c_str(), Read(base, kSoldiersAlive), Read(base, kSoldiersMax),
              copies);
    copying = true;
    for (int i = 0; i < copies; i++) {
        if (Read(base, kSoldiersAlive) + mohea::kAssaultReserve >= Read(base, kSoldiersMax) ||
            !FactoriesHaveRoom(base)) {
            LOG_FIRST(16, "assault: no room for more copies, alive %u of %u", Read(base, kSoldiersAlive),
                      Read(base, kSoldiersMax));
            break;
        }
        kernel::CallGuest(ctx, kSpawnRequest, {spawner, placement, cls});
    }
    copying = false;
    ctx.eax = result;
}
