"""Static checks on the source tree."""

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "app" / "domain"
FORBIDDEN_ROOTS = {"fastapi", "pydantic", "sqlite3", "starlette"}


def _imported_modules(path: Path) -> list[tuple[str, int]]:
    """(module, relative level) for every import in a file."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


def test_domain_imports_no_framework_db_or_other_app_package() -> None:
    """AD-1 / AD-8: app/domain imports no fastapi, pydantic, sqlite3 or other app package."""
    files = sorted(DOMAIN.rglob("*.py"))
    assert files, "app/domain has no modules"
    violations = []
    for path in files:
        for module, level in _imported_modules(path):
            root = module.split(".")[0]
            if level == 0 and root in FORBIDDEN_ROOTS:
                violations.append(f"{path.name}: {module}")
            elif level == 0 and root == "app" and not module.startswith("app.domain"):
                violations.append(f"{path.name}: {module}")
            elif level > 1:  # relative import that climbs out of app/domain
                violations.append(f"{path.name}: {'.' * level}{module}")
    assert not violations


def test_layered_package_tree_exists() -> None:
    """FR9 / AD-1: the service has the layered packages from the architecture spine."""
    for package in ("api", "services", "domain", "repositories", "infra"):
        assert (ROOT / "app" / package / "__init__.py").is_file()


def test_repo_tracks_no_env_files() -> None:
    """NFR4: the repo contains no .env files (tracked or untracked-but-not-ignored)."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    env_files = [p for p in listed if Path(p).name == ".env" or Path(p).name.startswith(".env.")]
    assert [p for p in env_files if not p.endswith(".env.example")] == []
