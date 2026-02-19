"""Script to copy EA files to MT5 data folder."""

import shutil
import sys
from pathlib import Path


def find_mt5_data_folder() -> Path | None:
    """Find MT5 data folder in common locations."""
    appdata = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    if not appdata.exists():
        return None

    # Find terminal folders (each has a long hash name)
    for terminal_dir in appdata.iterdir():
        if terminal_dir.is_dir() and len(terminal_dir.name) == 32:
            mql5_dir = terminal_dir / "MQL5"
            if mql5_dir.exists():
                return mql5_dir
    return None


def install():
    src_dir = Path(__file__).parent.parent / "mt5"
    mql5_dir = find_mt5_data_folder()

    if not mql5_dir:
        print("ERROR: Could not find MT5 data folder.")
        print("Manually copy mt5/TradeAgent.mq5 to your MT5 MQL5/Experts/ folder.")
        sys.exit(1)

    # Copy EA
    ea_src = src_dir / "TradeAgent.mq5"
    ea_dst = mql5_dir / "Experts" / "TradeAgent.mq5"
    ea_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ea_src, ea_dst)
    print(f"Copied EA: {ea_dst}")

    # Copy Include files
    include_src = src_dir / "Include"
    if include_src.exists():
        include_dst = mql5_dir / "Include"
        for f in include_src.rglob("*"):
            if f.is_file():
                dst = include_dst / f.relative_to(include_src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
                print(f"Copied: {dst}")

    # Copy Library files
    lib_src = src_dir / "Libraries"
    if lib_src.exists():
        lib_dst = mql5_dir / "Libraries"
        for f in lib_src.rglob("*"):
            if f.is_file():
                dst = lib_dst / f.relative_to(lib_src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
                print(f"Copied: {dst}")

    print("\nInstallation complete! Restart MT5 and compile the EA.")


if __name__ == "__main__":
    install()
