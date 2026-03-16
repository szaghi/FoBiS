# JSON Output

The `--json` flag makes `fobis build`, `fobis clean`, and `fobis fetch` emit a single JSON object to **stdout** instead of human-readable progress messages. This is useful for scripting, CI pipelines, and AI agent workflows that need to parse the result programmatically.

## Usage

```bash
fobis build --json
fobis clean --json
fobis fetch --json
```

`--json` can be combined with any other option:

```bash
fobis build --fobos project.fobos --mode release --json
fobis clean --fobos project.fobos --json
fobis fetch --update --json
```

## Schemas

### `fobis build --json`

```json
{
  "status": "ok",
  "target": "all",
  "objects_compiled": 3,
  "errors": []
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` \| `"error"` | Whether the build succeeded |
| `target` | `string` | The `--target` value, or `"all"` when building all programs |
| `objects_compiled` | `integer` | Number of `.o` files newly written in this run |
| `errors` | `string[]` | Compiler error lines and any warning messages emitted during the build |

### `fobis clean --json`

```json
{
  "status": "ok",
  "removed": [
    "build/obj/main.o",
    "build/mod/mymodule.mod"
  ],
  "errors": []
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` \| `"error"` | Whether the clean succeeded |
| `removed` | `string[]` | Paths of `.o`, `.mod`, and `.smod` files that were deleted |
| `errors` | `string[]` | Any warning messages emitted during the clean |

### `fobis fetch --json`

```json
{
  "status": "ok",
  "deps_dir": ".fobis_deps",
  "dependencies": [
    { "name": "penf",    "path": ".fobis_deps/penf",    "use": "sources" },
    { "name": "jsonfort","path": ".fobis_deps/jsonfort", "use": "fobos"   }
  ],
  "errors": []
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` \| `"error"` | Whether all dependencies were fetched successfully |
| `deps_dir` | `string` | The directory where dependencies were cloned |
| `dependencies` | `object[]` | One entry per dependency (see below) |
| `errors` | `string[]` | Git error messages or build failures |

Each entry in `dependencies`:

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Dependency name (matches the fobos key) |
| `path` | `string` | Absolute path to the cloned directory |
| `use` | `"sources"` \| `"fobos"` | Integration mode |

## Exit codes

`--json` does not change the exit code behaviour:

- `0` on success — `"status": "ok"`
- `1` on failure — `"status": "error"`, `errors` contains the diagnostics

## Scripting example

Parse the JSON output with `jq`:

```bash
# Build and check status
result=$(fobis build --json)
status=$(echo "$result" | jq -r '.status')
if [ "$status" != "ok" ]; then
  echo "Build failed:"
  echo "$result" | jq -r '.errors[]'
  exit 1
fi
echo "Built $(echo "$result" | jq '.objects_compiled') object(s)"
```

Python example:

```python
import json
import subprocess

result = subprocess.run(
    ["fobis", "build", "--fobos", "fobos", "--json"],
    capture_output=True,
    text=True,
)
data = json.loads(result.stdout)
if data["status"] != "ok":
    raise RuntimeError("Build failed: " + "\n".join(data["errors"]))
print(f"Compiled {data['objects_compiled']} object(s)")
```

## Notes

- All human-readable output is suppressed when `--json` is active.
- Compiler diagnostics written to stderr are captured and included in the `errors` array.
- On build failure the JSON is still printed before FoBiS.py exits with code 1, so the calling process can always parse the output regardless of the exit code.
