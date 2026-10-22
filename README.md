# DRNAS Android Port Lab

Native Android experiments and open-source software ports, developed and tested on real ARM64 Android devices.

**[Download builds and pre-releases](https://github.com/Frane12/AndroidGameTest/releases)** · [GitHub Actions](https://github.com/Frane12/AndroidGameTest/actions) · [Issues](https://github.com/Frane12/AndroidGameTest/issues)

## Featured project: Stellarium 26.3 for Android

An experimental **native ARM64 port of the original Stellarium desktop application**, built from the upstream C++ source using Qt 6.8.3 and OpenGL ES.

- Real Stellarium sky renderer, star catalogs and desktop GUI — not a web wrapper or emulator.
- Android adaptations for window placement, orientation, sky information and touch-friendly layout.
- Experimental Enhanced / Realistic sky appearance options.
- APKs are experimental and may contain visual or runtime issues.

**[Stellarium source and build instructions](https://github.com/Frane12/AndroidGameTest/tree/experiment/stellarium-native-android-26-3/stellarium)**

**[Stellarium Android build history](https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-stellarium-android-arm64.yml)**

## Where to get the APK

Visit **[Releases](https://github.com/Frane12/AndroidGameTest/releases)** and open the latest Stellarium **pre-release**. Under **Assets**, download the Android ARM64 `.apk` if one has been published.

If no APK is listed yet, check the [Stellarium Actions workflow](https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-stellarium-android-arm64.yml) for a successful build with a downloadable artifact. GitHub Actions artifacts may require signing in and can expire or be deleted.

## Development status

This repository hosts experimental work. The current Stellarium Android port is **pre-alpha** and is not an official release from the Stellarium project. The original application and its assets remain subject to their upstream licenses and notices.

Testing and bug reports are welcome via [Issues](https://github.com/Frane12/AndroidGameTest/issues).
