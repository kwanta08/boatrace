import re
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_packages_explicit():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["setuptools"]["packages"] == ["boatev"]
    requires = data["build-system"]["requires"]
    assert any(r.startswith("setuptools") for r in requires)
    assert all("==" in r for r in requires)


def _lines(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_requirements_pinned():
    for name in ("requirements.txt", "requirements-dev.txt"):
        for line in _lines(ROOT / name):
            assert line.startswith("-r ") or re.fullmatch(r"[A-Za-z0-9_.\-]+==[^=\s]+", line), line


def _collect(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in _lines(path):
        if line.startswith("-r "):
            pins.update(_collect(path.parent / line[3:].strip()))
        else:
            name, ver = line.split("==")
            pins[_norm(name)] = ver
    return pins


def test_pins_match_installed():
    pins = _collect(ROOT / "requirements-dev.txt")
    installed = {
        _norm(d.metadata["Name"]): d.version
        for d in metadata.distributions()
        if _norm(d.metadata["Name"]) not in {"pip", "boatev"}
    }
    assert pins == installed


def test_gitignore_entries():
    entries = set(_lines(ROOT / ".gitignore"))
    for e in ("data/", "models/", "reports/", "config.yaml", "tests/fixtures/real/", ".env"):
        assert e in entries, e
    assert ".venv/" in entries or ".venv" in entries


def test_layout():
    assert (ROOT / "boatev" / "__init__.py").is_file()
    assert (ROOT / "config.example.yaml").is_file()
    assert (ROOT / "tests").is_dir()
