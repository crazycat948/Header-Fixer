#!/usr/bin/env python3
# fixer.py — C/C++/Python test fixer (no AI)
# - C/C++ (.c/.cpp): compile-check, detect missing symbols, insert headers, re-check
# - Header (.h): self-containment check via temp TU; insert headers into the header file
# - Python (.py): static import completion via __python__ map, then py_compile
# - English logs, .bak backup, safe insertion, script-dir based mapping path

import sys
import os
import re
import json
import shutil
import subprocess
import pathlib

# -------------- Generic utils --------------
def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"

def insert_headers_safely(file_path: str, headers: list[str]) -> bool:
    """
    Insert missing #include lines into a C/C++ source or header file.
    - De-duplicate
    - Insert after the last existing #include; if none, at the very top (with a blank line)
    - Create .bak backup before writing
    """
    p = pathlib.Path(file_path).resolve()
    src = p.read_text(encoding="utf-8")
    eol = detect_eol(src)

    to_insert = []
    for h in headers:
        line = f"#include {h}"
        if line not in src:
            to_insert.append(line)
    if not to_insert:
        return False

    lines = src.splitlines()
    inc_re = re.compile(r'^\s*#\s*include\s+[<"].+[>"]\s*$')
    last_inc = -1
    for i, line in enumerate(lines):
        if inc_re.match(line):
            last_inc = i

    insert_idx = last_inc + 1
    new_lines = lines[:insert_idx] + to_insert + lines[insert_idx:]

    if insert_idx == 0:
        new_lines.insert(len(to_insert), "")

    new_src = detect_eol(src).join(new_lines)
    if src.endswith(("\n", "\r\n")) and not new_src.endswith(("\n", "\r\n")):
        new_src += eol

    if new_src == src:
        return False

    bak = p.with_suffix(p.suffix + ".bak")
    shutil.copy2(p, bak)
    p.write_text(new_src, encoding="utf-8")
    return True

def choose_compiler(src: str) -> list[str]:
    """Prefer clang; then g++/gcc; then MSVC cl. Use syntax-only & modern std."""
    is_cpp = src.lower().endswith((".cpp", ".cc", ".cxx"))
    if shutil.which("clang++") and is_cpp:
        return ["clang++", "-std=c++17", "-fsyntax-only", src]
    if shutil.which("clang") and not is_cpp:
        return ["clang", "-std=c17", "-fsyntax-only", src]
    if shutil.which("g++") and is_cpp:
        return ["g++", "-std=c++17", "-fsyntax-only", src]
    if shutil.which("gcc") and not is_cpp:
        return ["gcc", "-std=c17", "-fsyntax-only", src]
    if shutil.which("cl"):
        return ["cl", "/nologo", "/Zs"] + (["/std:c++17"] if is_cpp else []) + [src]
    print("❌ No compiler found (install clang/gcc/MSVC).")
    sys.exit(2)

