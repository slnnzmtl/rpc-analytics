from pathlib import Path

from rpc_analytics import __version__


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_architecture_doc_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "architecture.md").is_file()
    assert (root / "docs" / "threat-model.md").is_file()
