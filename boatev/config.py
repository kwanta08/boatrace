"""config.yaml の設定ローダ。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from boatev import __version__

# fetch.user_agent 内のこの文字列を boatev.__version__ に置き換える（版の二重管理を避ける）
VERSION_PLACEHOLDER = "{version}"
LZH_INTERVAL_MIN = 2.0
PAGE_INTERVAL_MIN = 3.0
ROLES = ("dev", "exec")


class ConfigError(Exception):
    """設定の読み込み・検証の失敗。"""


@dataclass(frozen=True)
class Config:
    role: str
    data_dir: Path
    models_dir: Path
    reports_dir: Path
    sevenzip: Path
    lzh_interval_sec: float
    page_interval_sec: float
    timeout_sec: float
    user_agent: str
    lzh_base: str
    race_page_base: str
    ev_min: float
    p_min: float
    odds_max: float
    kelly: float
    bet_cap_fraction: float
    bet_cap_yen: int
    unit_yen: int
    monthly_yen: int
    daily_stop_fraction: float


def _get(raw: dict[str, Any], section: str, key: str) -> Any:
    sec = raw.get(section)
    if not isinstance(sec, dict):
        raise ConfigError(f"必須セクションがありません: {section}")
    if key not in sec or sec[key] is None:
        raise ConfigError(f"必須キーがありません: {section}.{key}")
    return sec[key]


def _num(raw: dict[str, Any], section: str, key: str) -> float:
    v = _get(raw, section, key)
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ConfigError(f"数値ではありません: {section}.{key}")
    return float(v)


def _int(raw: dict[str, Any], section: str, key: str) -> int:
    v = _get(raw, section, key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"整数ではありません: {section}.{key}")
    return v


def _str(raw: dict[str, Any], section: str, key: str) -> str:
    v = _get(raw, section, key)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"文字列ではありません: {section}.{key}")
    return v


def load_config(path: str | Path) -> Config:
    """config を読む。相対パスは config ファイルの位置基準で解決する。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"設定ファイルを読めません: {p} ({e})") from e
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML として読めません: {p} ({e})") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"設定のトップ階層がマップではありません: {p}")

    base = p.resolve().parent

    def resolve(s: str) -> Path:
        q = Path(s).expanduser()
        return q if q.is_absolute() else (base / q).resolve()

    role = _str(raw, "machine", "role")
    if role not in ROLES:
        raise ConfigError(f"machine.role は {ROLES} のどちらか: {role}")

    lzh_iv = _num(raw, "fetch", "lzh_interval_sec")
    page_iv = _num(raw, "fetch", "page_interval_sec")
    # nan は比較が常に False になるので「下限以上」の形で判定し、inf も有限でないとして弾く
    if not (math.isfinite(lzh_iv) and lzh_iv >= LZH_INTERVAL_MIN):
        raise ConfigError(f"fetch.lzh_interval_sec は {LZH_INTERVAL_MIN} 以上の有限値: {lzh_iv}")
    if not (math.isfinite(page_iv) and page_iv >= PAGE_INTERVAL_MIN):
        raise ConfigError(f"fetch.page_interval_sec は {PAGE_INTERVAL_MIN} 以上の有限値: {page_iv}")

    timeout = _num(raw, "fetch", "timeout_sec")
    if not (math.isfinite(timeout) and timeout > 0):
        raise ConfigError(f"fetch.timeout_sec は正の有限値: {timeout}")

    return Config(
        role=role,
        data_dir=resolve(_str(raw, "paths", "data_dir")),
        models_dir=resolve(_str(raw, "paths", "models_dir")),
        reports_dir=resolve(_str(raw, "paths", "reports_dir")),
        sevenzip=Path(_str(raw, "tools", "sevenzip")).expanduser(),
        lzh_interval_sec=lzh_iv,
        page_interval_sec=page_iv,
        timeout_sec=timeout,
        user_agent=_str(raw, "fetch", "user_agent").replace(VERSION_PLACEHOLDER, __version__),
        lzh_base=_str(raw, "urls", "lzh_base"),
        race_page_base=_str(raw, "urls", "race_page_base"),
        ev_min=_num(raw, "betting", "ev_min"),
        p_min=_num(raw, "betting", "p_min"),
        odds_max=_num(raw, "betting", "odds_max"),
        kelly=_num(raw, "betting", "kelly"),
        bet_cap_fraction=_num(raw, "betting", "bet_cap_fraction"),
        bet_cap_yen=_int(raw, "betting", "bet_cap_yen"),
        unit_yen=_int(raw, "betting", "unit_yen"),
        monthly_yen=_int(raw, "budget", "monthly_yen"),
        daily_stop_fraction=_num(raw, "budget", "daily_stop_fraction"),
    )
