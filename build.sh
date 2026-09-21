#!/usr/bin/env bash
set -euo pipefail
# Set ANDROID_SDK_ROOT; ECJ_JAR is optional (javac is the fallback).
: "${ANDROID_SDK_ROOT:?Set Android SDK path}"

cd "$(dirname "$0")"
BT="$ANDROID_SDK_ROOT/build-tools/35.0.0"
API="$ANDROID_SDK_ROOT/platforms/android-35/android.jar"
mkdir -p build/classes
if [[ -n "${ECJ_JAR:-}" && -f "$ECJ_JAR" ]]; then
    java -jar "$ECJ_JAR" -1.8 -proc:none -bootclasspath "$API" -d build/classes src/hr/frane/zvjezdana/*.java
else
    javac -source 8 -target 8 -cp "$API" -d build/classes src/hr/frane/zvjezdana/*.java
fi
"$BT/aapt2" compile --dir res -o build/res.zip
"$BT/aapt2" link -o build/base.apk --manifest AndroidManifest.xml -I "$API" build/res.zip
"$BT/d8" --lib "$API" --min-api 23 --output build build/classes/hr/frane/zvjezdana/*.class
python3 - <<'PY'
import zipfile
with zipfile.ZipFile('build/base.apk','a',zipfile.ZIP_DEFLATED) as z:
    z.write('build/classes.dex','classes.dex')
PY
"$BT/zipalign" -f -p 4 build/base.apk build/aligned.apk
"$BT/apksigner" sign --ks test-signing.p12 --ks-key-alias test --ks-pass pass:android --key-pass pass:android --out build/Zvjezdana-Macka-0.5.apk build/aligned.apk
"$BT/apksigner" verify --verbose build/Zvjezdana-Macka-0.5.apk
