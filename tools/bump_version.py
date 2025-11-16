#!/usr/bin/env python3
import re
import sys
from pathlib import Path
import argparse

p = Path('gimp-ai-plugin.py')
if not p.exists():
    print("ERROR: gimp-ai-plugin.py not found", file=sys.stderr)
    sys.exit(1)

text = p.read_text(encoding='utf-8')

m = re.search(r"(VERSION\s*=\s*['\"])([^'\"]+)(['\"])", text)
if not m:
    print("ERROR: VERSION not found in gimp-ai-plugin.py", file=sys.stderr)
    sys.exit(1)

prefix, ver, suffix = m.group(1), m.group(2), m.group(3)

parser = argparse.ArgumentParser()
parser.add_argument('--type', choices=['patch','minor','major'], default='minor')
args = parser.parse_args()

# Separate pre-release suffix if present (e.g., 0.8.0-beta)
core = ver
prerelease = ''
if '-' in ver:
    core, prerelease = ver.split('-', 1)

parts = core.split('.')
while len(parts) < 3:
    parts.append('0')

try:
    major, minor, patch = map(int, parts[:3])
except ValueError:
    print("ERROR: Version core is not numeric major.minor.patch", file=sys.stderr)
    sys.exit(1)

if args.type == 'patch':
    patch += 1
elif args.type == 'minor':
    minor += 1
    patch = 0
elif args.type == 'major':
    major += 1
    minor = 0
    patch = 0

new_core = f"{major}.{minor}.{patch}"
# Decide whether to preserve prerelease: we drop prerelease by default for a bump
new_ver = new_core

new_text = re.sub(r"(VERSION\s*=\s*['\"])([^'\"]+)(['\"])", lambda m: m.group(1) + new_ver + m.group(3), text)
p.write_text(new_text, encoding='utf-8')

print(new_ver)
