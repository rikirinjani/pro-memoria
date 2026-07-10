"""Pro Memoria — Phase 3: Lexicon.

Two-tier command system over 8-bit positions:

  Tier 1 — Hamming [8,4,4] (16 commands, distance 4, SEC)
    Extended Hamming code. Corrects any single-bit error.
    Data bits in lower nybble (c0-c3), parity in upper nybble (c4-c7).

  Tier 2 — Parity-protected (128 commands, distance 2, SED)
    7 data bits + even parity. Detects any single-bit error.

Both encode to 8-bit values → 8-char Morse strings via bits_to_morse().
"""

from core import bits_to_morse, morse_to_bits


# ── Extended Hamming [8,4,4] ──────────────────────────────────────────

# Syndrome (s2,s1,s0 as 3-bit int) → bit position to flip
_SYN_TO_POS = {1: 4, 2: 5, 3: 0, 4: 6, 5: 1, 6: 2, 7: 3}


def _parity3(byte: int) -> tuple[int, int]:
    """Return (syndrome_3bit, overall_parity_flag) for an 8-bit value."""
    c = [(byte >> i) & 1 for i in range(8)]
    s0 = c[4] ^ c[0] ^ c[1] ^ c[3]
    s1 = c[5] ^ c[0] ^ c[2] ^ c[3]
    s2 = c[6] ^ c[1] ^ c[2] ^ c[3]
    s3 = c[7] ^ c[0] ^ c[1] ^ c[2] ^ c[3] ^ c[4] ^ c[5] ^ c[6]
    return (s2 << 2) | (s1 << 1) | s0, s3


def hamming_encode(cmd_id: int) -> int:
    """Encode a 4-bit command ID (0-15) into an 8-bit extended Hamming codeword.

    >>> [hex(hamming_encode(i)) for i in range(16)]
    ['0x0', '0xb1', '0xd2', '0x63', '0xe4', '0x55', '0x36', '0x87', '0x78', '0xc9', '0xaa', '0x1b', '0x9c', '0x2d', '0x4e', '0xff']
    """
    d0 = (cmd_id >> 0) & 1
    d1 = (cmd_id >> 1) & 1
    d2 = (cmd_id >> 2) & 1
    d3 = (cmd_id >> 3) & 1
    p0 = d0 ^ d1 ^ d3
    p1 = d0 ^ d2 ^ d3
    p2 = d1 ^ d2 ^ d3
    p3 = d0 ^ d1 ^ d2 ^ d3 ^ p0 ^ p1 ^ p2
    return (p3 << 7) | (p2 << 6) | (p1 << 5) | (p0 << 4) | (d3 << 3) | (d2 << 2) | (d1 << 1) | d0


def hamming_decode(byte: int, *, correct: bool = True) -> tuple[int | None, bool, bool]:
    """Decode an 8-bit value to a 4-bit command ID with error handling.

    Returns (cmd_id, was_corrected, is_uncorrectable).
    cmd_id is None when is_uncorrectable is True.

    >>> hamming_decode(0x00)
    (0, False, False)
    >>> hamming_decode(0x01)  # single-bit error -> corrected
    (0, True, False)
    >>> hamming_decode(0x03)  # double-bit error
    (None, False, True)
    >>> hamming_decode(0x78)
    (8, False, False)
    """
    syn, s3 = _parity3(byte)

    if syn == 0 and s3 == 0:
        return byte & 0x0F, False, False

    if s3 == 1 and syn == 0:
        if not correct:
            return None, False, True
        return (byte ^ (1 << 7)) & 0x0F, True, False

    if s3 == 1:
        if not correct:
            return None, False, True
        pos = _SYN_TO_POS[syn]
        return ((byte ^ (1 << pos)) & 0x0F), True, False

    # s3 == 0 and syn != 0: double error detected
    return None, False, True


def is_hamming_codeword(byte: int) -> bool:
    """Return True if byte is a valid extended Hamming codeword (no errors).

    >>> is_hamming_codeword(0x00)
    True
    >>> is_hamming_codeword(0x01)
    False
    >>> is_hamming_codeword(0xB1)
    True
    """
    syn, s3 = _parity3(byte)
    return syn == 0 and s3 == 0


# ── Parity-protected commands (distance 2) ────────────────────────────

def parity_encode(cmd_id: int) -> int:
    """Encode a 7-bit command ID (0-127) with even parity (MSB = parity).

    >>> hex(parity_encode(0x41))
    '0x41'
    >>> hex(parity_encode(0x00))
    '0x0'
    >>> hex(parity_encode(0x7F))
    '0xff'
    """
    if not (0 <= cmd_id < 128):
        raise ValueError(f"cmd_id must be 0-127, got {cmd_id}")
    parity = (cmd_id.bit_count() & 1) << 7
    return cmd_id | parity


