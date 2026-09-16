"""Private key storage for the signing service.

Keys are 32-byte ML-DSA seeds held one per file, named by key id. In a deployed
environment the directory is populated at start-up from a secret manager and the
process runs with no other access to it.

The seeds never leave this module: callers receive signatures, never key
material, and the loaded seed is not cached in a way the rest of the process can
reach.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from medcrypto.keys import PRIVATE_KEY_SEED_BYTES

KEY_ID_RE = re.compile(r"\Amldsa65-[0-9a-f]{32}\Z")


class KeyNotAvailable(Exception):
    """The requested key is not present in this signer's store."""


class KeyStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, key_id: str) -> Path:
        # key_id is attacker-influenced in the sense that it arrives over the
        # wire, so it is validated against a strict pattern before touching the
        # filesystem rather than being trusted as a path component.
        if not KEY_ID_RE.match(key_id):
            raise KeyNotAvailable(f"malformed key id: {key_id!r}")
        return self.root / f"{key_id}.seed"

    def has(self, key_id: str) -> bool:
        try:
            return self.path_for(key_id).is_file()
        except KeyNotAvailable:
            return False

    def load_seed(self, key_id: str) -> bytes:
        path = self.path_for(key_id)
        if not path.is_file():
            raise KeyNotAvailable(f"no key material for {key_id}")
        seed = path.read_bytes()
        if len(seed) != PRIVATE_KEY_SEED_BYTES:
            raise KeyNotAvailable(
                f"key {key_id} is {len(seed)} bytes, expected {PRIVATE_KEY_SEED_BYTES}"
            )
        return seed

    def store_seed(self, key_id: str, seed: bytes) -> Path:
        """Write a seed to the store with owner-only permissions.

        Intended for provisioning and tests. Production seeds arrive from a
        secret manager at start-up.
        """
        if len(seed) != PRIVATE_KEY_SEED_BYTES:
            raise ValueError(f"seed must be {PRIVATE_KEY_SEED_BYTES} bytes")
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, stat.S_IRWXU)
        path = self.path_for(key_id)
        path.write_bytes(seed)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return path
