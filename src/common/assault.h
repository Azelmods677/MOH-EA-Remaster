#pragma once

#include <cstdint>

namespace mohea {

// "Modo Asalto": more soldiers on both sides. settings.toml options, percentages:
//   assault_mode   on or off
//   extra_enemies  extra enemies per enemy the level spawns (50 = one more for every two)
//   extra_allies   extra allies per ally, in every level; the player's squad stays as it is
extern bool g_assault;
extern uint32_t g_extra_enemies, g_extra_allies;

// of the level's own maximum of soldiers alive, what the copies leave to the level's soldiers: the maximum is what
// the game's object factories were sized for
constexpr uint32_t kAssaultReserve = 10;

// side of a spawn, from the soldier definition's team affiliation (1 Allies, 2 Axis)
enum class Side { Unknown, Ally, Enemy };

// how many extra copies of this spawn to ask for; class is the soldier's class prefix, which marks the bosses, and
// squad and archetype the spawner's, which mark the player's squad and the scripted soldiers
int AssaultCopies(Side side, const char* cls, const char* squad, const char* archetype);

}  // namespace mohea
