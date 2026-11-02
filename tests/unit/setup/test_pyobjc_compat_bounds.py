"""Protect macOS Intel binaries from unvalidated SDK-27 PyObjC bindings.

PyObjC 13 wheels are built with Xcode 27 and may fail on older macOS runners
with a missing libswiftCoreMedia.dylib; keep project extras and lock coherent.
"""

from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[3]


def test_all_macos_framework_extras_exclude_pyobjc_13() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]["desktop-macos"]
    pyobjc = [Requirement(item) for item in extras if item.startswith("pyobjc-framework-")]
    assert len(pyobjc) == 12
    names = {req.name.lower() for req in pyobjc}
    assert {
        "pyobjc-framework-avfoundation",
        "pyobjc-framework-coremedia",
        "pyobjc-framework-coreaudio",
        "pyobjc-framework-cocoa",
        "pyobjc-framework-webkit",
        "pyobjc-framework-security",
        "pyobjc-framework-uniformtypeidentifiers",
    } <= names
    assert any(Requirement(item).name.lower() == "pyobjc-core"
               for item in extras)
    assert all("12.2.1" in req.specifier for req in pyobjc)
    assert all("13" not in req.specifier for req in pyobjc)
    assert all("13" not in Requirement(item).specifier
               for item in extras if item.startswith("pyobjc-"))


def test_locked_pyobjc_core_and_frameworks_remain_below_13() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {
        p["name"]: Version(p["version"])
        for p in lock["package"]
        if p["name"].startswith("pyobjc-")
    }
    assert len(packages) >= 5
    assert all(version < Version("13") for version in packages.values())
