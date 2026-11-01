<p align="center"><img src="docs/images/banner.png" alt="Medal of Honor: European Assault Remaster — port nativo para PC"></p>

# Medal of Honor: European Assault Remaster — Port nativo para PC

Port nativo no oficial para PC de la versión de **Xbox original** de *Medal of Honor: European Assault* (2005), con un
**remaster visual** propio, creado por **AzelModsX677** como proyecto de ingeniería inversa.

El código x86 del juego se recompila a C++ con [Xbox XBE Recomp](https://github.com/TGP482/XboxXBERecomp) y se compila
como un ejecutable de Windows de 64 bits. Direct3D 8, DirectSound y el kernel de la Xbox se sustituyen por
Direct3D 12, XAudio2 y Win32. No es un emulador: el juego corre como un programa de PC, y encima de su imagen el
remaster añade antialiasing, nitidez, *bloom*, corrección de color, viñeta y grano de película.

> [!NOTE]
> Este proyecto **no incluye ningún archivo del juego** (ni el disco, ni el `default.xbe`, ni sus datos, ni el código
> traducido). Necesitas tu propia copia legal de la versión de Xbox para compilarlo o jugarlo.

> [!WARNING]
> **En desarrollo.** La campaña se juega de principio a fin en las pruebas, pero quedan problemas conocidos
> (ver [Estado](#estado)).

<p align="center">
  <img src="docs/images/original-vs-remaster.webp" alt="St. Nazaire: el original de Xbox y el remaster, la misma escena">
</p>

<p align="center">
  <img src="docs/images/combate.gif" width="49%" alt="Modo Asalto: una fila de aliados abre fuego en el muelle">
  <img src="docs/images/remaster-comparacion.webp" width="49%" alt="F9: sin efectos a la izquierda, remaster a la derecha">
  <img src="docs/images/remaster-beck.webp" width="49%" alt="El capitán Beck en el muelle de St. Nazaire, con el remaster">
  <img src="docs/images/menu-teclas.webp" width="49%" alt="Menú principal con teclas de PC en lugar de los botones de Xbox">
</p>

<p align="center"><sub>Capturas del juego tomadas con F12 y F11 dentro del propio port, en 16:9.</sub></p>

## Contenido

- [Del Xbox al PC: antes y después](#del-xbox-al-pc-antes-y-después)
- [Características](#características)
- [Remaster](#remaster)
- [Capturas y clips](#capturas-y-clips)
- [Modo Asalto](#modo-asalto--modded-by-azelmodsx677)
- [Controles](#controles)
- [Copia soportada](#copia-soportada)
- [Compilar](#compilar)
- [Estado](#estado)
- [Hoja de ruta del remaster](#hoja-de-ruta-del-remaster)
- [Herramientas propias](#herramientas-propias)
- [Créditos](#créditos)

## Del Xbox al PC: antes y después

Cada arreglo salió de ingeniería inversa del ejecutable; el proceso completo está en
[docs/APRENDIZAJE.md](docs/APRENDIZAJE.md).

| Antes | Después |
|---|---|
| <img src="docs/images/antes-fuentes.webp" alt="Letras con cajas negras"> | <img src="docs/images/perfil.webp" alt="Letras correctas"> |
| Las fuentes son texturas con paleta y el SDK no conocía `D3DDevice_SetPalette`: sin paleta, el fondo de cada letra era opaco. | Encontrada a mano en `0x2D9200` (su firma del XDK 5849 estaba vacía). |
| <img src="docs/images/antes-personajes.webp" alt="Personajes con estática gris"> | <img src="docs/images/gameplay-grua.webp" alt="Personajes con su textura"> |
| Las 55 texturas con paleta se dibujaban como índices grises: "estática de televisor". | El mismo arreglo: un dato encontrado, dos fallos resueltos. |

Otros arreglos del camino: cuatro crashes al arrancar (`D3D_FvfShader`, `SetViewport(NULL)`, `D3DDevice_Reset` y
`RunPushBuffer`), vídeos negros (el reproductor de EA escribe en la pantalla con la CPU sin `Lock`), y HUD y efectos
invisibles (`BeginPush`/`EndPush` sin firma).

## Características

- **Ejecutable nativo de Windows de 64 bits** con Direct3D 12 y XAudio2.
- **Resolución de tu pantalla** y **pantalla ancha 16:9**, en modo ventana sin bordes, ventana o pantalla completa;
  resolución interna configurable (`render_percent`) y filtrado anisotrópico.
- **Remaster visual**: FXAA, nitidez adaptativa, *bloom*, corrección de color, viñeta y grano, cada uno ajustable.
- **Comparación en directo**: F9 parte la pantalla en *original* y *remaster* sobre el mismo fotograma.
- **Capturas y clips** a resolución completa con F12 y F11.
- **Controles de PC completos**: teclado y ratón con el esquema del propio juego, cursor oculto mientras juegas, y
  mandos de Xbox, PlayStation y Switch.
- **Iconos de teclas de PC** ([Kenney Input Prompts](https://kenney.nl/assets/input-prompts), CC0) en lugar de los
  botones del mando en el HUD, los avisos y la barra de ayuda.
- **Pack de texturas HD con IA**: las texturas del mundo reescaladas con Real-ESRGAN, generado en tu PC a partir de tu
  copia.
- **Modo Asalto**: más aliados y enemigos en cada nivel.

## Remaster

El remaster son pasadas propias sobre cada fotograma, en la GPU, después de que el juego lo dibuja
([src/common/remaster.cpp](src/common/remaster.cpp)). La imagen del juego no se toca: **F9** la muestra tal cual al
momento.

<p align="center"><img src="docs/images/remaster-comparacion.webp" width="80%" alt="Comparación con F9"></p>

| F9 | Qué se ve |
|---|---|
| 1.ª vez | **Comparación**: a la izquierda sin efectos y a la derecha con ellos, sobre el mismo fotograma |
| 2.ª vez | **Original**: el juego como en la Xbox, sin efectos y sin el pack de texturas (vuelven los botones de Xbox) |
| 3.ª vez | **Remaster** otra vez |

| Efecto | Opción en `settings.toml` | Por defecto | Qué hace |
|---|---|---|---|
| Remaster | `remaster` | `true` | activa o quita todo |
| Antialiasing | `remaster_fxaa` | `true` | FXAA: suaviza los bordes en sierra; las zonas planas y el texto del HUD quedan igual |
| Nitidez | `remaster_sharpen` | `50` | nitidez adaptativa al contraste: recupera detalle sin halos |
| *Bloom* | `remaster_bloom` | `35` | brillo alrededor de focos, fuego y fogonazos |
| Color | `remaster_color` | `50` | saturación, sombras levantadas (el juego es muy oscuro) y un tono cálido de película |
| Viñeta | `remaster_vignette` | `35` | esquinas más oscuras |
| Grano | `remaster_grain` | `20` | grano de película animado |

Los valores van de `0` a `100`. Del SDK: `render_percent` (resolución interna; `200` = supermuestreo) y
`anisotropic_filtering` (texturas nítidas en ángulo; recomendado `16`).

### Pack de texturas HD
Las texturas del mundo (paredes, suelos, uniformes, armas) se reescalan con la IA
[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) en tu PC, a partir de las que vuelca tu propia copia: el pack no
se distribuye, porque son texturas del juego. Cada una se reescala ×4 y se reduce con Lanczos a su tamaño final (×4
hasta 128 píxeles, ×2 hasta 256), sin costuras en las que se repiten. Las letras, el HUD y las partículas se dejan
como están.

1. Juega un rato con `dump_textures = true` en `settings.toml` (vuelca cada textura que se dibuja).
2. Descarga `realesrgan-ncnn-vulkan` de su [release v0.2.5.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0)
   (funciona en gráficas AMD, NVIDIA e Intel) y descomprímelo.
3. Ejecuta:
   ```
   python tools\make_hd_pack.py --esrgan <carpeta de realesrgan-ncnn-vulkan>
   ```
   El pack queda en `out\build\release\textures\replacement\hd`. Con `custom_textures = true` el juego lo usa al momento.

### Iconos de teclas

<p align="center">
  <img src="docs/images/menu-teclas.webp" width="49%" alt="Menú principal: E Select">
  <img src="docs/images/aviso-tecla.webp" width="49%" alt="Aviso del nivel: Press E to use Weapon">
</p>

Descarga [Kenney Input Prompts](https://kenney.nl/assets/input-prompts) y, después de una partida con
`dump_textures = true`:
```
python tools\make_key_icons.py --kenney "<carpeta del pack>\Keyboard & Mouse\Double"
```
Sin `--kenney`, la herramienta dibuja unas teclas propias.

## Capturas y clips

| Tecla | Qué guarda, en `screenshots\` junto al `.exe` |
|---|---|
| **F12** | una captura PNG del fotograma tal como se ve (con el remaster, el original o la comparación) |
| **F11** | un clip: imágenes PNG a 15 por segundo hasta pulsar F11 otra vez (8 segundos como mucho) |

Las imágenes del README salen de ahí con `python tools\make_readme_media.py`: banner, comparaciones, GIF y un tráiler
MP4 1080p hecho con FFmpeg.

## Modo Asalto — modded by AzelModsX677

Más soldados de los dos bandos en cada nivel, sobre todo **aliados: +150 % en todos los niveles**, sin pasar de lo que
el juego aguanta. Se ajusta en `settings.toml` (porcentajes):

| Opción | Por defecto | Qué hace |
|---|---|---|
| `assault_mode` | `true` | activa el modo |
| `extra_enemies` | `50` | enemigos extra por cada enemigo del nivel (50 = uno más por cada dos) |
| `extra_allies` | `150` | aliados extra por cada aliado, en todos los niveles (150 = uno o dos más por cada uno) |

Los aliados extra son **soldados libres**: tu escuadrón (`PlayerSquad`) no se copia, así que sigues mandando a los
mismos compañeros, y tampoco los soldados de guion (cadáveres, muertes de la intro, cargas suicidas, escenas). Los jefes
(*Nemesis*) no se duplican. Las copias solo aparecen si caben en ese momento: respetan el límite de soldados vivos del
nivel dejándole 10 plazas, y comprueban que las reservas de objetos del juego tengan sitio de sobra (subir ese límite
llenaba la reserva y el juego se cerraba). Cómo se encontró el sistema de soldados: [docs/APRENDIZAJE.md, Fase 8](docs/APRENDIZAJE.md).

## Controles

<p align="center"><img src="docs/images/controles.webp" width="70%" alt="Esquema Sharp Shooter del juego"></p>

Las teclas siguen el esquema **Sharp Shooter** del propio juego (Options → Controller Settings):

| Acción | Teclado y ratón | Mando |
|---|---|---|
| Moverse | W A S D | stick izquierdo |
| Mirar | ratón | stick derecho |
| Disparar | clic izquierdo | gatillo derecho |
| Apuntar | clic derecho | gatillo izquierdo |
| Saltar, levantarse | Espacio | Y |
| Agacharse, tumbarse | C, Ctrl izquierdo | X |
| Cambiar de arma | Q, rueda del ratón | B |
| Acción, recargar | R, E | A |
| Adrenalina | F | negro |
| Botiquín | H | blanco |
| Mapa de la misión | Tab, M | Back |
| Pausa (muestra el cursor) | Esc | Start |
| Granada | G | cruceta arriba |
| Llamar al escuadrón | T | cruceta abajo |
| Posicionar al escuadrón | Z | clic del stick izquierdo |
| Cuerpo a cuerpo | V, botón central | clic del stick derecho |
| Menús: moverse, aceptar, volver | flechas, Enter, Retroceso | cruceta, A, B |

En `settings.toml` (junto al `.exe`): `mouse_sensitivity` (100 = normal) e `invert_mouse`.

Iconos de teclas: ver [Iconos de teclas](#iconos-de-teclas).

## Copia soportada

| | |
|---|---|
| Versión | Xbox, NTSC-U (Norteamérica), Title ID `0x4541005E` |
| `default.xbe` | SHA-1 `F194E90B50F9F2A5259ED941971B0B4C11583EEE` |
| XDK | 5849 |

Comprueba tu copia con `python tools\xbeinfo.py assets\default.xbe`.

## Compilar

### 1. Requisitos
- Windows 10/11 de 64 bits y una GPU con Direct3D 12.
- Visual Studio 2022 (o solo sus Build Tools) con MSVC y el Windows SDK.
- LLVM/Clang, CMake y Ninja.
- Git y Python 3 (`pip install capstone pillow` para las herramientas).

### 2. Poner los archivos del juego
Extrae tu disco en la carpeta `assets`. `default.xbe` tiene que quedar ahí, con la carpeta `DATA` al lado:
```
python tools\xdvdfs.py extract "<tu imagen>.iso" assets
```

### 3. Compilar
Ejecuta `.\build.bat`. La primera compilación recompila el juego y tarda bastante.
El ejecutable queda en `out\build\release\MOHEA.exe`.

## Estado

| Funciona | Problemas conocidos |
|---|---|
| Arranque, menús, perfiles y partidas guardadas | **Mirar con el ratón** pasa por el stick derecho (no es un *mouse look* real todavía) |
| Vídeos (logos, cinemáticas) | **Audio**: a veces se queda sin datos a tiempo y se oye un ruido al terminar una cinemática |
| Niveles, HUD, efectos, fuego y disparos | **Pack HD**: solo las texturas que se han volcado (por ahora, la primera misión) |
| Teclado, ratón y mandos | **Modo Asalto** sin probar en toda la campaña |
| Remaster, comparación, capturas y clips | |
| Iconos de teclas en menús, pausa, avisos y HUD | |

## Hoja de ruta del remaster

Hecho: pantalla ancha 16:9, antialiasing, nitidez, *bloom*, color, viñeta, grano, comparación en directo, capturas,
iconos de teclas de Kenney y pack de texturas HD con IA. Lo siguiente, de lo más cercano a lo más largo:

1. ***Mouse look* real**: sumar el movimiento del ratón directamente a la cámara del jugador.
2. **Campo de visión (FOV)** ajustable para pantallas anchas.
3. **Pack HD completo**: volcar las texturas de todas las campañas, no solo las del primer nivel.
4. **HDR interno y *bloom* físico**: guardar los colores por encima de 1 antes de recortarlos.
5. **Mejor iluminación y sombras** en los *shaders* del renderizador (`gpu::Extension::Shaders`).
6. **Modelos remasterizados** (soldados, armas): hace falta arte 3D nuevo y un sistema para cargarlo.

## Herramientas propias

- `tools/xdvdfs.py`: lista y extrae discos de Xbox (XISO y redump) y convierte un redump en XISO.
- `tools/xbeinfo.py`: muestra la cabecera de un `.xbe`: certificado, secciones y versión del XDK.
- `tools/xbedis.py`: desensambla código del `.xbe` con los nombres de `config/game.toml`.
- `tools/xbefuncs.py`: busca funciones por longitud, `ret`, constantes y llamadas.
- `tools/xbecalls.py`: grafo de llamadas (quién llama a quién, caminos hasta el SDK).
- `tools/xberefs.py`: quién usa una dirección o un texto.
- `tools/xbehw.py`: código que toca el hardware de la Xbox o campos del dispositivo sin inicializar.
- `tools/make_key_icons.py`: teclas de PC en lugar de los botones del mando.
- `tools/make_hd_pack.py`: pack de texturas HD con Real-ESRGAN, a partir de las texturas volcadas de tu copia.
- `tools/make_readme_media.py`: banner, comparaciones, GIF y tráiler MP4 a partir de capturas F12 y clips F11.

## Créditos

- **AzelModsX677**: port, ingeniería inversa, controles de PC, remaster y Modo Asalto.
- [Xbox XBE Recomp](https://github.com/TGP482/XboxXBERecomp) (MIT), el recompilador y el runtime en los que se basa este
  port; incluye arreglos propios descritos en [NOTAS_PROYECTO.md](NOTAS_PROYECTO.md).
- FXAA, de Timothy Lottes (NVIDIA), y la nitidez adaptativa de AMD FidelityFX CAS (MIT), como base de las pasadas del
  remaster, escritas de nuevo para este port.
- [Finest Hour Remastered](https://github.com/crazyriddler/FinestHourRemastered), otro port con el mismo recompilador, como
  inspiración de lo que un remaster puede llegar a ser.
- [Kenney Input Prompts](https://kenney.nl/assets/input-prompts) (CC0) para los iconos de teclas y ratón.
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (BSD-3), de Xintao Wang y colaboradores, para el pack HD.
- [FFmpeg](https://ffmpeg.org/) para el tráiler.
- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) por el diseño de funciones sustituibles y los hooks de instrucciones.
- [Zydis](https://github.com/zyantific/zydis) para decodificar x86, [toml++](https://github.com/marzer/tomlplusplus) para las configuraciones, [Dear ImGui](https://github.com/ocornut/imgui) para el menú de opciones y [SDL](https://github.com/libsdl-org/SDL) para la ventana, la entrada y los mandos.
- [Capstone](https://www.capstone-engine.org/) y [Pillow](https://python-pillow.org/) en las herramientas.

*Medal of Honor* y *European Assault* son marcas de Electronic Arts. Este proyecto no está afiliado ni respaldado por
Electronic Arts; es un trabajo de aficionado con fines educativos, y necesitas tu propia copia del juego.
