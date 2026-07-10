"""PM-1 Handshake — encoding negotiation between two agents.

Flow:
  1. HELLO (always PM-1 Morse — guaranteed to work)
  2. VERSION / VERSION_ACK
  3. ENCODING {morse[, braille]} — initiator advertises supported encodings
  4. ENCODING_ACK <encoding> — responder selects best shared encoding
  5. ACK — proceed to sync
  6. SYNC / STATE_REP — full state exchange in negotiated encoding

On error recovery: encoder resets to Morse, re-negotiation required.
"""

from hybrid import HybridEncoder, ENCODING_MORSE, ENCODING_BRAILLE, SUPPORTED_ENCODINGS
from protocol import ProtocolState, next_state, allowed


class HandshakeError(Exception):
    """Raised when handshake fails (version mismatch, encoding mismatch, etc.)."""


class HybridHandshake:
    """Drives encoding handshake between two agents.

    Usage:
        hs = HybridHandshake()
        hs.initiate()        # start from CLOSED
        hs.send_encoding()   # advertise supported encodings
        hs.recv_ack(ack)     # responder picks best
        # -> encoder now upgraded
    """

    def __init__(self, supported: set[str] | None = None):
        self.supported = supported or SUPPORTED_ENCODINGS
        self.encoder = HybridEncoder(ENCODING_MORSE)
        self.state = ProtocolState.CLOSED
        self.peer_encodings: set[str] | None = None

    def transition(self, command: str) -> None:
        """Apply a protocol state transition."""
        self.state = next_state(self.state, command)

    def initiate(self) -> str:
        """Begin handshake from CLOSED -> HANDSHAKE.

        Returns 'HELLO' command.
        """
        self.state = ProtocolState.HANDSHAKE
        return 'HELLO'

    def send_encoding(self) -> str:
        """Advertise supported encodings to peer.

        Returns ENCODING command with supported set.
        """
        enc_list = ','.join(sorted(self.supported))
        return f"ENCODING {enc_list}"

    def recv_encoding(self, advertised: str) -> str:
        """Receive peer's supported encodings and select best match.

        Returns ENCODING_ACK with selected encoding.
        Best priority: braille > morse (density wins).
        """
        peer_set = set(advertised.replace('ENCODING ', '').split(','))
        self.peer_encodings = peer_set
        available = self.supported & peer_set

        if ENCODING_BRAILLE in available:
            selected = ENCODING_BRAILLE
        elif ENCODING_MORSE in available:
            selected = ENCODING_MORSE
        else:
            raise HandshakeError(
                f"No compatible encoding. Local: {self.supported}, peer: {peer_set}"
            )

        return f"ENCODING_ACK {selected}"

    def recv_ack(self, ack: str) -> None:
        """Process ENCODING_ACK from responder.

        Upgrades encoder to negotiated encoding.
        """
        if not ack.startswith('ENCODING_ACK '):
            raise HandshakeError(f"Expected ENCODING_ACK, got: {ack}")

        encoding = ack.split(' ', 1)[1]
        if encoding not in self.supported:
            raise HandshakeError(f"Peer selected unsupported encoding: {encoding}")

        self.encoder.upgrade_to(encoding)

    def reset(self) -> None:
        """Reset handshake state. Encoder reverts to Morse."""
        self.encoder.reset()
        self.state = ProtocolState.CLOSED
        self.peer_encodings = None

    def full_handshake_initiator(self, peer_advertised: str) -> list[str]:
        """Run complete handshake as initiator.

        Returns sequence of commands to send.
        """
        cmds = [
            self.initiate(),
            'VERSION 1.0',
            self.send_encoding(),
        ]
        ack_cmd = self.recv_encoding(peer_advertised)
        cmds.append(ack_cmd)
        self.recv_ack(ack_cmd)
        cmds.append('ACK')
        self.transition('ACK')
        return cmds

    def full_handshake_responder(self, received: list[str]) -> list[str]:
        """Process incoming handshake as responder. Returns response commands."""
        responses = []
        for cmd in received:
            if cmd == 'HELLO':
                self.state = ProtocolState.HANDSHAKE
            elif cmd.startswith('VERSION'):
                responses.append('VERSION_ACK 1.0')
            elif cmd.startswith('ENCODING '):
                ack = self.recv_encoding(cmd)
                responses.append(ack)
            elif cmd == 'ACK':
                self.state = ProtocolState.SYNCING
        return responses
