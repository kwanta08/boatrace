from pathlib import Path

import pytest
import yaml

from boatev import __version__
from boatev.config import VERSION_PLACEHOLDER, ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.yaml"


def _write(tmp_path: Path, mutate=None) -> Path:
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    if mutate:
        mutate(raw)
    p = tmp_path / "sub" / "config.yaml"
    p.parent.mkdir(exist_ok=True)
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return p


def test_example_loads():
    cfg = load_config(EXAMPLE)
    assert cfg.role == "dev"
    assert cfg.lzh_interval_sec == 2.0
    assert cfg.page_interval_sec == 3.0
    assert cfg.monthly_yen == 10000
    assert isinstance(cfg.sevenzip, Path)


def test_relative_paths_resolved_from_config_dir(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.data_dir == (tmp_path / "sub" / "data").resolve()
    assert cfg.models_dir == (tmp_path / "sub" / "models").resolve()
    assert cfg.reports_dir == (tmp_path / "sub" / "reports").resolve()


def test_absolute_path_kept(tmp_path):
    abs_dir = (tmp_path / "abs").resolve()

    def m(raw):
        raw["paths"]["data_dir"] = str(abs_dir)

    assert load_config(_write(tmp_path, m)).data_dir == abs_dir


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [("fetch", "lzh_interval_sec", 1.9), ("fetch", "page_interval_sec", 2.9)],
)
def test_interval_below_floor_rejected(tmp_path, section, key, value):
    def m(raw):
        raw[section][key] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, m))


@pytest.mark.parametrize("key", ["lzh_interval_sec", "page_interval_sec"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_interval_non_finite_rejected(tmp_path, key, value):
    def m(raw):
        raw["fetch"][key] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, m))


@pytest.mark.parametrize("value", [0, -1, -0.5, float("nan"), float("inf"), float("-inf")])
def test_timeout_must_be_positive_finite(tmp_path, value):
    def m(raw):
        raw["fetch"]["timeout_sec"] = value

    with pytest.raises(ConfigError, match="timeout_sec"):
        load_config(_write(tmp_path, m))


def test_timeout_positive_ok(tmp_path):
    def m(raw):
        raw["fetch"]["timeout_sec"] = 0.5

    assert load_config(_write(tmp_path, m)).timeout_sec == 0.5


def test_user_agent_version_filled_from_package(tmp_path):
    example = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert VERSION_PLACEHOLDER in example["fetch"]["user_agent"]
    assert __version__ not in example["fetch"]["user_agent"]  # 版の直書きなし
    cfg = load_config(EXAMPLE)
    assert cfg.user_agent == f"boatev/{__version__} (private use)"


def test_user_agent_without_placeholder_kept(tmp_path):
    def m(raw):
        raw["fetch"]["user_agent"] = "my-agent/1"

    assert load_config(_write(tmp_path, m)).user_agent == "my-agent/1"


def test_interval_at_floor_ok(tmp_path):
    def m(raw):
        raw["fetch"]["lzh_interval_sec"] = 2
        raw["fetch"]["page_interval_sec"] = 3

    assert load_config(_write(tmp_path, m)).page_interval_sec == 3.0


@pytest.mark.parametrize(
    ("section", "key"),
    [("tools", "sevenzip"), ("paths", "data_dir"), ("betting", "kelly"), ("machine", "role")],
)
def test_missing_key(tmp_path, section, key):
    def m(raw):
        del raw[section][key]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, m))


def test_missing_section(tmp_path):
    def m(raw):
        del raw["budget"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, m))


def test_bad_role(tmp_path):
    def m(raw):
        raw["machine"]["role"] = "prod"

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, m))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_no_hardcoded_sevenzip_in_code():
    for f in (ROOT / "boatev").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "7z.exe" not in text, f
        assert "Program Files" not in text, f
