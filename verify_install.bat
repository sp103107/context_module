@echo off
REM Verify Installation Script for Windows
REM Usage: verify_install.bat

echo ==========================================
echo AoS Context Module - Installation Verify
echo ==========================================
echo.

REM Clean up any existing test venv
if exist venv_test (
    echo Cleaning up existing test environment...
    rmdir /s /q venv_test
)

REM Create fresh virtual environment
echo Step 1: Creating fresh virtual environment...
python -m venv venv_test
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    exit /b 1
)

REM Activate virtual environment
echo Step 2: Activating virtual environment...
call venv_test\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    exit /b 1
)

REM Upgrade pip
echo Step 3: Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Install the package in editable mode
echo Step 4: Installing package (editable mode)...
pip install -e . --quiet
if errorlevel 1 (
    echo ERROR: Failed to install package
    call venv_test\Scripts\deactivate.bat
    exit /b 1
)

REM Run integration test
echo Step 5: Running integration test...
echo.
python tests\integration_test.py
if errorlevel 1 (
    echo ERROR: Integration test failed
    call venv_test\Scripts\deactivate.bat
    exit /b 1
)

REM Deactivate
echo.
echo Step 6: Deactivating virtual environment...
call venv_test\Scripts\deactivate.bat

REM Clean up
echo Step 7: Cleaning up test environment...
rmdir /s /q venv_test

echo.
echo ==========================================
echo Installation Verification Complete
echo ==========================================
pause

