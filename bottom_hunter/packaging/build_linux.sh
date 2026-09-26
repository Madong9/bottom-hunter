#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPOSITORY_DIR="$(cd -- "$PACKAGE_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPOSITORY_DIR/.venv/bin/python}"
BUILD_ROOT="$REPOSITORY_DIR/.packaging-build"
PYINSTALLER_DIST="$BUILD_ROOT/pyinstaller-dist"
APP_DIR="$BUILD_ROOT/BottomHunter.AppDir"
DEB_ROOT="$BUILD_ROOT/deb-root"
OUTPUT_DIR="$REPOSITORY_DIR/dist"
APPIMAGE_TOOL="$BUILD_ROOT/tools/appimagetool-x86_64.AppImage"
TARGET="${1:---all}"

case "$TARGET" in
    --all|--appimage|--deb) ;;
    *) echo "用法: $0 [--all|--appimage|--deb]" >&2; exit 2 ;;
esac

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "未找到构建 Python: $PYTHON_BIN" >&2
    exit 2
fi
if ! "$PYTHON_BIN" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "缺少 PyInstaller，请运行: $PYTHON_BIN -m pip install -e '$PACKAGE_DIR[package]'" >&2
    exit 2
fi

VERSION="$($PYTHON_BIN -c 'import tomllib, pathlib; print(tomllib.loads(pathlib.Path("'"$PACKAGE_DIR"'/pyproject.toml").read_text())["project"]["version"])')"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
APPIMAGE_ARCH="x86_64"
if [[ "$ARCH" == "arm64" ]]; then APPIMAGE_ARCH="aarch64"; fi

mkdir -p "$BUILD_ROOT" "$OUTPUT_DIR"
rm -rf "$PYINSTALLER_DIST" "$BUILD_ROOT/pyinstaller-work" "$APP_DIR" "$DEB_ROOT"

"$PYTHON_BIN" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "$PYINSTALLER_DIST" \
    --workpath "$BUILD_ROOT/pyinstaller-work" \
    "$SCRIPT_DIR/bottom-hunter.spec"

build_appimage() {
    install -d "$APP_DIR/usr/lib/bottom-hunter" "$APP_DIR/usr/share/applications" "$APP_DIR/usr/share/icons/hicolor/scalable/apps"
    cp -a "$PYINSTALLER_DIST/BottomHunter/." "$APP_DIR/usr/lib/bottom-hunter/"
    install -m 0755 "$SCRIPT_DIR/AppRun" "$APP_DIR/AppRun"
    install -m 0644 "$SCRIPT_DIR/bottom-hunter.desktop" "$APP_DIR/bottom-hunter.desktop"
    install -m 0644 "$SCRIPT_DIR/bottom-hunter.desktop" "$APP_DIR/usr/share/applications/bottom-hunter.desktop"
    install -m 0644 "$SCRIPT_DIR/bottom-hunter.svg" "$APP_DIR/bottom-hunter.svg"
    install -m 0644 "$SCRIPT_DIR/bottom-hunter.svg" "$APP_DIR/usr/share/icons/hicolor/scalable/apps/bottom-hunter.svg"
    ln -sfn bottom-hunter.svg "$APP_DIR/.DirIcon"

    if [[ ! -x "$APPIMAGE_TOOL" ]]; then
        mkdir -p "$(dirname -- "$APPIMAGE_TOOL")"
        curl --fail --location --retry 3 \
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-$APPIMAGE_ARCH.AppImage" \
            --output "$APPIMAGE_TOOL"
        chmod 0755 "$APPIMAGE_TOOL"
    fi
    local output="$OUTPUT_DIR/BottomHunter-$VERSION-$APPIMAGE_ARCH.AppImage"
    rm -f "$output"
    ARCH="$APPIMAGE_ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE_TOOL" "$APP_DIR" "$output"
    chmod 0755 "$output"
}

build_deb() {
    install -d "$DEB_ROOT/DEBIAN" "$DEB_ROOT/opt/bottom-hunter" "$DEB_ROOT/usr/bin" \
        "$DEB_ROOT/usr/share/applications" "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps"
    cp -a "$PYINSTALLER_DIST/BottomHunter/." "$DEB_ROOT/opt/bottom-hunter/"
    install -m 0644 "$SCRIPT_DIR/bottom-hunter.desktop" "$DEB_ROOT/usr/share/applications/bottom-hunter.desktop"
    install -m 0644 "$SCRIPT_DIR/bottom-hunter.svg" "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps/bottom-hunter.svg"
    cat >"$DEB_ROOT/usr/bin/bottom-hunter" <<'EOF'
#!/bin/sh
export PYTHONNOUSERSITE=1
unset PYTHONPATH
exec /opt/bottom-hunter/BottomHunter "$@"
EOF
    chmod 0755 "$DEB_ROOT/usr/bin/bottom-hunter"
    local installed_size
    installed_size="$(du -sk "$DEB_ROOT/opt/bottom-hunter" | cut -f1)"
    cat >"$DEB_ROOT/DEBIAN/control" <<EOF
Package: bottom-hunter
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $installed_size
Maintainer: Bottom Hunter Project
Depends: libxcb-cursor0, libgl1, libfontconfig1, libxkbcommon-x11-0
Description: Cross-market oversold rebound research desktop
 Qt Quick desktop application for watchlist import, scanning, research,
 reports, health status and interactive K-line analysis.
EOF
    local output="$OUTPUT_DIR/bottom-hunter_${VERSION}_${ARCH}.deb"
    rm -f "$output"
    dpkg-deb --build --root-owner-group "$DEB_ROOT" "$output"
}

if [[ "$TARGET" == "--all" || "$TARGET" == "--appimage" ]]; then build_appimage; fi
if [[ "$TARGET" == "--all" || "$TARGET" == "--deb" ]]; then build_deb; fi

(cd "$OUTPUT_DIR" && sha256sum BottomHunter-*.AppImage bottom-hunter_*.deb 2>/dev/null > SHA256SUMS || true)
echo "构建完成: $OUTPUT_DIR"
