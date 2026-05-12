# Repository Guidelines

## Project Overview

AlgoScope is a Python CLI package for measuring runtime complexity and OS-level resource behavior. It runs target Python programs across input sizes, collects timing, memory, and optional syscall data, estimates an observed Big O fit, and writes JSON plus static HTML reports.

## Structure

- `algoscope/cli.py`: CLI argument parsing and application workflow.
- `algoscope/probes.py`: process timing, memory, and syscall probes.
- `algoscope/complexity.py`: observed Big O model fitting.
- `algoscope/report.py`: JSON and static HTML report generation.
- `algoscope/models.py`: shared dataclasses.
- `algoscope/config.py`: built-in demo case configuration.
- `examples/`: demo workloads.
- `analyzer.py`: compatibility CLI entrypoint.
- `main.py`: uv-friendly CLI entrypoint.
- `reports/`: generated demo reports and JSON data.

## Common Commands

Run a built-in demo:

```bash
python3 analyzer.py --case bubble_sort
```

Run a smaller smoke test:

```bash
python3 analyzer.py --case bubble_sort --sizes 10 20 --repeats 1 --syscalls off
```

Analyze a custom program:

```bash
python3 analyzer.py --program path/to/target.py --sizes 100 500 1000
```

Compile-check the Python files:

```bash
python3 -m compileall algoscope examples analyzer.py main.py
```

## Environment Notes

- The project targets Python 3.12 or newer.
- `strace` is optional and mostly Linux-specific. Use `--syscalls off` for portable smoke tests, especially on macOS.
- `/usr/bin/time` is used when available; otherwise probes fall back to `os.wait4`.
- Running the CLI writes or updates files under `reports/`.

## Development Conventions

- Keep implementation dependencies minimal; `pyproject.toml` currently declares no runtime dependencies.
- Prefer focused changes that follow the existing plain-Python module layout.
- Do not assume generated reports are disposable unless the user asks for cleanup.
- Preserve the target-program contract: analyzed programs accept the input size as `argv[1]`.
- When changing probe parsing or report output, run at least the smoke test and `compileall`.

## Git State

At initialization, the repository contents were untracked. Treat existing files as user-created state and avoid reverting or deleting them unless explicitly requested.
