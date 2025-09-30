# fixer.py — compile-check + auto-insert headers (no AI)
# - Detects missing symbols from compiler diagnostics
# - Maps symbols→headers via tools/headers_map.json
# - Inserts needed #include lines safely (after existing includes or at file top)
# - Creates .bak backup before modifying
# - Falls back to inserting common headers if regex finds no symbols
# - Works with clang/gcc/msvc (cl)

import sys
import re
import json
import shutil
import subprocess
import pathlib

MAP_PATH = "tools/headers_map.json"

def detect_eol(text: str) -> str:
    """Preserve original line endings."""
    return "\r\n" if "\r\n" in text else "\n"

def insert_headers_safely(file_path: str, headers: list[str]) -> bool:
    """
    Insert missing #include lines.
    - De-duplicate (only insert if not already present)
    - Insert after the last existing #include; if none, insert at file top
    - Create .bak backup before writing
    Returns True if file changed, else False.
    """
    p = pathlib.Path(file_path).resolve()
    src = p.read_text(encoding="utf-8")
    eol = detect_eol(src)

    # Filter already-present includes
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

    insert_idx = last_inc + 1  # 0 => beginning
    new_lines = lines[:insert_idx] + to_insert + lines[insert_idx:]

    # If inserted at very top, add a blank line after the inserted block for readability
    if insert_idx == 0:
        new_lines.insert(len(to_insert), "")

    # Preserve trailing newline if original had one
    new_src = eol.join(new_lines)
    if src.endswith(("\n", "\r\n")) and not new_src.endswith(("\n", "\r\n")):
        new_src += eol

    if new_src == src:
        return False

    bak = p.with_suffix(p.suffix + ".bak")
    shutil.copy2(p, bak)

    p.write_text(new_src, encoding="utf-8")
    return True

def choose_compiler(src: str) -> list[str]:
    """
    Prefer clang; fall back to g++/gcc; then MSVC cl.
    Use syntax-only flags and set a modern standard for clearer diagnostics.
    """
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
        # MSVC: /Zs = syntax check only; add C++17 if needed.
        return ["cl", "/nologo", "/Zs"] + (["/std:c++17"] if is_cpp else []) + [src]
    print("❌ No compiler found (install clang/gcc/MSVC).")
    sys.exit(2)

def run_compile(cmd: list[str]) -> tuple[int, str]:
    """
    Run compiler; return (exit_code, diagnostics_string).
    Note: MSVC prints diagnostics to stdout; clang/gcc use stderr.
    """
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # Heuristic: when using cl, diagnostics usually in stdout
    if cmd and pathlib.Path(cmd[0]).name.lower().startswith("cl"):
        diag = proc.stdout
    else:
        diag = proc.stderr
    return proc.returncode, diag

def parse_missing_symbols(diag: str) -> set[str]:
    """
    Extract likely-missing symbols from GCC/Clang/MSVC diagnostics.
    Covers common wordings (with straight/curly quotes).
    """
    syms = set()
    patterns = [
        # GCC/Clang C:
        r"implicit declaration of function '([A-Za-z_]\w*)'",
        r"implicit declaration of function “([A-Za-z_]\w*)”",

        # C/C++ common:
        r"'([A-Za-z_]\w*)' was not declared in this scope",
        r"‘([A-Za-z_]\w*)’ was not declared in this scope",
        r"use of undeclared identifier '([A-Za-z_]\w*)'",
        r"use of undeclared identifier “([A-Za-z_]\w*)”",
        r"unknown type name '([A-Za-z_]\w*)'",
        r"unknown type name “([A-Za-z_]\w*)”",

        # MSVC:
        r"identifier '([A-Za-z_]\w*)' is undefined",
        r"type name '([A-Za-z_]\w*)' is undefined",

        # Sometimes compilers omit quotes:
        r"\b([A-Za-z_]\w*)\b was not declared in this scope",

        # C++ std member hints (not always a header issue, but useful):
        r"no member named '([A-Za-z_]\w*)' in namespace 'std'",
    ]

    for line in diag.splitlines():
        for pat in patterns:
            m = re.search(pat, line)
            if m:
                syms.add(m.group(1))
    return syms

def load_map() -> dict:
    try:
        with open(MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Mapping file not found: {MAP_PATH}")
        print("   Create it or adjust MAP_PATH.")
        sys.exit(2)

def headers_for_symbols(symbols: set[str], mapping: dict, is_cpp: bool) -> list[str]:
    """
    Collapse symbol→headers map into an ordered, de-duplicated header list.
    Keep mapping order; caller can choose C vs C++ preference in mapping content.
    """
    headers = []
    for s in symbols:
        headers += mapping.get(s, [])
    # de-duplicate, keep order
    seen = set()
    ordered = []
    for h in headers:
        if h not in seen:
            seen.add(h)
            ordered.append(h)
    return ordered

def fallback_headers(is_cpp: bool) -> list[str]:
    """Single-shot safe fallback set when we couldn't parse symbols."""
    if is_cpp:
        return ["<cstdio>", "<cassert>", "<cstdint>", "<cstring>"]
    return ["<stdio.h>", "<assert.h>", "<stdint.h>", "<string.h>", "<stddef.h>", "<stdbool.h>"]

def main():
    if len(sys.argv) != 2:
        print("Usage: python fixer.py <file.c|cpp>")
        sys.exit(1)

    src = sys.argv[1]
    p = pathlib.Path(src).resolve()
    if not p.exists():
        print(f"❌ File not found: {p}")
        sys.exit(2)

    is_cpp = p.suffix.lower() in (".cpp", ".cc", ".cxx")
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
        hdrs = headers_for_symbols(missing, mapping, is_cpp)
        if not hdrs:
            print("ℹ️ No headers found in mapping for the missing symbols.")
        else:
            print("➕ Inserting headers:", ", ".join(hdrs))
            changed = insert_headers_safely(str(p), hdrs)
            if changed:
                print("💾 File updated (backup created).")
            else:
                print("ℹ️ Headers already present. Will re-check compilation.")

            code2, diag2 = run_compile(cmd)
            if code2 == 0:
                print("✅ Fixed compilation passed!")
                return
            else:
                print("❌ Still failing after mapped headers. Compiler output:\n" + diag2)
                # Fall through to fallback attempt (once)
    else:
        print("ℹ️ No missing symbol detected by regex.")

    # Fallback attempt (single shot)
    fb = fallback_headers(is_cpp)
    print("🛟 Trying fallback headers once:", ", ".join(fb))
    changed_fb = insert_headers_safely(str(p), fb)
    if changed_fb:
        print("💾 File updated (fallback; backup created).")
    else:
        print("ℹ️ Fallback headers already present.")

    code3, diag3 = run_compile(cmd)
    if code3 == 0:
        print("✅ Compilation passed after fallback headers.")
        return
    else:
        print("❌ Still failing after fallback.\nCompiler output:\n" + diag3)
        sys.exit(5)

if __name__ == "__main__":
    main()


