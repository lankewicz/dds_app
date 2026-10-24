"""Install the isolated read-only API on the Orange. Does not restart the collector."""
import datetime
import grp
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import subprocess
import sys
import zipfile


def main():
    if os.geteuid() != 0:
        raise SystemExit("Executar como administrador no Orange")
    app = Path("/home/orangepi/dds-events-api")
    unit = Path("/etc/systemd/system/orange-events-api.service")
    marker = app / ".readonly-api-managed"
    if app.is_symlink() or unit.is_symlink():
        raise SystemExit("Destino de instalação inesperado")
    if app.exists() and any(app.iterdir()) and not marker.exists():
        raise SystemExit("Diretório existente não gerenciado; revisar antes de instalar")
    if unit.exists() and "WorkingDirectory=/home/orangepi/dds-events-api" not in unit.read_text():
        raise SystemExit("Unit existente pertence a outra instalação")
    names = {"events_api.py", "data_routes.py", "data_roots.py", "rotalog_event_contract.py",
             "torre_access.py", "orange-events-api.service"}
    with zipfile.ZipFile(sys.argv[1]) as archive:
        if set(archive.namelist()) != names:
            raise SystemExit("Pacote de instalação incompatível")
        sources = {name: archive.read(name) for name in names}
    uid, gid = pwd.getpwnam("orangepi").pw_uid, grp.getgrnam("orangepi").gr_gid
    app.mkdir(mode=0o700, exist_ok=True)
    os.chown(app, uid, gid)
    app.chmod(0o700)
    backup = app / "backups" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name in names - {unit.name}:
        destination = app / name
        if destination.is_symlink():
            raise SystemExit("Arquivo da aplicação não pode ser link simbólico")
        if destination.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup / name)
        destination.write_bytes(sources[name])
        destination.chmod(0o644)
        os.chown(destination, uid, gid)
    env_path = app / ".env"
    if env_path.is_symlink():
        raise SystemExit("Configuração não pode ser link simbólico")
    settings = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and not name.startswith("#"):
                settings[name.strip()] = value
    if len(settings.get("TORRE_SIGNING_KEY", "")) < 32:
        settings["TORRE_SIGNING_KEY"] = secrets.token_hex(32)
    settings.update({
        "DDS_EMPRESA_PADRAO": "ChicoEletro",
        "TORRE_ALLOWED_ORIGINS": "https://chicoeletro.web.app,https://chicoeletro.firebaseapp.com",
        "ROTALOG_DATA_ROOT": "/mnt/ssd/dds-coletor-rtl/chicoeletro/dados-local",
        "ROTALOG_FALLBACK_ROOT": "/home/orangepi/dds-coletor-rtl/dados-local",
        "ROTALOG_EVENTS_FILE": "/mnt/ssd/dds-coletor-rtl/chicoeletro/dados-local/rotalog/events/current/index.json.gz",
        "ROTALOG_SSD_MOUNT": "/mnt/ssd",
        "ROTALOG_SSD_UUID": "185b3d33-422b-493c-8d1a-ccd3b914f038",
    })
    temporary_env = app / ".env.installing"
    with os.fdopen(os.open(temporary_env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as stream:
        stream.write("".join(f"{name}={value}\n" for name, value in settings.items()))
    os.chown(temporary_env, uid, gid)
    temporary_env.replace(env_path)
    marker.write_text("dds-webtools read-only API\n")
    os.chown(marker, uid, gid)
    if unit.exists():
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unit, backup / unit.name)
    unit.write_bytes(sources[unit.name])
    unit.chmod(0o644)
    subprocess.run(["systemd-analyze", "verify", str(unit)], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", unit.name], check=True)
    subprocess.run(["systemctl", "restart", unit.name], check=True)
    subprocess.run(["systemctl", "is-active", unit.name], check=True)
    print(json.dumps({"installed": True, "dataWritesEnabled": False, "collectorRestarted": False,
                      "primary": settings["ROTALOG_DATA_ROOT"], "fallbackOnlyWhenSsdOffline": True}))


if __name__ == "__main__":
    main()
