"""PyInstaller-friendly launcher for tacz-updater."""

from tacz_updater.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
