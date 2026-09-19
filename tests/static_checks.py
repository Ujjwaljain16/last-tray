"""A static check for 'this module must not read raw data', usable on real modules AND on deliberately bad source in negative tests."""
from __future__ import annotations

import ast

FORBIDDEN_IMPORTS = {"tarfile", "zipfile", "shutil", "glob", "socket", "requests", "urllib", "http"}
FORBIDDEN_MODULES = {"src.ingest.handoff", "src.ingest.flavoria", "src.ingest.retrieval", "src.ingest.requests_client", "src.ingest.snapshot", "src.ingest.preserve",
                     "src.ingest.ingest", "src.ingest.http", "src.stage.stage", "src.stage.events", "src.stage.components", "src.stage.timestamps", "src.stage.weather",
                     "src.validate.load"}
FILE_CALLS = {"read_bytes", "read_text", "open", "write_text", "write_bytes", "unlink", "mkdir"}


def _imports(tree: ast.AST) -> set[str]:
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
            mods |= {f"{n.module}.{a.name}" for a in n.names}
    return mods


def raw_access_violations(source: str, *, may_touch_files: bool = False) -> list[str]:
    """Reasons this source could read raw data (empty list = clean). Docstrings are prose and are ignored."""
    tree = ast.parse(source)
    problems = []
    mods = _imports(tree)
    problems += [f"imports {m}" for m in sorted({m.split(".")[0] for m in mods} & FORBIDDEN_IMPORTS)]
    problems += [f"imports {m}" for m in sorted(mods & FORBIDDEN_MODULES)]
    docstrings = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
    problems += [f"names the raw directory: {s!r}" for s in strings if "data/raw" in s or "data\raw" in s or s in ("data", "flavoria")]
    if not may_touch_files:
        attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        problems += [f"calls {c}" for c in sorted((attrs | names) & FILE_CALLS)]
    return problems
