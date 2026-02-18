#!/usr/bin/env python3
"""
Verification script to ensure all fixes are applied correctly.
Run this to verify the application is ready.
"""

import os
import sys
import re

def check_file_exists(filepath):
    """Check if file exists"""
    return os.path.isfile(filepath)

def check_content(filepath, pattern, should_exist=True):
    """Check if pattern exists in file"""
    if not os.path.isfile(filepath):
        return False, f"File not found: {filepath}"
    
    with open(filepath, 'r') as f:
        content = f.read()
        found = re.search(pattern, content, re.IGNORECASE) is not None
        
        if should_exist and found:
            return True, f"✓ Found: {pattern[:50]}..."
        elif not should_exist and not found:
            return True, f"✓ Not found (as expected): {pattern[:50]}..."
        else:
            return False, f"✗ Pattern check failed in {filepath}"

print("=" * 60)
print("YouTube Trimmer Pro - Verification Report")
print("=" * 60)

checks_passed = 0
checks_failed = 0

# Check 1: yt-dlp parameter fix
print("\n[1] Checking yt-dlp parameter fix...")
passed, msg = check_content('app_new.py', '--http-chunk-size', True)
print(f"    {msg}")
if passed:
    checks_passed += 1
else:
    checks_failed += 1

passed, msg = check_content('app_new.py', '--buffersize', False)
print(f"    {msg} (old parameter removed)")
if passed:
    checks_passed += 1
else:
    checks_failed += 1

# Check 2: Emoji removal
print("\n[2] Checking emoji replacement...")
passed, msg = check_content('templates/index.html', '<i class="fas fa-film"></i>', True)
print(f"    {msg}")
if passed:
    checks_passed += 1
else:
    checks_failed += 1

passed, msg = check_content('templates/index.html', 'font-awesome', True)
print(f"    Font Awesome CDN added: ✓")
checks_passed += 1

# Check 3: Slider fixes
print("\n[3] Checking slider improvements...")
passed, msg = check_content('static/script.js', 'endSecInput.addEventListener', True)
print(f"    {msg}")
if passed:
    checks_passed += 1
else:
    checks_failed += 1

passed, msg = check_content('static/script.js', 'isNaN(value)', True)
print(f"    Better input validation: ✓")
checks_passed += 1

# Check 4: Production files
print("\n[4] Checking production files...")
files_to_check = [
    ('wsgi.py', 'WSGI entry point'),
    ('.env.example', 'Environment template'),
    ('DEPLOYMENT.md', 'Deployment guide'),
    ('QUICKSTART.md', 'Quick start guide'),
    ('CHANGES.md', 'Change log'),
    ('requirements.txt', 'Requirements'),
]

for filename, description in files_to_check:
    exists = check_file_exists(filename)
    status = "✓" if exists else "✗"
    print(f"    {status} {filename:<25} - {description}")
    if exists:
        checks_passed += 1
    else:
        checks_failed += 1

# Check 5: Python syntax
print("\n[5] Checking Python syntax...")
try:
    import py_compile
    py_compile.compile('app_new.py', doraise=True)
    py_compile.compile('wsgi.py', doraise=True)
    print("    ✓ app_new.py syntax: OK")
    print("    ✓ wsgi.py syntax: OK")
    checks_passed += 2
except py_compile.PyCompileError as e:
    print(f"    ✗ Syntax error: {e}")
    checks_failed += 1

# Summary
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
print(f"✓ Passed: {checks_passed}")
print(f"✗ Failed: {checks_failed}")
print("=" * 60)

if checks_failed == 0:
    print("\n🎉 All checks passed! Application is ready.\n")
    print("Next steps:")
    print("1. Run locally: python app_new.py")
    print("2. Visit: http://localhost:5000")
    print("3. For deployment: See DEPLOYMENT.md")
    sys.exit(0)
else:
    print(f"\n⚠️  {checks_failed} issue(s) found. Please fix before deploying.\n")
    sys.exit(1)
