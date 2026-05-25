"""AST-based argparse surface extractor for cortex-* console scripts.

Reads ``[project.scripts]`` from ``pyproject.toml`` via ``tomllib``, resolves
each ``module:attr`` target to a source path via ``importlib.util.find_spec``
(no imports — avoids side-effects), parses the source with ``ast``, and walks
for ``argparse.ArgumentParser(...)`` constructors and
``.add_argument(...)`` / ``.add_subparsers(...)`` / subparser ``.add_parser(...)``
calls.

Error codes emitted by this module:
  E201  cannot AST-parse module source for cortex-X at path Y
  E202  ambiguous main parser for cortex-X (tied add_argument counts)

The ``extract_surface()`` function is the primary public API.  All other
callables are internal helpers.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParserSurface:
    """Static representation of one ArgumentParser's accepted surface."""

    binary: str
    """The console-script binary name (e.g. ``cortex-create-backlog-item``)."""

    module_path: Path
    """Absolute path to the source file."""

    required_flags: set[str] = field(default_factory=set)
    """Long- and short-form flags declared with ``required=True``."""

    optional_flags: set[str] = field(default_factory=set)
    """Long- and short-form flags NOT declared required (or with a default)."""

    subcommands: dict[str, "ParserSurface"] = field(default_factory=dict)
    """Subcommand name → ParserSurface for each ``.add_parser(name)`` call."""

    extraction_status: Literal["ok", "ast_error", "ambiguous", "not_argparse"] = "ok"
    """Extraction outcome for this entry."""


@dataclass
class ExtractionError:
    """Non-fatal error emitted during surface extraction."""

    binary: str
    code: str  # E201 or E202
    message: str

    def format_text(self) -> str:
        return f"{self.code} {self.message}"


# ---------------------------------------------------------------------------
# tomllib helpers (mirrors cortex_command/parity_check.py:gather_entry_point_names)
# ---------------------------------------------------------------------------


def _load_project_scripts(pyproject_path: Path) -> dict[str, str]:
    """Return the ``[project.scripts]`` mapping or empty dict on any error."""
    if not pyproject_path.is_file():
        return {}
    try:
        with open(pyproject_path, "rb") as fh:
            data = tomllib.load(fh)
        scripts = data.get("project", {}).get("scripts", {})
        return scripts if isinstance(scripts, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Module path resolution (importlib.util — no import)
# ---------------------------------------------------------------------------


def _resolve_module_path(module_attr: str) -> Path | None:
    """Resolve ``module.path:attr`` to an absolute source path.

    Uses ``importlib.util.find_spec()`` which does NOT import the module;
    reads ``spec.origin`` for the file path.  Returns ``None`` if the spec
    cannot be found or has no origin.
    """
    if ":" not in module_attr:
        return None
    module_name, _attr = module_attr.split(":", 1)
    try:
        spec = importlib.util.find_spec(module_name)
    except (ModuleNotFoundError, ValueError):
        return None
    if spec is None or spec.origin is None:
        return None
    return Path(spec.origin)


# ---------------------------------------------------------------------------
# AST walking helpers
# ---------------------------------------------------------------------------


def _is_argument_parser_call(node: ast.Call) -> bool:
    """Return True if ``node`` looks like ``argparse.ArgumentParser(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        # argparse.ArgumentParser(...)
        if func.attr == "ArgumentParser":
            return True
    elif isinstance(func, ast.Name):
        # ArgumentParser(...) after ``from argparse import ArgumentParser``
        if func.id == "ArgumentParser":
            return True
    return False


def _method_name(node: ast.Call) -> str | None:
    """Return the method name if the call is a method call, else None."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_string_arg(args: list[ast.expr], keywords: list[ast.keyword],
                         keyword_name: str, positional_index: int = 0) -> str | None:
    """Extract a string literal from positional or keyword argument."""
    # Try keyword first
    for kw in keywords:
        if kw.arg == keyword_name:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    # Try positional
    if positional_index < len(args):
        a = args[positional_index]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
    return None


def _is_required(keywords: list[ast.keyword]) -> bool:
    """Return True if ``required=True`` is explicitly in the keyword args."""
    for kw in keywords:
        if kw.arg == "required":
            if isinstance(kw.value, ast.Constant):
                return bool(kw.value.value)
    return False


def _extract_flags_from_add_argument(node: ast.Call) -> tuple[list[str], bool]:
    """Return (flag_names, is_required) from an ``add_argument(...)`` call.

    Only collects long-form ``--flag`` and short-form ``-f`` names.
    Positional arguments (no leading ``-``) are ignored for flag validation.
    """
    flags: list[str] = []
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            val = arg.value
            if val.startswith("-"):
                flags.append(val)
    required = _is_required(node.keywords)
    return flags, required


