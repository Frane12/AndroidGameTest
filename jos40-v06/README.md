# Još 40 zora v0.6 — Poly Haven desert and survival UI

Built on the user-confirmed stable v0.5 base for Snapdragon Adreno 810. `patch.b85` contains the compressed unified source diff, applied by `.github/workflows/build-jos40-v06.yml` after restoring the v0.5 project. The CI removes three unsupported `BaseMaterial3D.TEXTURE_REPEAT_ENABLED` assignments (Godot 4.5 uses material default); this fix is included directly in the downloadable v0.6 source ZIP.

The workflow fetches and validates two 1K CC0 Poly Haven **diffuse photographs**, embeds them as local APK assets (no runtime internet), checks both materials are bound and runs a smoke test for new game, sun cycle, save/load and menu, then exports a signed ARM64 APK.

- Sand 03 by Charlotte Baglioni: https://polyhaven.com/a/sand_03
- Sandstone Blocks 04 by Rob Tuytel: https://polyhaven.com/a/sandstone_blocks_04
- Poly Haven CC0: https://polyhaven.com/license

Changes: real textured sand, dunes and sandstone pyramids with face UVs, warmer key sunlight and darker ambient fill, revamped layered HUD, survival meters, day/night indicator and diary presentation. Old controls, Android package ID, save-slot format and single-shadow-light design are preserved.

This is a CI-tested build, not a measured A810 runtime test. Keep v0.5 installed or backed up until v0.6 is verified on device.
