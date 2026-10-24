"""Select the SSD or the explicitly configured local fallback; never mix missing files."""
import os
from pathlib import Path
import re


class DataRoots:
    def __init__(self, primary, fallback=None, mount_point=None, expected_uuid=None):
        self.primary = Path(primary)
        self.fallback = Path(fallback) if fallback else None
        self.mount_point = Path(mount_point) if mount_point else None
        if expected_uuid and not re.fullmatch(r"[0-9a-fA-F-]+", expected_uuid):
            raise ValueError("UUID inválido")
        self.expected_uuid = expected_uuid

    def ssd_available(self):
        if self.mount_point is None:
            return True
        if not os.path.ismount(self.mount_point):
            return False
        if self.expected_uuid:
            try:
                device = Path("/dev/disk/by-uuid") / self.expected_uuid
                return device.stat().st_rdev == self.mount_point.stat().st_dev
            except FileNotFoundError:
                return False
        return True

    def select(self):
        if self.ssd_available():
            root, source = self.primary, "ssd"
        elif self.fallback is not None:
            root, source = self.fallback, "local"
        else:
            raise OSError("SSD indisponível e sem alternativa configurada")
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise OSError("Raiz de dados inválida")
        return root, source
