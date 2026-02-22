#!/usr/bin/env python3
"""
Test script to verify genre extraction regex patterns
"""

import re

# Test URLs from the actual website
test_urls = [
    "/genre/7-rock/",
    "/genre/27-punk-rock/",
    "/genre/15-hip-hop/",
    "/genre/3-pop/",
    "/genre/12-indie-rock/",
]

# Current regex pattern (with double backslash - BROKEN)
broken_pattern = r'/genre/\\d+-(.+)/'

# Fixed regex pattern (with single backslash - WORKING)
fixed_pattern = r'/genre/\d+-(.+)/'

print("Testing regex patterns:")
print("=" * 60)

print("\nBROKEN PATTERN (double backslash):")
print(f"Pattern: {broken_pattern}")
for url in test_urls:
    match = re.search(broken_pattern, url)
    if match:
        print(f"  ✓ {url} -> {match.group(1)}")
    else:
        print(f"  ✗ {url} -> NO MATCH")

print("\nFIXED PATTERN (single backslash):")
print(f"Pattern: {fixed_pattern}")
for url in test_urls:
    match = re.search(fixed_pattern, url)
    if match:
        print(f"  ✓ {url} -> {match.group(1)}")
    else:
        print(f"  ✗ {url} -> NO MATCH")
