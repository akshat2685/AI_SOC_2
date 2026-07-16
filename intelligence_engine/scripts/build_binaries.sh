#!/bin/bash
# build_binaries.sh
set -e

echo "Building binaries and packages for AI SOC Intelligence Engine..."

# Ensure we are in the intelligence_engine directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/.."

echo "Setting up virtual environment for building..."
python3 -m venv build_venv
source build_venv/bin/activate

echo "Installing packaging dependencies..."
pip install pyinstaller

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

echo "Running PyInstaller..."
# We assume main.py is the entry point
if [ ! -f "main.py" ]; then
    echo "Error: main.py not found. Cannot build executable."
    exit 1
fi

pyinstaller --name intelligence_engine --onefile main.py

echo "Creating .deb package structure..."
DEB_DIR="dist/deb_build/intelligence_engine_1.0.0_amd64"
mkdir -p "$DEB_DIR/usr/bin"
mkdir -p "$DEB_DIR/DEBIAN"

cp dist/intelligence_engine "$DEB_DIR/usr/bin/"

cat << 'EOF' > "$DEB_DIR/DEBIAN/control"
Package: intelligence-engine
Version: 1.0.0
Section: base
Priority: optional
Architecture: amd64
Maintainer: AI SOC Team
Description: AI SOC Intelligence Engine
EOF

if [ -x "$(command -v dpkg-deb)" ]; then
    dpkg-deb --build "$DEB_DIR" dist/intelligence_engine_1.0.0_amd64.deb
else
    echo "Warning: dpkg-deb not found, skipping .deb build."
fi

echo "Creating .rpm package (requires alien)..."
if [ -x "$(command -v alien)" ]; then
    alien -r dist/intelligence_engine_1.0.0_amd64.deb --generated --to-rpm
    mv *.rpm dist/
else
    echo "Warning: alien not found, skipping .rpm build."
fi

echo "Build complete. Artifacts are in the dist/ directory."
