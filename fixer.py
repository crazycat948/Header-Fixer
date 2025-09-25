# fixer.py (v3 - safer insert)
import sys, re, pathlib, shutil

def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"

def ensure_include(file_path: str, header: str = "<cstdio>"):
    p = pathlib.Path(file_path).resolve()
    print(f"[INFO] Target file: {p}")
    if not p.exists():
        print("[ERR] File not found.")
        sys.exit(2)

    src = p.read_text(encoding="utf-8")
    eol = detect_eol(src)

    include_line = f"#include {header}"
    if include_line in src:
        print(f"[OK] {include_line} already present. No change.")
        return

    # 按行切分，保留内容；插入点=最后一个 #include 之后，否则文件开头
    lines = src.splitlines()
    inc_re = re.compile(r'^\s*#\s*include\s+[<"].+[>"]\s*$')
    last_inc = -1
    for i, line in enumerate(lines):
        if inc_re.match(line):
            last_inc = i

    insert_idx = last_inc + 1  # 0 表示最前面
    new_lines = lines.copy()

    # 在 insert_idx 位置插入 include_line
    new_lines[insert_idx:insert_idx] = [include_line]

    # 如果是插在最前面，加一个空行美观（不影响原内容）
    if insert_idx == 0 and (len(new_lines) < 2 or new_lines[1].strip() != ""):
        new_lines.insert(1, "")  # 空行

    new_src = eol.join(new_lines) + (eol if src.endswith(("\n", "\r\n")) else "")

    if new_src == src:
        print("[INFO] No effective diff; skip writing.")
        return

    # 先备份
    bak = p.with_suffix(p.suffix + ".bak")
    shutil.copy2(p, bak)
    print(f"[INFO] Backup written: {bak}")

    # 写回
    p.write_text(new_src, encoding="utf-8")
    print(f"[DONE] Inserted {include_line}")

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print('Usage: python fixer.py <file.cpp> ["<header>"]')
        print('Example: python fixer.py .\\test.cpp "<stdio.h>"')
        sys.exit(1)
    file_path = sys.argv[1]
    header = sys.argv[2] if len(sys.argv) == 3 else "<cstdio>"
    ensure_include(file_path, header)