# ---------------------------------------------------------------------------
# Multi-parser disambiguation
# ---------------------------------------------------------------------------


@dataclass
class _ParserNode:
    """Tracks an ArgumentParser variable assignment and its add_argument count."""

    assign_target: str | None  # variable name, e.g. "parser", or None for inline
    add_argument_count: int = 0
    flags_required: list[tuple[list[str], bool]] = field(default_factory=list)
    subparser_var: str | None = None
    # Subparser choices: name -> list of (flags, required) pairs
    subparser_choices: dict[str, list[tuple[list[str], bool]]] = field(default_factory=dict)


def _collect_parser_nodes(tree: ast.Module) -> list[_ParserNode]:
    """Walk the AST and collect ArgumentParser instances.

    Strategy:
    - Walk all nodes looking for ``argparse.ArgumentParser(...)`` constructor calls.
    - Track variable assignments so we can identify which ``.add_argument``
      calls belong to which parser.
    - Also track ``.add_subparsers()`` and subparser ``.add_parser(...)`` calls.

    This is necessarily heuristic for complex modules; the spec says to pick
    the parser with the most ``.add_argument`` calls as the main parser.
    """
    # Phase 1: find all ArgumentParser assignments and inline constructions.
    # We do a single flat walk; subparser tracking is best-effort.
    parsers: list[_ParserNode] = []
    # Map var_name -> _ParserNode for assignment-based tracking.
    var_to_parser: dict[str, _ParserNode] = {}
    # Map subparsers_var -> parser_node for add_subparsers tracking.
    subparsers_var_to_parser: dict[str, _ParserNode] = {}
    # Map subparser_choice_var -> (parent_parser_node, choice_name).
    subparser_choice_to_parser: dict[str, tuple[_ParserNode, str]] = {}

    for node in ast.walk(tree):
        # --- ArgumentParser constructor assignments ---
        if isinstance(node, ast.Assign):
            # Handle: parser = argparse.ArgumentParser(...)
            if isinstance(node.value, ast.Call) and _is_argument_parser_call(node.value):
                target_names: list[str] = []
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        target_names.append(t.id)
                pn = _ParserNode(assign_target=target_names[0] if target_names else None)
                parsers.append(pn)
                for name in target_names:
                    var_to_parser[name] = pn
            # Handle: sub = subparsers.add_parser("name") or similar
            elif isinstance(node.value, ast.Call):
                mn = _method_name(node.value)
                if mn == "add_parser":
                    choice_name = _extract_string_arg(node.value.args, node.value.keywords, "name", 0)
                    # Identify which parent's subparsers object this is called on.
                    func_val = node.value.func
                    if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                        sp_var = func_val.value.id
                        if sp_var in subparsers_var_to_parser and choice_name:
                            parent_pn = subparsers_var_to_parser[sp_var]
                            if choice_name not in parent_pn.subparser_choices:
                                parent_pn.subparser_choices[choice_name] = []
                            # Track the variable assigned for this subparser.
                            for t in node.targets:
                                if isinstance(t, ast.Name):
                                    subparser_choice_to_parser[t.id] = (parent_pn, choice_name)
                # Handle: subparsers = parser.add_subparsers(...)
                elif mn == "add_subparsers":
                    func_val = node.value.func
                    if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                        parser_var = func_val.value.id
                        if parser_var in var_to_parser:
                            pn = var_to_parser[parser_var]
                            for t in node.targets:
                                if isinstance(t, ast.Name):
                                    subparsers_var_to_parser[t.id] = pn
                                    pn.subparser_var = t.id

        # --- Augmented assignment / annotated assignment with ArgumentParser ---
        elif isinstance(node, ast.AnnAssign):
            if node.value and isinstance(node.value, ast.Call) and _is_argument_parser_call(node.value):
                target_name: str | None = None
                if isinstance(node.target, ast.Name):
                    target_name = node.target.id
                pn = _ParserNode(assign_target=target_name)
                parsers.append(pn)
                if target_name:
                    var_to_parser[target_name] = pn

        # --- Return statements with ArgumentParser constructor ---
        elif isinstance(node, ast.Return):
            if node.value and isinstance(node.value, ast.Call) and _is_argument_parser_call(node.value):
                # Could be ``return argparse.ArgumentParser(...)``; track as unnamed.
                pn = _ParserNode(assign_target=None)
                parsers.append(pn)

        # --- method calls: add_argument, add_subparsers ---
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            mn = _method_name(call)
            if mn == "add_argument":
                func_val = call.func
                if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                    receiver = func_val.value.id
                    flags, req = _extract_flags_from_add_argument(call)
                    if flags:
                        if receiver in var_to_parser:
                            var_to_parser[receiver].add_argument_count += 1
                            var_to_parser[receiver].flags_required.append((flags, req))
                        elif receiver in subparser_choice_to_parser:
                            parent_pn, choice_name = subparser_choice_to_parser[receiver]
                            parent_pn.subparser_choices[choice_name].append((flags, req))
            elif mn == "add_subparsers":
                func_val = call.func
                if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                    parser_var = func_val.value.id
                    if parser_var in var_to_parser:
                        # Inline (not assigned): just note it.
                        pass

    # Phase 2: handle inline add_argument on return-type parsers or chained.
    # For unnamed (return-based) parsers, attribute calls are harder to track;
    # we do best-effort by looking for any add_argument calls whose receiver
    # is not tracked.

    return parsers


