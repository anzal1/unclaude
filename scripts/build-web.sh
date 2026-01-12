#!/bin/bash
# Build web UI for distribution
# This script builds the Next.js frontend and copies it to the Python package

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WEB_UI_DIR="$PROJECT_DIR/web-ui"
STATIC_DIR="$PROJECT_DIR/src/unclaude/web/static"

echo "🔨 Building UnClaude Web UI..."

# Check if web-ui directory exists
if [ ! -d "$WEB_UI_DIR" ]; then
    echo "❌ Error: web-ui directory not found at $WEB_UI_DIR"
    exit 1
fi

# Navigate to web-ui directory
cd "$WEB_UI_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Build the static export
echo "🏗️  Building Next.js static export..."
npm run build

# Check if output directory exists
if [ ! -d "out" ]; then
    echo "❌ Error: Build failed - 'out' directory not found"
    exit 1
fi

# Remove old static files
if [ -d "$STATIC_DIR" ]; then
    echo "🧹 Removing old static files..."
    rm -rf "$STATIC_DIR"
fi

# Copy new static files
echo "📁 Copying static files to package..."
cp -r out "$STATIC_DIR"

echo "✅ Web UI built successfully!"
echo "   Static files: $STATIC_DIR"
echo ""
echo "You can now build and publish the package:"
echo "   python -m build"
echo "   twine upload dist/*"
