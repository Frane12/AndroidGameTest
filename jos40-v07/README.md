# Još 40 zora v0.7 — A810 test build

Based on v0.6. Sun/moon lighting now moves on Android too. Day/night is 600 seconds instead of 180; menu pauses the clock and old saves preserve their phase. Desert fog is disabled on startup and updates. Angela appears at the bottom right of the opening menu.

Ground shadows use one fixed-size 2D silhouette mask updated at 12 Hz, projected along the moving sun/moon direction and sampled by the sand shader. Directional shadow atlases stay disabled on all quality settings. Eco uses 768×128, other presets 1536×256. Collection is bounded to 128 nearby mesh primitives. This technique casts onto the flat outdoor ground, not walls or characters; distant scenery does not cast onto the play area.

GitHub Actions reconstructs the original sources, applies v0.5/v0.6/v0.7 patches, imports CC0 textures, runs headless regressions and exports the signed ARM64 Android APK. Smoke tests cover the 600-second cycle, fog, moving light, bounded nodes, save migration and pause. Desktop software Vulkan screenshots check the opening menu and day/night rendering; Android A810 hardware performance and stability still need device testing.