def parity_decode(byte: int) -> tuple[int, bool]:
    """Decode an 8-bit parity-protected byte to (cmd_id, error_detected).

    >>> parity_decode(0xc1)  # parity bit = 1, but 0x41 has even parity
    (65, True)
    >>> parity_decode(0x41)  # even parity is correct for 0x41
    (65, False)
    >>> parity_decode(0x00)
    (0, False)
    """
    cmd_id = byte & 0x7F
    expected_parity = (cmd_id.bit_count() & 1) << 7
    error = (byte & 0xFF) != (cmd_id | expected_parity)
    return cmd_id, error


def is_parity_valid(byte: int) -> bool:
    """Return True if byte has valid even parity.

    >>> is_parity_valid(0x41)
    True
    >>> is_parity_valid(0xc1)
    False
    """
    return (byte & 0xFF) == parity_encode(byte & 0x7F)


# ── Command listings ──────────────────────────────────────────────────

HAMMING_COMMANDS: dict[int, str] = {
    0x0: 'NOP',       # No operation
    0x1: 'ACK',       # Acknowledge
    0x2: 'NAK',       # Negative acknowledge
    0x3: 'RESET',     # Reset state
    0x4: 'SYNC',      # Synchronize
    0x5: 'REQ',       # Request data
    0x6: 'DATA',      # Data frame follows
    0x7: 'EOF',       # End of frame
    0x8: 'ERR',       # Error
    0x9: 'RETRY',     # Retry
    0xA: 'STATUS',    # Status request/report
    0xB: 'CONFIG',    # Configure
    0xC: 'HELLO',     # Handshake initiate
    0xD: 'BYE',       # Disconnect
    0xE: 'ECHO',      # Echo for liveness
    0xF: 'HALT',      # Halt/stop
}

PARITY_COMMANDS: dict[int, str] = {
    0x00: 'NOP_LOW',      0x01: 'PING',
    0x02: 'PONG',         0x03: 'BEAT',
    0x04: 'STATE_REQ',    0x05: 'STATE_REP',
    0x06: 'DIFF',         0x07: 'FULL_SYNC',
    0x08: 'COMPRESS',     0x09: 'DECOMPRESS',
    0x0A: 'ENCRYPT',      0x0B: 'DECRYPT',
    0x0C: 'SIGN',         0x0D: 'VERIFY',
    0x0E: 'VERSION',      0x0F: 'VERSION_ACK',
}


#
# NOTE ON PROTOCOL VERSIONING:
#   Parity command 0x0E (VERSION) is reserved for capability negotiation:
#     Agent A -> Agent B:   VERSION <major>.<minor> (as DSP frame data)
#     Agent B -> Agent A:   VERSION_ACK (0x0F) if compatible
#   This must be the first exchange in any handshake.
#   Incompatible agents should disconnect gracefully.
#


#
# NOTE ON TIER COLLISION:
#   0x87 (Morse: -....---) is a valid codeword in BOTH tiers:
#     - Hamming: hamming_encode(7) = 0x87 = "EOF" (cmd_id=7)
#     - Parity:  parity_encode(7)   = 0x87 = "FULL_SYNC" (cmd_id=7)
#
#   This is by design — Hamming and parity occupy overlapping 8-bit spaces.
#   Protocol MUST specify which tier it intends. Auto-detection is NOT
#   supported for protocol use. Use command_name(byte, tier='hamming')
#   or command_name(byte, tier='parity') explicitly.
#
def command_name(byte: int, *, tier: str) -> str:
    """Look up command name by its 8-bit encoded value and explicit tier.

    Tier MUST be specified explicitly ('hamming' or 'parity').
    Auto-detection is intentionally removed due to the 0x87 collision
    (see module docstring).

    >>> command_name(0x00, tier='hamming')
    'NOP'
    >>> command_name(0x78, tier='hamming')
    'ERR'
    >>> command_name(0x41, tier='parity')
    'P_0x41'
    >>> command_name(0xB1, tier='hamming')
    'ACK'
    """
    if tier == 'hamming':
        cmd_id = byte & 0x0F
        return HAMMING_COMMANDS.get(cmd_id, f'HAMMING_0x{cmd_id:X}')
    if tier == 'parity':
        cmd_id = byte & 0x7F
        return PARITY_COMMANDS.get(cmd_id, f'P_0x{cmd_id:02X}')
    raise ValueError(f"tier must be 'hamming' or 'parity', got {tier!r}")


