"""Pro Memoria — Phase 2: Differential State Protocol (DSP).

Emits only changed bytes. Frame-based diff format with grow/shrink support.

Frame format:
    <index>:<8-morse-chars>|<index>:<8-morse-chars>|...

Control commands (embedded in frame):
    T:<new_length>|  — truncate state to new_length bytes

Examples:
    "12:.-.....-|44:--......|"  → byte 12 = 0x41, byte 44 = 0xC0
    "T:2|"                       → truncate to 2 bytes

Security: MAX_STATE_BYTES (64 KB) bounds decoder allocations.
"""

from core import bits_to_morse, morse_to_bits

MAX_STATE_BYTES = 65536  # maximum allowed state size (DoS guard)


def encode_diff(old: bytes, new: bytes) -> str:
    """Compute a diff frame from old state to new state.

    Only bytes that changed are emitted. Handles grow/shrink.

    >>> encode_diff(b'', b'')
    ''
    >>> encode_diff(b'', b'A')
    '0:.-.....-|'
    >>> encode_diff(b'AB', b'A\\xff')
    '1:--------|'
    >>> encode_diff(b'ABC', b'AB')
    'T:2|'
    >>> encode_diff(b'\\x00\\x00\\x00', b'A\\x00\\xff')
    '0:.-.....-|2:--------|'
    """
    parts = []

    # Changed bytes within overlapping region
    for i in range(min(len(old), len(new))):
        if old[i] != new[i]:
            parts.append(f"{i}:{bits_to_morse(new[i])}")

    # New bytes (state grew)
    for i in range(len(old), len(new)):
        parts.append(f"{i}:{bits_to_morse(new[i])}")

    # Truncation (state shrank)
    if len(new) < len(old):
        parts.append(f"T:{len(new)}")

    return '|'.join(parts) + ('|' if parts else '')


def decode_diff(state: bytes, frame: str) -> bytes:
    """Apply a diff frame to an existing state and return new state.

    >>> decode_diff(b'', '')
    b''
    >>> decode_diff(b'', '0:.-.....-|')
    b'A'
    >>> decode_diff(b'AB', '1:--------|')
    b'A\\xff'
    >>> decode_diff(b'ABC', 'T:2|')
    b'AB'
    >>> decode_diff(b'', '0:.-.....-|2:--------|')
    b'A\\x00\\xff'
    """
    if not frame:
        return state

    buf = bytearray(state)

    entries = [e for e in frame.rstrip('|').split('|') if e]
    truncations = [e for e in entries if e.startswith('T:')]
    updates = [e for e in entries if not e.startswith('T:')]

    # Pass 1: process truncations first (avoids expand-then-truncate waste)
    for entry in truncations:
        length = int(entry[2:])
        if length > MAX_STATE_BYTES:
            raise ValueError(f"truncation length {length} exceeds max {MAX_STATE_BYTES}")
        if length < len(buf):
            buf = buf[:length]

    # Pass 2: process byte updates
    for entry in updates:
        colon = entry.find(':')
        if colon == -1:
            raise ValueError(f"invalid diff entry: {entry!r}")

        index = int(entry[:colon])
        morse = entry[colon + 1:]

        if len(morse) != 8:
            raise ValueError(f"invalid morse in diff entry: {entry!r}")

        if index >= MAX_STATE_BYTES:
            raise ValueError(f"byte index {index} exceeds max state size {MAX_STATE_BYTES}")

        value = morse_to_bits(morse)

        if index >= len(buf):
            buf.extend(b'\x00' * (index - len(buf) + 1))
        buf[index] = value

    return bytes(buf)


class DiffState:
    """Maintains state and supports emit-on-change protocol.

    >>> ds = DiffState()
    >>> ds.diff(b'AB')
    '0:.-.....-|1:.-....-.|'
    >>> ds.state
    b'AB'
    >>> ds.diff(b'A\\xff')
    '1:--------|'
    >>> ds.state
    b'A\\xff'
    >>> ds.diff(b'A\\xff')  # no change
    ''
    """

    def __init__(self, initial: bytes = b''):
        self._state = bytearray(initial)

    @property
    def state(self) -> bytes:
        return bytes(self._state)

    def diff(self, new_state: bytes) -> str:
        """Compare current state to new_state and emit diff frame.

        Internal state is updated to new_state.
        """
        old = bytes(self._state)
        frame = encode_diff(old, new_state)
        self._state = bytearray(new_state)
        return frame

    def apply(self, frame: str) -> str:
        """Apply a diff frame to current state.

        Returns the incoming frame (the diff that was applied),
        so relay chains can forward it downstream.

        >>> ds = DiffState(b'AB')
        >>> ds.apply('1:--------|')
        '1:--------|'
        >>> ds.state
        b'A\\xff'
        """
        new_state = decode_diff(bytes(self._state), frame)
        self._state = bytearray(new_state)
        return frame

    def sync(self, new_state: bytes) -> str:
        """Replace state entirely, emit full sync frame.

        Useful for initial handshake or recovery.
        """
        self._state = bytearray(new_state)
        return ''.join(f"{i}:{bits_to_morse(b)}|" for i, b in enumerate(new_state))

    def __repr__(self) -> str:
        return f"DiffState({bytes(self._state)!r})"


if __name__ == '__main__':
    import doctest

    results = doctest.testmod(verbose=False)
    print(f"Doctests: {results.attempted} attempted, {results.failed} failed")
    print(f"Examples verified: encode_diff, decode_diff, DiffState")
