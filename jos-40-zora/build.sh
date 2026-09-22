#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
BT="$SDK/build-tools/35.0.0"
API="$SDK/platforms/android-35/android.jar"
mkdir -p build/classes
javac -encoding UTF-8 -source 8 -target 8 -cp "$API" -d build/classes src/hr/frane/zora/MainActivity.java
"$BT/aapt2" link -o build/base.apk --manifest AndroidManifest.xml -I "$API"
mapfile -t classes < <(find build/classes -name '*.class')
"$BT/d8" --min-api 23 --lib "$API" --output build "${classes[@]}"
python3 - <<'PY'
import zipfile
with zipfile.ZipFile('build/base.apk','a',zipfile.ZIP_DEFLATED) as z:
    z.write('build/classes.dex','classes.dex')
PY
"$BT/zipalign" -f -p 4 build/base.apk build/aligned.apk
keytool -genkeypair -noprompt -keystore build/prototype-signing.p12 -storetype PKCS12 \
  -storepass android -keypass android -alias prototype -keyalg RSA -keysize 2048 \
  -validity 3650 -dname 'CN=Jos 40 zora, OU=Prototype, O=Independent Game'
"$BT/apksigner" sign --ks build/prototype-signing.p12 --ks-key-alias prototype \
   --ks-pass pass:android --key-pass pass:android \
   --out build/Jos-40-zora-prototip.apk build/aligned.apk
"$BT/apksigner" verify --verbose build/Jos-40-zora-prototip.apk
unzip -t build/Jos-40-zora-prototip.apk
