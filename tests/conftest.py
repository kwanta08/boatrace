from pathlib import Path

import pytest

from boatev.config import load_config
from boatev.lzh import find_sevenzip

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def sevenzip_exe() -> Path:
    """実在する 7z。config.yaml があればその tools.sevenzip、無ければ config.example.yaml の値。

    実在しなければ、7z を実際に呼ぶテストを skip する。
    """
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.is_file():
        cfg_path = ROOT / "config.example.yaml"
    exe = find_sevenzip(load_config(cfg_path).sevenzip)
    if exe is None:
        pytest.skip(f"7-Zip が実在しない（{cfg_path.name} の tools.sevenzip）")
    return exe
