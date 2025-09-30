# 🛠️ Header Fixer

A demo tool that automatically fixes missing header files in C/C++ test files.  
The goal is to ensure that **AI-generated or incomplete test files always compile successfully** by analyzing compiler errors and inserting the required `#include` directives.

---

## ✨ Features
- Runs a dry-run compilation (`clang`, `gcc/g++`, or MSVC `cl`) with syntax-only mode
- Parses compiler diagnostics to detect missing symbols (e.g., `printf`, `assert`, `uint32_t`)
- Maps symbols → headers using a configurable JSON file (`headers_map.json`)
- Automatically inserts missing `#include` lines at the top of the file
- Creates a `.bak` backup before making changes
- Recompiles to verify that the fix worked
- Provides a fallback mechanism (adds common headers if no symbols were detected)

---

## Project Structure
Header-Fixer/
├─ tools/
│ └─ headers_map.json # symbol → header mapping
├─ fixer.py # main script
├─ sample/
│ └─ test.cpp # example file (intentionally missing headers)
└─ README.md

yaml
Copy code

---

## 🚀 Usage

1. Put a `.c` or `.cpp` file in your project (for example `sample/test.cpp`):

```cpp
int main() {
    printf("Hello World\n");
    return 0;
}
Run the fixer:

bash
Copy code
python fixer.py sample/test.cpp
Output example:

bash
Copy code
Compiler command: g++ -std=c++17 -fsyntax-only sample/test.cpp
Compilation failed, analyzing missing symbols…
Missing symbols: printf
Inserting headers: <stdio.h>
File updated (backup created).
Fixed compilation passed!
The file is automatically modified:

cpp
Copy code
#include <stdio.h>

int main() {
    printf("Hello World\n");
    return 0;
}
⚙️ Configuration
The mapping of symbols → headers is stored in tools/headers_map.json.
Example:

json
Copy code
{
  "printf": ["<stdio.h>"],
  "assert": ["<assert.h>"],
  "uint32_t": ["<stdint.h>"],
  "memcpy": ["<string.h>"]
}
You can expand this file as needed for your project.

 Purpose
This tool is a proof of concept (MVP) for automatically repairing AI-generated unit tests.
While this version only inserts missing headers, the idea can be extended with:

Recursive fixing of compiler errors

Merging multiple test files

Integration with OpenAI or other LLMs for more complex code repairs