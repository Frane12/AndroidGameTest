# DRNAS Native Audacity 4 — Android ARM64

Experimental porting workspace for the **original Audacity 4** C++ / Qt application to Android ARM64. This is not an official Audacity build.

## Starting point

- Upstream: https://github.com/audacity/audacity
- Pinned release: `Audacity-4.0.1` (September 30, 2026)
- Framework: Qt 6.10.0, including host tools and Android arm64-v8a libraries
- Target: Android API 28+, using SDK API 36, NDK 27.2.12479018 and JDK 17
- Licensing: Audacity GNU GPL v3; retain all upstream notices and source availability.

**Current state: preflight / toolchain integration only. No runnable Audacity APK is claimed.**

## Approach

1. Clone the authentic upstream source at the pinned release, **including submodules**.
2. Install Android SDK/NDK and the Qt 6.10 host + Android toolchains.
3. Run the actual Audacity CMake configure step for Android; preserve diagnostics even when it fails.
4. Fix cross-platform assumptions incrementally in patches, without substituting an unrelated waveform demo for the native Audacity engine.
5. Once configure and link work, add the correct Android Qt Activity, permissions, low-latency audio backend, file picker and touch navigation.
6. Produce an installable signed/debug APK only when the actual Audacity target builds and Android packaging succeeds.

## CI

Workflow: `.github/workflows/drnas-audacity4-android-arm64.yml`

A push to this experimental branch that changes Audacity port files runs **configure diagnostics** automatically. It can also be run manually from GitHub Actions with a choice of `configure` or `build`. A failed configure/build is an expected useful diagnostic, **not** evidence of a successful port. All logs are uploaded as workflow artifacts.

## Priority issues

- Audacity 4 incorporates components and Muse Framework assumptions designed for Windows/macOS/Linux.
- Qt's Android ABI support does not automatically make Audacity's desktop audio backend work on Android.
- Review platform-dependent dependencies (PortAudio, filesystem, plugin hosting and process spawning), then integrate Android AAudio/Oboe or another proper Android backend.
- Fix QML/UI responsiveness using native touch gestures, no relative mouse overlay.
- Keep orientation fixed to landscape initially to simplify hit-testing and focus; revisit adaptive rotation afterward.

## References

- [Audacity 4 source/build documentation](https://github.com/audacity/audacity/blob/Audacity-4.0.1/BUILDING.md)
- [Qt 6.10 Android requirements](https://doc.qt.io/qt-6.10/android-getting-started.html)