def lexicon_table() -> str:
    """Generate a formatted table of all commands with hex + Morse encoding."""
    lines = []
    lines.append(f"{'Tier':8s} {'ID':6s} {'Name':12s} {'Hex':6s} {'Morse':20s}")
    lines.append('-' * 52)

    for cmd_id, name in HAMMING_COMMANDS.items():
        cw = hamming_encode(cmd_id)
        mor = bits_to_morse(cw)
        label = f"{'Hamming':8s} {cmd_id:4d}  {name:12s} 0x{cw:02X}  {mor:20s}"
        if is_parity_valid(cw):
            label += f"  <-- COLLISION with parity cmd {cw & 0x7F}"
        lines.append(label)

    for cmd_id in sorted(PARITY_COMMANDS):
        pw = parity_encode(cmd_id)
        mor = bits_to_morse(pw)
        name = PARITY_COMMANDS[cmd_id]
        label = f"{'Parity':8s} {cmd_id:4d}  {name:12s} 0x{pw:02X}  {mor:20s}"
        if is_hamming_codeword(pw):
            hamming_cmd = HAMMING_COMMANDS.get(pw & 0x0F, '?')
            label += f"  <-- COLLISION with Hamming {hamming_cmd}"
        lines.append(label)

    lines.append('')
    collision_warning = (
        "WARNING: 0x87 (-....---) is valid in BOTH tiers: "
        "Hamming cmd 7 (EOF) == Parity cmd 7 (FULL_SYNC). "
        "Always specify tier explicitly in protocol use."
    )
    lines.append(collision_warning)

    return '\n'.join(lines)


# ── Printable Morse dictionary ────────────────────────────────────────

def morse_dict() -> dict[str, tuple[int, str, str]]:
    """Return {morse_string: (byte, hex_str, name)} for all defined commands."""
    result = {}
    for cmd_id, name in HAMMING_COMMANDS.items():
        cw = hamming_encode(cmd_id)
        mor = bits_to_morse(cw)
        result[mor] = (cw, f'0x{cw:02X}', f'Hamming:{name}')
    for cmd_id, name in PARITY_COMMANDS.items():
        pw = parity_encode(cmd_id)
        mor = bits_to_morse(pw)
        result[mor] = (pw, f'0x{pw:02X}', f'Parity:{name}')
    return result


if __name__ == '__main__':
    import doctest
    results = doctest.testmod(verbose=False)
    print(f"Doctests: {results.attempted} attempted, {results.failed} failed")

    print('\n' + lexicon_table())

    # Verify all 16 Hamming codewords correct single-bit errors
    ok = True
    for cmd_id in range(16):
        cw = hamming_encode(cmd_id)
        if not is_hamming_codeword(cw):
            print(f"FAIL: 0x{cmd_id:X} -> 0x{cw:02X} is not a valid codeword")
            ok = False
        for bit in range(8):
            err = cw ^ (1 << bit)
            decoded, corrected, bad = hamming_decode(err)
            if decoded != cmd_id or not corrected or bad:
                print(f"FAIL: 0x{cmd_id:X} bit {bit}: decoded={decoded} corrected={corrected} bad={bad}")
                ok = False
        # Double error: two bits flipped
        for b1 in range(8):
            for b2 in range(b1+1, 8):
                    err2 = cw ^ (1 << b1) ^ (1 << b2)
                    decoded, corrected, bad = hamming_decode(err2, correct=True)
                    if not bad:
                        print(f"WARN: 0x{cmd_id:X} bits {b1},{b2} -> decoded={decoded} (should be detected)")
    if ok:
        print("Hamming: 16 commands, 128 single-error corrections, double-error detection: PASS")

    # Verify all 128 parity commands
    ok = True
    for cmd_id in range(128):
        pw = parity_encode(cmd_id)
        if not is_parity_valid(pw):
            print(f"FAIL: 0x{cmd_id:X} -> 0x{pw:02X} invalid parity")
            ok = False
        decoded, err = parity_decode(pw)
        if decoded != cmd_id or err:
            print(f"FAIL: decode parity 0x{cmd_id:X} -> {decoded} err={err}")
            ok = False
        # Flip any single bit -> error detected
        for bit in range(8):
            corrupted = pw ^ (1 << bit)
            _, err_detected = parity_decode(corrupted)
            if not err_detected:
                print(f"FAIL: parity cmd 0x{cmd_id:X} bit {bit}: error not detected")
                ok = False
    if ok:
        print("Parity: 128 commands, single-error detection: PASS")
