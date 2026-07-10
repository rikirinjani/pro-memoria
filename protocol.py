"""Pro Memoria — Protocol State Machine.

Defines the handshake→sync→data→error→recovery lifecycle for the
Pro Memoria protocol. Builds on the Hamming/Parity command tiers
from lexicon.py and the DSP frame format from dsp.py.

Wire format:
  DSP frames carry state diffs. Hamming/Parity commands are embedded
  in DSP frame data or sent as single-byte command frames (no index).
  A command-only frame: "<hamming_morse>|" (index omitted = command).
"""

from enum import Enum, auto


class ProtocolState(Enum):
    """Valid protocol states in the connection lifecycle."""
    CLOSED = auto()       # No connection
    HANDSHAKE = auto()    # Version negotiation
    SYNCING = auto()      # State synchronization
    DATA = auto()         # Normal operation
    ERROR = auto()        # Recoverable error
    RECOVERY = auto()     # Re-syncing after error
    DISCONNECT = auto()   # Clean shutdown


# ── State transitions ─────────────────────────────────────────────────

def next_state(current: ProtocolState, command: str) -> ProtocolState:
    """Determine the next protocol state given a command.

    >>> next_state(ProtocolState.HANDSHAKE, 'ACK').name
    'SYNCING'
    >>> next_state(ProtocolState.HANDSHAKE, 'NAK').name
    'DISCONNECT'
    >>> next_state(ProtocolState.ERROR, 'RETRY').name
    'RECOVERY'
    >>> next_state(ProtocolState.DATA, 'BYE').name
    'DISCONNECT'
    """
    transitions = {
        ProtocolState.CLOSED: {
            'HELLO': ProtocolState.HANDSHAKE,
            'VERSION': ProtocolState.HANDSHAKE,
        },
        ProtocolState.HANDSHAKE: {
            'ACK': ProtocolState.SYNCING,
            'NAK': ProtocolState.DISCONNECT,
            'VERSION_ACK': ProtocolState.HANDSHAKE,
            'VERSION': ProtocolState.HANDSHAKE,
            'BYE': ProtocolState.DISCONNECT,
        },
        ProtocolState.SYNCING: {
            'SYNC': ProtocolState.SYNCING,
            'STATE_REP': ProtocolState.SYNCING,
            'ACK': ProtocolState.DATA,
            'NAK': ProtocolState.SYNCING,
            'ERR': ProtocolState.ERROR,
            'BYE': ProtocolState.DISCONNECT,
        },
        ProtocolState.DATA: {
            'ERR': ProtocolState.ERROR,
            'BYE': ProtocolState.DISCONNECT,
            'HALT': ProtocolState.DISCONNECT,
            'EOF': ProtocolState.DATA,
            'ECHO': ProtocolState.DATA,
            'STATUS': ProtocolState.DATA,
            'PING': ProtocolState.DATA,
        },
        ProtocolState.ERROR: {
            'RETRY': ProtocolState.RECOVERY,
            'RESET': ProtocolState.RECOVERY,
            'STATUS': ProtocolState.ERROR,
            'BYE': ProtocolState.DISCONNECT,
            'HALT': ProtocolState.DISCONNECT,
        },
        ProtocolState.RECOVERY: {
            'RESET': ProtocolState.RECOVERY,
            'REQ': ProtocolState.RECOVERY,
            'STATE_REP': ProtocolState.SYNCING,
            'ACK': ProtocolState.DATA,
            'NAK': ProtocolState.RECOVERY,
            'BYE': ProtocolState.DISCONNECT,
        },
        ProtocolState.DISCONNECT: {
            'BYE': ProtocolState.CLOSED,
            'HALT': ProtocolState.CLOSED,
        },
    }
    return transitions.get(current, {}).get(command, current)


# ── Allowed commands per state ────────────────────────────────────────

