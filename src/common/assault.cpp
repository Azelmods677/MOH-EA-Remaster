// "Modo Asalto — modded by AzelModsX677": more allies and enemies in the levels. The decisions live here; the hooks
// that spawn the copies are in src/game/hooks.cpp. Found by reverse engineering (docs/APRENDIZAJE.md, Fase 8):
//   sub_00039330  at a level's start: the maximum of soldiers alive comes from the level's settings, into 0x3A0330
//   sub_000396B0  spawn request (spawner, placement, class): spawns at once while fewer than the maximum are alive,
//                 else waits in a queue of 15
//   0x3A04F0      the soldiers' pool: 75 entries, an empty one is written through a null pointer
//   sub_000EF230  the game object factories, which run dry before that pool: the level's maximum stays (Fase 11)
#include <cctype>
#include <cstring>
#include <random>
#include <string>

#include "assault.h"
#include "core/log.h"

namespace mohea {

bool g_assault = true;
uint32_t g_extra_enemies = 50;
uint32_t g_extra_allies = 150;

namespace {

// squads the level scripts: corpses, deaths in the intro, charges that end in death, gags and in-cutscene soldiers
// (St. Nazaire: DeadBody1, IntroDeath1, SuicideAlly1, BlowUpGag, QuartetICS1). A copy would repeat the scene.
constexpr const char* kScripted[] = {"dead", "death", "body", "suicide", "gag", "intro", "ics", "cine", "outro"};

bool Contains(const char* text, const char* word) {
    std::string lower;
    for (size_t i = 0; i < 128 && text && text[i]; i++) lower += char(std::tolower(static_cast<unsigned char>(text[i])));
    return lower.find(word) != std::string::npos;
}

// whole copies plus one more with the remainder's chance: 150 % gives 1, and 2 half the time
int Copies(uint32_t percent) {
    static std::mt19937 rng{std::random_device{}()};
    int copies = int(percent / 100);
    if (std::uniform_int_distribution<uint32_t>(0, 99)(rng) < percent % 100) copies++;
    return copies;
}

}  // namespace

int AssaultCopies(Side side, const char* cls, const char* squad, const char* archetype) {
    if (!g_assault || side == Side::Unknown) return 0;
    // bosses stay single: a second one could leave the mission's "kill the Nemesis" waiting
    if (Contains(cls, "nemesis") || Contains(cls, "boss")) return 0;
    // the player's buddies too: the copies are free soldiers, not more of the squad the player commands
    if (Contains(squad, "playersquad") || Contains(archetype, "playersquad")) return 0;
    for (const char* word : kScripted)
        if (Contains(squad, word)) return 0;
    return Copies(side == Side::Enemy ? g_extra_enemies : g_extra_allies);
}

}  // namespace mohea