def run_compile(cmd: list[str]) -> tuple[int, str]:
    """Return (exit_code, diagnostics_string). cl prints to stdout; others to stderr."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    diag = proc.stdout if pathlib.Path(cmd[0]).name.lower().startswith("cl") else proc.stderr
    return proc.returncode, diag

def parse_missing_symbols(diag: str) -> set[str]:
    """Extract likely-missing identifiers from diagnostics across clang/gcc/msvc."""
    syms = set()
    patterns = [
        r"implicit declaration of function '([A-Za-z_]\w*)'",
        r"implicit declaration of function “([A-Za-z_]\w*)”",
        r"'([A-Za-z_]\w*)' was not declared in this scope",
        r"‘([A-Za-z_]\w*)’ was not declared in this scope",
        r"use of undeclared identifier '([A-Za-z_]\w*)'",
        r"use of undeclared identifier “([A-Za-z_]\w*)”",
        r"unknown type name '([A-Za-z_]\w*)'",
        r"unknown type name “([A-Za-z_]\w*)”",
        r"identifier '([A-Za-z_]\w*)' is undefined",
        r"type name '([A-Za-z_]\w*)' is undefined",
        r"\b([A-Za-z_]\w*)\b was not declared in this scope",
        r"no member named '([A-Za-z_]\w*)' in namespace 'std'",
    ]
    for line in diag.splitlines():
        for pat in patterns:
            m = re.search(pat, line)
            if m:
                syms.add(m.group(1))
    return syms

def load_map() -> dict:
    """Load tools/headers_map.json relative to this fixer.py file."""
    script_dir = pathlib.Path(__file__).resolve().parent
    map_path = script_dir / "tools" / "headers_map.json"
    print(f"🔎 Loading mapping from: {map_path}")
    if not map_path.exists():
        print("❌ Mapping file not found. Expected at:", map_path)
        sys.exit(2)
    try:
        with map_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print("❌ JSON decode error in headers_map.json:", e)
        sys.exit(2)
    if not isinstance(data, dict):
        print("❌ Mapping must be a JSON object (symbol → [headers]).")
        sys.exit(2)
    return data

def headers_for_symbols(symbols: set[str], mapping: dict, is_cpp: bool) -> list[str]:
    """Collapse symbol→headers and de-duplicate while preserving order."""
    headers = []
    for s in symbols:
        headers += mapping.get(s, [])
    seen, ordered = set(), []
    for h in headers:
        if h not in seen:
            seen.add(h)
            ordered.append(h)
    return ordered

def fallback_headers(is_cpp: bool) -> list[str]:
    """One-shot safe fallback when regex found no symbols or mapping empty."""
    return ["<cstdio>", "<cassert>", "<cstdint>", "<cstring>"] if is_cpp \
           else ["<stdio.h>", "<assert.h>", "<stdint.h>", "<string.h>", "<stddef.h>", "<stdbool.h>"]

# -------------- Python helpers --------------
def py_syntax_check(py_path: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-m", "py_compile", py_path],
                          capture_output=True, text=True)
    diag = (proc.stderr or "") + (proc.stdout or "")
    return proc.returncode, diag

def py_parse_existing_imports(src: str) -> set[str]:
    imported = set()
    for line in src.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("import "):
            body = line[len("import "):]
            parts = [p.strip() for p in body.split(",")]
            for p in parts:
                if " as " in p:
                    mod, alias = [x.strip() for x in p.split(" as ", 1)]
                    imported.add(mod.split(".")[0])
                    imported.add(alias)
                else:
                    imported.add(p.split(".")[0])
        elif line.startswith("from "):
            try:
                after_from = line[len("from "):]
                mod, after_mod = after_from.split(" import ", 1)
                imported.add(mod.split(".")[0])
                members = [m.strip() for m in after_mod.split(",")]
                for m in members:
                    if " as " in m:
                        name, alias = [x.strip() for x in m.split(" as ", 1)]
                        imported.add(name)
                        imported.add(alias)
                    else:
                        imported.add(m)
            except ValueError:
                pass
    return imported

def py_required_import_lines(src: str, py_map: dict) -> list[str]:
    needed = []
    imported = py_parse_existing_imports(src)

    for key, import_lines in py_map.items():
        essential_names = []
        for line in import_lines:
            s = line.strip()
            if s.startswith("import "):
                body = s[len("import "):].strip()
                name = body.split(" as ")[-1].strip() if " as " in body else body
                essential_names.append(name.split(".")[0])
            elif s.startswith("from "):
                try:
                    after_from = s[len("from "):]
                    mod, after_mod = after_from.split(" import ", 1)
                    essential_names.append(mod.split(".")[0])
                    for m in [m.strip() for m in after_mod.split(",")]:
                        essential_names.append((m.split(" as ")[-1]).strip())
                except ValueError:
                    pass

        already_have = any(n in imported for n in essential_names)
        if already_have:
            continue

        if re.search(rf"\b{re.escape(key)}\b", src):
            needed.extend(import_lines)

    seen, ordered = set(), []
    for ln in needed:
        if ln not in seen:
            seen.add(ln)
            ordered.append(ln)
    return ordered

def ensure_py_import(py_path: str, module: str) -> bool:
    p = pathlib.Path(py_path).resolve()
    src = p.read_text(encoding="utf-8")
    line = f"import {module}"
    if re.search(rf"^\s*import\s+{re.escape(module)}\b", src, re.M):
        return False
    lines = src.splitlines()
    insert_idx = 1 if (lines and lines[0].startswith("#!")) else 0
    lines[insert_idx:insert_idx] = [line, ""]
    bak = p.with_suffix(p.suffix + ".bak")
    shutil.copy2(p, bak)
    p.write_text("\n".join(lines) + ("\n" if src.endswith("\n") else ""), encoding="utf-8")
    return True

def handle_python(py_path: str):
    print("🐍 Checking Python test…")
    p = pathlib.Path(py_path).resolve()
    src = p.read_text(encoding="utf-8")

    mapping = load_map()
    py_map = mapping.get("__python__", {})

    missing_import_lines = py_required_import_lines(src, py_map)
    if missing_import_lines:
        print("➕ Inserting missing Python imports:", ", ".join(missing_import_lines))
        lines = src.splitlines()
        insert_idx = 1 if (lines and lines[0].startswith("#!")) else 0
        new_lines = lines[:insert_idx] + missing_import_lines + [""] + lines[insert_idx:]
        bak = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, bak)
        p.write_text("\n".join(new_lines) + ("\n" if src.endswith("\n") else ""), encoding="utf-8")
        src = p.read_text(encoding="utf-8")

    code, diag = py_syntax_check(str(p))
    if code == 0:
        print("✅ Python syntax OK.")
        return

    print("⚠️ Python compile failed. Diagnostics:")
    print(diag)

    uses_unittest = bool(re.search(r"\bunittest\b|\bTestCase\b", src))
    has_unittest_import = bool(re.search(r"^\s*import\s+unittest\b", src, re.M))
    if uses_unittest and not has_unittest_import:
        changed = ensure_py_import(str(p), "unittest")
        if changed:
            print("🛟 Fallback: inserted 'import unittest'. Rechecking…")
            code2, diag2 = py_syntax_check(str(p))
            if code2 == 0:
                print("✅ Python fixed after fallback.")
                return
            else:
                print("❌ Still failing after fallback:\n" + diag2)
                sys.exit(5)

    sys.exit(5)

# -------------- Header (.h) handler --------------
def handle_header(header_path: str, mapping: dict):
    print("📄 Checking header self-containment…")
    header = pathlib.Path(header_path).resolve()
    tmp = header.with_suffix(".selfcheck.cpp")
    tmp.write_text(f'#include "{header.name}"\nint main(){{return 0;}}\n', encoding="utf-8")
    try:
        cmd = choose_compiler(str(tmp))
        print("🔧 Compiler command:", " ".join(cmd))
        code, diag = run_compile(cmd)
        if code == 0:
            print("✅ Header is self-contained. No fix needed.")
            return
        print("⚠️ Self-check failed, analyzing missing symbols…")
        missing = parse_missing_symbols(diag)
        if not missing:
            hdrs = fallback_headers(is_cpp=True)
        else:
            hdrs = headers_for_symbols(missing, mapping, is_cpp=True) or fallback_headers(is_cpp=True)
        print("➕ Inserting headers into the header file:", ", ".join(hdrs))
        changed = insert_headers_safely(str(header), hdrs)
        print("💾 Header updated (backup created)." if changed else "ℹ️ Headers already present. Rechecking…")
        code2, diag2 = run_compile(cmd)
        if code2 == 0:
            print("✅ Header fixed. Self-check passed.")
        else:
            print("❌ Still failing for header. Diagnostics:\n" + diag2)
            sys.exit(5)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

# -------------- Dispatcher --------------
def main():
    if len(sys.argv) != 2:
        print("Usage: python fixer.py <file.cpp|file.h|file.py>")
        sys.exit(1)

    src = sys.argv[1]
    p = pathlib.Path(src).resolve()
    if not p.exists():
        print(f"❌ File not found: {p}")
        sys.exit(2)

    ext = p.suffix.lower()

    if ext in (".cpp", ".cc", ".cxx", ".c"):
        mapping = load_map()
        cmd = choose_compiler(str(p))
        print("🔧 Compiler command:", " ".join(cmd))
        code, diag = run_compile(cmd)
        if code == 0:
            print("✅ Initial compilation passed, no fix needed.")
            return
        print("⚠️ Compilation failed, analyzing missing symbols…")
        missing = parse_missing_symbols(diag)
        if missing:
            print("🧩 Missing symbols:", ", ".join(sorted(missing)))
            hdrs = headers_for_symbols(missing, mapping, is_cpp=(ext != ".c"))
            if hdrs:
                print("➕ Inserting headers:", ", ".join(hdrs))
                changed = insert_headers_safely(str(p), hdrs)
                if changed:
                    print("💾 File updated (backup created).")
            code2, diag2 = run_compile(cmd)
            if code2 == 0:
                print("✅ Fixed compilation passed!")
                return
            else:
                print("❌ Still failing after mapped headers. Diagnostics:\n" + diag2)
        else:
            print("ℹ️ No missing symbol detected by regex.")

        fb = fallback_headers(is_cpp=(ext != ".c"))
        print("🛟 Trying fallback headers once:", ", ".join(fb))
        changed_fb = insert_headers_safely(str(p), fb)
        if changed_fb:
            print("💾 File updated (fallback; backup created).")
        code3, diag3 = run_compile(cmd)
        if code3 == 0:
            print("✅ Compilation passed after fallback headers.")
            return
        print("❌ Still failing after fallback.\nCompiler output:\n" + diag3)
        sys.exit(5)

    elif ext == ".h":
        mapping = load_map()
        handle_header(str(p), mapping)

    elif ext == ".py":
        handle_python(str(p))

    else:
        print(f"❌ Unsupported file type: {ext}")
        sys.exit(2)

if __name__ == "__main__":
    main()