def _pick_main_parser(parsers: list[_ParserNode]) -> tuple[_ParserNode | None, bool]:
    """Pick the main parser (most add_argument calls).

    Returns (parser_node, is_ambiguous).  ``is_ambiguous`` is True iff there
    are ≥2 parsers tied for the maximum count.
    """
    if not parsers:
        return None, False
    max_count = max(p.add_argument_count for p in parsers)
    candidates = [p for p in parsers if p.add_argument_count == max_count]
    if len(candidates) > 1:
        return candidates[0], True
    return candidates[0], False


# ---------------------------------------------------------------------------
# Surface builder
# ---------------------------------------------------------------------------


def _build_surface(binary: str, module_path: Path, main_pn: _ParserNode) -> ParserSurface:
    """Build a ParserSurface from a _ParserNode."""
    required_flags: set[str] = set()
    optional_flags: set[str] = set()

    for flags, req in main_pn.flags_required:
        for flag in flags:
            if req:
                required_flags.add(flag)
            else:
                optional_flags.add(flag)

    # Subcommands
    subcommands: dict[str, ParserSurface] = {}
    for choice_name, choice_flags in main_pn.subparser_choices.items():
        sub_required: set[str] = set()
        sub_optional: set[str] = set()
        for flags, req in choice_flags:
            for flag in flags:
                if req:
                    sub_required.add(flag)
                else:
                    sub_optional.add(flag)
        subcommands[choice_name] = ParserSurface(
            binary=binary,
            module_path=module_path,
            required_flags=sub_required,
            optional_flags=sub_optional,
            extraction_status="ok",
        )

    return ParserSurface(
        binary=binary,
        module_path=module_path,
        required_flags=required_flags,
        optional_flags=optional_flags,
        subcommands=subcommands,
        extraction_status="ok",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_surface(
    root: Path | None = None,
) -> tuple[dict[str, ParserSurface], list[ExtractionError]]:
    """Extract the argparse surface for all ``cortex-*`` console scripts.

    Reads ``[project.scripts]`` from ``pyproject.toml`` at ``root``,
    resolves each entry to a source path via ``importlib.util.find_spec``,
    parses with ``ast``, and returns a mapping of binary name → ParserSurface.

    Returns:
        (surface_map, extraction_errors)
        ``surface_map`` contains entries for all scripts, including those with
        ``extraction_status != "ok"``.  ``extraction_errors`` lists E201/E202
        errors for diagnostics.
    """
    if root is None:
        root = Path.cwd()
    root = root.resolve()

    pyproject = root / "pyproject.toml"
    scripts = _load_project_scripts(pyproject)

    surface_map: dict[str, ParserSurface] = {}
    errors: list[ExtractionError] = []

    for binary, module_attr in sorted(scripts.items()):
        if not binary.startswith("cortex-"):
            continue

        # Resolve to source path
        module_path = _resolve_module_path(module_attr)
        if module_path is None:
            # Can't resolve — treat as not_argparse without emitting E201
            # (the module may not be importlib-visible, e.g. wrong venv).
            placeholder_path = root / "cortex_command" / "_unresolved.py"
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=placeholder_path,
                extraction_status="not_argparse",
            )
            continue

        # Read and parse source
        try:
            source = module_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(ExtractionError(
                binary=binary,
                code="E201",
                message=f"cannot AST-parse module source for {binary} at path {module_path}: {exc}",
            ))
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="ast_error",
            )
            continue

        try:
            tree = ast.parse(source, filename=str(module_path))
        except SyntaxError as exc:
            errors.append(ExtractionError(
                binary=binary,
                code="E201",
                message=f"cannot AST-parse module source for {binary} at path {module_path}: {exc}",
            ))
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="ast_error",
            )
            continue

        # Walk for parser nodes
        parser_nodes = _collect_parser_nodes(tree)

        if not parser_nodes:
            # No ArgumentParser found — module uses different argv handling.
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="not_argparse",
            )
            continue

        main_pn, is_ambiguous = _pick_main_parser(parser_nodes)

        if is_ambiguous:
            errors.append(ExtractionError(
                binary=binary,
                code="E202",
                message=f"ambiguous main parser for {binary} (tied add_argument counts)",
            ))
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="ambiguous",
            )
            continue

        assert main_pn is not None
        surface = _build_surface(binary, module_path, main_pn)
        surface_map[binary] = surface

    return surface_map, errors


