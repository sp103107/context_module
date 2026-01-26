#!/bin/bash
# Verify Installation Script - Tests package installation in clean environment
# Usage: bash verify_install.sh

set -e  # Exit on error

echo "=========================================="
echo "AoS Context Module - Installation Verify"
echo "=========================================="
echo ""

# Clean up any existing test venv
if [ -d "venv_test" ]; then
    echo "Cleaning up existing test environment..."
    rm -rf venv_test
fi

# Create fresh virtual environment
echo "Step 1: Creating fresh virtual environment..."
python -m venv venv_test

# Activate virtual environment
echo "Step 2: Activating virtual environment..."
source venv_test/bin/activate

# Upgrade pip
echo "Step 3: Upgrading pip..."
pip install --upgrade pip --quiet

# Install the package in editable mode
echo "Step 4: Installing package (editable mode)..."
pip install -e . --quiet

# Run integration test
echo "Step 5: Running integration test..."
echo ""
python tests/integration_test.py

# Deactivate
echo ""
echo "Step 6: Deactivating virtual environment..."
deactivate

# Clean up
echo "Step 7: Cleaning up test environment..."
rm -rf venv_test

echo ""
echo "=========================================="
echo "✅ Installation Verification Complete"
echo "=========================================="

