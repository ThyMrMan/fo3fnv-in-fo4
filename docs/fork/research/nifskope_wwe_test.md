# NifSkope Wild Wasteland Edition against Elric (2026-11-11)

Status: tested offline as a reference for replacing Elric
([item 5](../fo4_ck_replacements.md#options)); not used by the build. Repo:
[BungoV/NifSkope-WildWastelandEdition](https://github.com/BungoV/NifSkope-WildWastelandEdition)
(BSD-3), commit `d11a545` (2026-11-05). Where it sits among other tools:
[open landscape](fo4_open_landscape.md#hknp-writer).

## <a id="build"></a>Build

`tools_ext\build_nifskope_wwe.bat` builds it in its source folder
(`tools_ext\NifSkope-WWE`) with Qt 6.10.3 `mingw_64` and Qt's MinGW 13.1
(both from `aqt`, in `tools_ext\Qt`), Khronos Vulkan-Headers for
`bakert.cpp`, and `APIENTRY` defined (MSYS2's Qt pulls in `GL/gl.h`, Qt's
own binaries don't). MSVC fails on its code (`FloatVector4` ambiguities);
LLVM-MinGW fails on `pthread_gethandle`. Its README's MSYS2 package list
lacks the Vulkan headers. The post-link DLL copy fails on MSYS2's
`libb2-1.dll`; the exe is fine. `tools_ext\nifskope_wwe_cli.cmd <args>`
runs the headless CLI with Qt on PATH. The build runs half the cores (one
`cc1plus` per core held the machine). No source changes.

## <a id="tests"></a>Tests

Seven FNV meshes converted to our pre-Elric NIFs (`convert_static.convert`),
each also run through Elric (`elric_cache.process`): `nv_generalstore`
and `deckstep` (triangle meshes), `ammobox01`, `cratelarge01`,
`nv_prospectorsaloon_door` (convex), `acunit` (box in a transform), and the
gecko skeleton (25 bodies, 24 joints; Elric leaves it unconverted, our
creature ragdolls come another way).

| Test | Result |
|---|---|
| `collision --roundtrip` on Elric's output (decode, re-encode) | Byte-exact 6 of 6. With every shape rebuilt from its decoded values: exact for the 4 convex meshes, not the 2 triangle meshes |
| `Havok/Compile All Collision` on our pre-Elric NIFs as they are | Refuses all 7 (below) |
| The same after normalising the refused body settings | 6 of 6 compiled. Convex: same class, size, layer, material and body settings as Elric; volume and inertia 0.06–0.8% apart. Door, compiled keyframed: same 1,504 bytes and body record as Elric |
| Triangle meshes | Store: 1 material where Elric keeps 6, 313 vertices where Elric has 275; deck: 1 material where Elric keeps 2 |
| Gecko | Nothing written: one body still refused, and it then refuses the whole merge ("24 of 24 joints named a body this merge could not place") |
| Repeat runs | Byte-identical (store, crate, door); about 0.3 s per file, mostly process start |

**Refusals.** Compile accepts only motion systems 3, 5 and 6, Quality Type
and Solver Deactivation of the motion's default, Deactivator Type 1 and
Penetration Depth 0.15 (`collisiontools.cpp`, the
"not validated yet" check): our converter carries FNV's values (crate:
quality 1, depth 0.015; door and gecko: motion 4). Those fields' hknp
layout is unverified there, so it stops rather than drop them.

**Materials.** Our `collision.mesh` writes one `NiTriStripsData` per
material with the material CRC inside it; Elric reads it there. WWE's
`tlCollAppendEditableMesh` gives a `bhkNiTriStripsShape` its shape-level
material for every strip, and doesn't weld vertices shared between strips.

## <a id="verdict"></a>Verdict

Worth keeping as a reference: its convex, compressed-mesh, keyframed and
packfile writers produce Elric's layout (byte-exact round trips, matching
bodies), deterministically and fast. Not usable as a drop-in tool for us:
its compile gate refuses FNV's body settings, it loses per-strip materials,
and it writes no ragdoll. A writer of our own would port its encoders
(`src/gl/hknpencode.cpp`, `hknpdecode.cpp`) and feed them our shapes
directly, keeping our materials and FNV's settings.