ALLOWED_COMMANDS: dict[ProtocolState, set[str]] = {
    ProtocolState.CLOSED: {'HELLO', 'VERSION'},
    ProtocolState.HANDSHAKE: {'VERSION', 'VERSION_ACK', 'ACK', 'NAK', 'BYE'},
    ProtocolState.SYNCING: {'SYNC', 'STATE_REQ', 'STATE_REP', 'ACK', 'NAK', 'ERR', 'BYE'},
    ProtocolState.DATA: {
        'NOP', 'ACK', 'NAK', 'EOF', 'ERR', 'STATUS', 'ECHO',
        'PING', 'PONG', 'DIFF', 'FULL_SYNC', 'BYE', 'HALT',
        'NOP_LOW', 'COMPRESS', 'DECOMPRESS', 'ENCRYPT', 'DECRYPT',
        'SIGN', 'VERIFY',
    },
    ProtocolState.ERROR: {'ERR', 'RETRY', 'RESET', 'STATUS', 'BYE', 'HALT'},
    ProtocolState.RECOVERY: {'RESET', 'REQ', 'STATE_REP', 'ACK', 'NAK', 'BYE'},
    ProtocolState.DISCONNECT: {'BYE', 'HALT'},
}


# ── Handshake sequence ────────────────────────────────────────────────

HANDSHAKE_SEQUENCE: list[tuple[ProtocolState, str, str]] = [
    # (from_state, command, next_state_description)
    (ProtocolState.CLOSED, 'HELLO', 'initiate connection'),
    (ProtocolState.HANDSHAKE, 'VERSION', 'send protocol version'),
    (ProtocolState.HANDSHAKE, 'VERSION_ACK', 'acknowledge version'),
    (ProtocolState.HANDSHAKE, 'ACK', 'proceed to sync'),
    (ProtocolState.SYNCING, 'SYNC', 'request full state'),
    (ProtocolState.SYNCING, 'STATE_REP', 'send current state'),
    (ProtocolState.SYNCING, 'ACK', 'enter data mode'),
]


# ── Error recovery sequence ───────────────────────────────────────────

ERROR_RECOVERY_SEQUENCE: list[tuple[ProtocolState, str, str]] = [
    # (from_state, command, effect)
    (ProtocolState.ERROR, 'STATUS', 'diagnose error'),
    (ProtocolState.ERROR, 'RESET', 'reset state machine'),
    (ProtocolState.RECOVERY, 'RESET', 'reset agent state'),
    (ProtocolState.RECOVERY, 'REQ', 'request full state'),
    (ProtocolState.RECOVERY, 'STATE_REP', 'receive full state'),
    (ProtocolState.RECOVERY, 'ACK', 'resume data mode'),
]


# ── Connection lifecycle ──────────────────────────────────────────────

def allowed(current: ProtocolState, command: str) -> bool:
    """Check if a command is valid in the current state.

    >>> allowed(ProtocolState.CLOSED, 'HELLO')
    True
    >>> allowed(ProtocolState.CLOSED, 'DATA')
    False
    >>> allowed(ProtocolState.DATA, 'ECHO')
    True
    >>> allowed(ProtocolState.DATA, 'VERSION')
    False
    """
    return command in ALLOWED_COMMANDS.get(current, set())


def can_transition(current: ProtocolState, target: ProtocolState) -> bool:
    """Check if any valid command can move from current to target."""
    cmds = ALLOWED_COMMANDS.get(current, set())
    return any(next_state(current, c) == target for c in cmds)


if __name__ == '__main__':
    import doctest
    results = doctest.testmod(verbose=False)
    print(f"Doctests: {results.attempted} attempted, {results.failed} failed")

    print("\nProtocol State Machine:")
    print(f"{'State':15s} {'Allowed Commands':45s} {'Can transition to':30s}")
    print("-" * 90)
    for state in ProtocolState:
        cmds = ', '.join(sorted(ALLOWED_COMMANDS[state]))
        targets = ', '.join(
            sorted(t.name for t in ProtocolState
                   if t != state and can_transition(state, t))
        )
        print(f"{state.name:15s} {cmds:45s} {targets:30s}")
