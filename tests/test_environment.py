from pathlib import Path


def test_runtime_dependencies_are_declared():
    project_root = Path(__file__).resolve().parents[1]
    content = (project_root / "pyproject.toml").read_text(encoding="utf-8")

    for dependency in ("fastapi", "pandapower", "simpy", "coptpy"):
        assert dependency in content