# ---------------------------------------------------------------------------
# Convenience wrapper (for backwards compat with the spec's single-return form)
# ---------------------------------------------------------------------------


def extract_surface_map(root: Path | None = None) -> dict[str, ParserSurface]:
    """Return only the surface map (discards extraction errors).

    Convenience wrapper used by tests and callers that don't need to inspect
    individual extraction errors.
    """
    surface_map, _errors = extract_surface(root)
    return surface_map


# ---------------------------------------------------------------------------
# CLI (minimal for this task — subsequent tasks add scanner/validator/output)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse as _argparse
    import json as _json

    p = _argparse.ArgumentParser(
        prog="cortex-check-contract",
        description="Skill-prose to CLI argparse contract lint",
    )
    p.add_argument("--root", default=None, help="Repository root (default: cwd)")
    p.add_argument("--json", dest="as_json", action="store_true",
                   help="Emit JSON output")
    p.add_argument("--self-test", action="store_true",
                   help="Run inline self-test fixtures and exit")
    p.add_argument("--staged", action="store_true",
                   help="Operate on git staged diff")
    p.add_argument("--audit", action="store_true",
                   help="Operate on the full repo corpus")
    p.add_argument("--validate-exceptions", action="store_true",
                   help="Validate the exception ledger and exit")

    args = p.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
    surface_map, extraction_errors = extract_surface(root)

    if args.as_json:
        payload = {
            binary: {
                "status": s.extraction_status,
                "required_flags": sorted(s.required_flags),
                "optional_flags": sorted(s.optional_flags),
                "subcommands": sorted(s.subcommands.keys()),
            }
            for binary, s in sorted(surface_map.items())
        }
        print(_json.dumps(payload))
    else:
        for err in extraction_errors:
            print(err.format_text(), file=sys.stderr)
        ok = sum(1 for s in surface_map.values() if s.extraction_status == "ok")
        total = len(surface_map)
        print(f"Extracted {ok}/{total} argparse surfaces")

    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    """Run inline self-test fixtures; return 0 on pass, 1 on fail."""
    failures: list[str] = []

    # Fixture 1: fenced code invocation must be validated (not skipped).
    # Fixture 2: inline-code invocation must be validated.
    # Fixture 3: prose mention must be skipped.
    # (Full scanner not in this task; this self-test covers extract_surface basics.)

    # Basic extraction self-test: create a minimal in-memory AST and verify
    # that _collect_parser_nodes and _build_surface work correctly.
    import textwrap

    sample_source = textwrap.dedent("""
        import argparse
        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("--status", required=True)
            parser.add_argument("--type", required=True)
            parser.add_argument("--title", required=True)
            parser.add_argument("--priority", default="low")
    """)

    try:
        tree = ast.parse(sample_source)
    except SyntaxError as exc:
        failures.append(f"self-test sample parse failed: {exc}")
    else:
        pnodes = _collect_parser_nodes(tree)
        if not pnodes:
            failures.append("self-test: no parser nodes found in sample")
        else:
            main_pn, ambiguous = _pick_main_parser(pnodes)
            if ambiguous:
                failures.append("self-test: unexpected ambiguity in sample parser")
            elif main_pn is None:
                failures.append("self-test: main_pn is None for sample")
            else:
                surf = _build_surface("cortex-test", Path("/dev/null"), main_pn)
                if "--status" not in surf.required_flags:
                    failures.append(f"self-test: --status not in required_flags: {surf.required_flags}")
                if "--type" not in surf.required_flags:
                    failures.append(f"self-test: --type not in required_flags: {surf.required_flags}")
                if "--title" not in surf.required_flags:
                    failures.append(f"self-test: --title not in required_flags: {surf.required_flags}")
                if "--priority" not in surf.optional_flags:
                    failures.append(f"self-test: --priority not in optional_flags: {surf.optional_flags}")

    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        return 1
    print("self-test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
