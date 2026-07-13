@echo off
REM Pre-commit hook — validate skills before commit
REM Install: git config core.hooksPath .githooks

python self-harness\tools\validate_skills.py --json > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Skill Validator] Skills have issues. Run python self-harness\tools\validate_skills.py to see details.
    exit /b 1
)

echo [pre-commit] All good
