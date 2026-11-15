#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "node and npm are required to build the web frontend." >&2
  exit 1
fi

if [ ! -f ../web/package-lock.json ]; then
  echo "../web/package-lock.json is missing. Run 'npm install' in ../web and commit the lockfile." >&2
  exit 1
fi

echo "Installing frontend dependencies..."
npm --prefix ../web ci --no-audit --no-fund

echo "Building frontend..."
npm --prefix ../web run build

if [ ! -f ../web/dist/index.html ]; then
  echo "Frontend build did not produce ../web/dist/index.html." >&2
  exit 1
fi

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
  echo "Installing build dependencies..."
  python3 -m pip install -r requirements-build.txt
fi

python3 packaging/make_icon.py packaging/OpportunityScout.icns

rm -rf build dist
python3 -m PyInstaller packaging/OpportunityScout.spec --noconfirm --clean

if ! find "dist/Opportunity Scout.app" -path "*/app/static/web/index.html" -print -quit | grep -q .; then
  echo "Packaged app is missing app/static/web/index.html." >&2
  exit 1
fi

hdiutil create \
  -volname "Opportunity Scout" \
  -srcfolder "dist/Opportunity Scout.app" \
  -ov -format UDZO \
  "dist/Opportunity Scout.dmg" >/dev/null

echo
echo "Built: $(pwd)/dist/Opportunity Scout.app"
echo "DMG:   $(pwd)/dist/Opportunity Scout.dmg"
echo "Open it from Finder, or run:"
echo "  open \"dist/Opportunity Scout.app\""
