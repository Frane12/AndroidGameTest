# DRNAS Native Stellarium — Android ARM64 experimental port

**Status: First signed APK built but crashes on-device; experimental startup assets fix in progress.**

This branch starts from the **real GPL-licensed Stellarium v26.3 desktop C++/Qt source**, pinned to commit
`3f23cf3a1a59523a9c7b1ec4540c33bca77addfa`.
It cross-compiles the authentic `stellarium` Qt Widgets / OpenGL ES application
with the official Qt 6.8.3 Android ARM64 packages and Android NDK.
No emulation, WebView imitation, or unrelated planetarium implementation is substituted.

## Build

GitHub Actions: [DRNAS Stellarium Native Android ARM64](../../actions/workflows/drnas-stellarium-android-arm64.yml).

The workflow installs Qt host + Android modules, fetches the pinned Stellarium tag,
sets a unique Android app ID, configures original CMake, compiles `stellarium`,
then invokes `stellarium_make_apk`. If compilation fails, logs are uploaded for debugging.
Only a successfully verified signed APK should be described as installable.

Intentionally disabled for the first proof: scripting, multimedia, QtWebEngine,
ShowMySky, spreadsheets, GPS and optional high-cost plugins. The star sky renderer
and desktop Qt GUI are **not replaced**.

## Next milestones

1. Green Android ARM64 configure + compile (real sources).
2. APK generated, signed, and ABI/manifest verified.
3. On-device boot with desktop sky viewport, resource paths and functional touch.
4. Restore plugins, catalogs, location/compass, and mobile-friendly UI controls.
5. Transfer isolated branch contents into a dedicated Stellarium port repository.

## Licensing

Upstream: https://github.com/Stellarium/stellarium (GPL-2.0-or-later / upstream license details).
Our build scripts are distributed with the intention of respecting upstream GPL obligations.
The original Stellarium source is fetched at build time, **not presented as an original DRNAS implementation**.

## Android start-up fix

The first signed APK (run 39712761275) was reported to crash at launch. Inspection found that the Android package source held **no Stellarium runtime assets**, whereas `StelFileMgr::init()` requires `assets:/data/ssystem_major.ini` or it aborts with `qFatal`. New APK staging copies actual upstream v26.3 `data`, stars, textures, nebula catalog, default sky culture and landscape into `android/assets`, including CMake-generated `data/default_cfg.ini`. CI rejects APKs missing essential assets. Native Android app configuration now uses app-private writable storage. This is a grounded suspected fix; **on-device validation is still required**.

For native logcat (device connected with USB debugging):

```sh
adb logcat -c
adb shell am force-stop org.drnas.stellarium.port
adb shell monkey -p org.drnas.stellarium.port 1
adb logcat -d -v time -s QtCore:V Qt:V AndroidRuntime:E libc:F DEBUG:E 'Stellarium:V' '*:S' > stellarium-android-startup.log
```

