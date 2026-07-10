"""Comprehensive DSP edge-case tests."""
import sys
sys.path.insert(0, r'C:\Users\think\morse')

from dsp import encode_diff, decode_diff, DiffState
from core import roundtrip_check

assert roundtrip_check(), "core roundtrip must pass"

tests = 0
passed = 0

def check(label, got, expected):
    global tests, passed
    tests += 1
    ok = got == expected
    if ok:
        passed += 1
    else:
        print(f"FAIL [{label}]: got {got!r}, expected {expected!r}")

# --- encode_diff ---
check("empty->empty",   encode_diff(b'', b''),                                    '')
check("empty->1byte",   encode_diff(b'', b'\x41'),                                '0:.-.....-|')
check("no change",      encode_diff(b'\x41', b'\x41'),                            '')
check("single change",  encode_diff(b'\x00', b'\xFF'),                            '0:--------|')
check("grow",           encode_diff(b'\x41', b'\x41\x42'),                        '1:.-....-.|')
check("shrink",         encode_diff(b'\x41\x42\x43', b'\x41\x42'),                'T:2|')
check("shrink to 0",    encode_diff(b'\x41\x42', b''),                            'T:0|')
check("multi change",   encode_diff(b'\x00\x00\x00', b'\x41\x00\xFF'),            '0:.-.....-|2:--------|')
check("all change",     encode_diff(b'\x00\x00', b'\xFF\xFF'),                    '0:--------|1:--------|')
check("grow with gap",  encode_diff(b'\x41', b'\x41\x00\x00\x42'),                '1:........|2:........|3:.-....-.|')

# --- decode_diff ---
check("empty frame",         decode_diff(b'', ''),                                  b'')
check("apply to empty",      decode_diff(b'', '0:.-.....-|'),                       b'\x41')
check("single change",       decode_diff(b'\x00', '0:--------|'),                   b'\xFF')
check("multi change",        decode_diff(b'\x00\x00', '0:--------|1:--------|'),    b'\xFF\xFF')
check("truncate",            decode_diff(b'\x41\x42\x43', 'T:2|'),                  b'\x41\x42')
check("truncate to 0",       decode_diff(b'\x41\x42', 'T:0|'),                      b'')
check("grow on apply",       decode_diff(b'', '0:.-.....-|2:.-....--|'),             b'A\x00C')
check("override existing",   decode_diff(b'AAA', '1:.-....-.|'),                      b'ABA')

# --- roundtrip: encode_diff + decode_diff ---
for old_len in range(5):
    for new_len in range(5):
        old = bytes(range(0x41, 0x41 + old_len))
        new = bytes(range(0xC0, 0xC0 + new_len))
        frame = encode_diff(old, new)
        recovered = decode_diff(old, frame)
        check(f"roundtrip len={old_len}->{new_len}", recovered, new)

# --- DiffState ---
ds = DiffState()
check("ds init", ds.state, b'')

ds = DiffState()
f1 = ds.diff(b'\x41\x42')
check("ds diff1 frame", f1, '0:.-.....-|1:.-....-.|')
check("ds diff1 state", ds.state, b'\x41\x42')

f2 = ds.diff(b'\x41\xFF')
check("ds diff2 frame", f2, '1:--------|')
check("ds diff2 state", ds.state, b'\x41\xFF')

check("ds no-change", ds.diff(b'\x41\xFF'), '')
check("ds no-change state", ds.state, b'\x41\xFF')

f3 = ds.diff(b'\x41\xFF\x00')
check("ds grow", f3, '2:........|')
check("ds grow state", ds.state, b'\x41\xFF\x00')

f4 = ds.diff(b'\x41')
check("ds shrink", f4, 'T:1|')
check("ds shrink state", ds.state, b'\x41')

f5 = ds.sync(b'\xDE\xAD')
check("ds sync", f5, '0:--.----.|1:-.-.--.-|')
check("ds sync state", ds.state, b'\xDE\xAD')

# --- MAX_STATE_BYTES guard ---
try:
    decode_diff(b'', '99999:........|')
    check("MAX_STATE_BYTES guard", False, True)
except ValueError:
    check("MAX_STATE_BYTES guard", True, True)

# --- Truncation-first processing ---
# T:1 truncates to 1 byte, then index 2 write extends back to 3 bytes
result = decode_diff(b'\x00\x00\x00', '2:--------|T:1|')
check("truncation-first", result, b'\x00\x00\xff')

# --- Summary ---
print(f"Results: {passed}/{tests} passed")
sys.exit(0 if passed == tests else 1)
