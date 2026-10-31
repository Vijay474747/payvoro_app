#!/usr/bin/env bash
# Creates YOUR Payvoro signing key (one time only) and keystore.properties.
# Run from the payvoro folder:   bash make-keystore.sh
#
# ⚠️ Keep payvoro-release.jks and the password safe FOREVER (copy to Google Drive / pen drive).
#    Every future update must be signed with the same key, or merchants must uninstall and reinstall.
set -e
cd "$(dirname "$0")"

if [ -f payvoro-release.jks ]; then
  echo "payvoro-release.jks already exists – not overwriting it."
  exit 1
fi

# Find keytool: Android Studio's embedded JDK first, then the system one
KEYTOOL=""
for k in /snap/android-studio/current/jbr/bin/keytool /opt/android-studio/jbr/bin/keytool \
         "$HOME/android-studio/jbr/bin/keytool" "$(command -v keytool || true)"; do
  if [ -n "$k" ] && [ -x "$k" ]; then KEYTOOL="$k"; break; fi
done
if [ -z "$KEYTOOL" ]; then
  echo "keytool not found. Use Android Studio: Build → Generate Signed App Bundle / APK → Create new."
  exit 1
fi

read -r -s -p "Choose a password (min 6 characters): " PASS; echo
read -r -s -p "Type it again: " PASS2; echo
[ "$PASS" = "$PASS2" ] || { echo "Passwords do not match"; exit 1; }
[ ${#PASS} -ge 6 ] || { echo "Password too short"; exit 1; }
read -r -p "Your name or company (e.g. Payvoro): " NAME

"$KEYTOOL" -genkeypair -v -keystore payvoro-release.jks -alias payvoro \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass "$PASS" -keypass "$PASS" \
  -dname "CN=${NAME:-Payvoro}, O=${NAME:-Payvoro}, C=IN"

cat > keystore.properties <<EOF
storeFile=payvoro-release.jks
storePassword=$PASS
keyAlias=payvoro
keyPassword=$PASS
EOF
chmod 600 keystore.properties payvoro-release.jks

echo
echo "✅ Key created: payvoro-release.jks + keystore.properties"
echo "   Back them up now. Never share them or upload them to GitHub."
echo "   Next: in Android Studio → Build → Build App Bundle(s) / APK(s) → Build APK(s)"
echo "   (choose the 'release' build variant first: Build → Select Build Variant)"
