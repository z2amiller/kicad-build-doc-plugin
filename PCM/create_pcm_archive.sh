#!/bin/sh
# Adapted from https://github.com/Bouni/kicad-jlcpcb-tools/blob/main/PCM/create_pcm_archive.sh
set -eu

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version>"
    echo "  version: e.g. 1.0.0 (without leading v)"
    exit 1
fi

VERSION=$1
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE_DIR="$REPO_ROOT/PCM/archive"
PLUGINS_DIR="$ARCHIVE_DIR/plugins"
RESOURCES_DIR="$ARCHIVE_DIR/resources"
ZIP_FILE="$REPO_ROOT/PCM/kicad-build-doc-plugin-v${VERSION}.zip"
METADATA_FILE="$ARCHIVE_DIR/metadata.json"

sed_inplace() {
    sed -i.bak "$1" "$2"
    rm -f "$2.bak"
}

echo "Clean up old files"
rm -f "$REPO_ROOT"/PCM/*.zip
rm -rf "$ARCHIVE_DIR"

echo "Create PCM folder structure"
mkdir -p "$PLUGINS_DIR" "$RESOURCES_DIR"

echo "Copy plugin source files"
for file in "$REPO_ROOT"/*.py "$REPO_ROOT"/*.txt \
            "$REPO_ROOT"/plugin.json \
            "$REPO_ROOT"/enclosure_presets.json \
            "$REPO_ROOT"/panel_config.json \
            "$REPO_ROOT"/LICENSE "$REPO_ROOT"/README.md; do
    [ -e "$file" ] || continue
    cp -f "$file" "$PLUGINS_DIR/"
done

echo "Copy icon to resources/ (PCM Plugin Manager) and plugins/ (IPC toolbar)"
cp -f "$REPO_ROOT/icon.png" "$RESOURCES_DIR/"
cp -f "$REPO_ROOT/icon.png" "$PLUGINS_DIR/"

echo "Write version to plugins/VERSION"
echo "$VERSION" > "$PLUGINS_DIR/VERSION"

echo "Generate metadata.json with placeholder values"
cp "$REPO_ROOT/PCM/metadata.template.json" "$METADATA_FILE"
sed_inplace "s/VERSION_HERE/$VERSION/g" "$METADATA_FILE"
sed_inplace "s/SHA256_HERE/PENDING_SHA256/g" "$METADATA_FILE"
sed_inplace "s|DOWNLOAD_URL_HERE|PENDING_URL|g" "$METADATA_FILE"
sed_inplace "s/DOWNLOAD_SIZE_HERE/0/g" "$METADATA_FILE"
sed_inplace "s/INSTALL_SIZE_HERE/0/g" "$METADATA_FILE"

echo "Build ZIP"
(cd "$ARCHIVE_DIR" && zip -r "$ZIP_FILE" .)

echo "Compute archive stats"
DOWNLOAD_SHA256=$(shasum --algorithm 256 "$ZIP_FILE" | awk '{print $1}')
DOWNLOAD_SIZE=$(wc -c < "$ZIP_FILE" | tr -d '[:space:]')
DOWNLOAD_URL="https://github.com/z2amiller/kicad-build-doc-plugin/releases/download/v${VERSION}/kicad-build-doc-plugin-v${VERSION}.zip"
INSTALL_SIZE=$(unzip -l "$ZIP_FILE" | awk 'END{print $1}')

echo "Patch metadata.json with real values"
sed_inplace "s/PENDING_SHA256/$DOWNLOAD_SHA256/g" "$METADATA_FILE"
sed_inplace "s|PENDING_URL|$DOWNLOAD_URL|g" "$METADATA_FILE"
sed_inplace "s/\"download_size\": 0/\"download_size\": $DOWNLOAD_SIZE/g" "$METADATA_FILE"
sed_inplace "s/\"install_size\": 0/\"install_size\": $INSTALL_SIZE/g" "$METADATA_FILE"

echo "Rebuild ZIP with final metadata"
(cd "$ARCHIVE_DIR" && zip -d "$ZIP_FILE" metadata.json && zip "$ZIP_FILE" metadata.json)

echo "Recompute final archive stats after metadata update"
DOWNLOAD_SHA256=$(shasum --algorithm 256 "$ZIP_FILE" | awk '{print $1}')
DOWNLOAD_SIZE=$(wc -c < "$ZIP_FILE" | tr -d '[:space:]')

if [ -n "${GITHUB_ENV:-}" ]; then
    echo "VERSION=$VERSION" >> "$GITHUB_ENV"
    echo "DOWNLOAD_SHA256=$DOWNLOAD_SHA256" >> "$GITHUB_ENV"
    echo "DOWNLOAD_SIZE=$DOWNLOAD_SIZE" >> "$GITHUB_ENV"
    echo "DOWNLOAD_URL=$DOWNLOAD_URL" >> "$GITHUB_ENV"
    echo "INSTALL_SIZE=$INSTALL_SIZE" >> "$GITHUB_ENV"
    echo "ZIP_FILE=$ZIP_FILE" >> "$GITHUB_ENV"
else
    echo ""
    echo "VERSION=$VERSION"
    echo "DOWNLOAD_SHA256=$DOWNLOAD_SHA256"
    echo "DOWNLOAD_SIZE=$DOWNLOAD_SIZE"
    echo "DOWNLOAD_URL=$DOWNLOAD_URL"
    echo "INSTALL_SIZE=$INSTALL_SIZE"
    echo "ZIP=$ZIP_FILE"
fi
