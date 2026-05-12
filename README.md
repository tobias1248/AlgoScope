# AlgoScope

**AlgoScope: A Linux-based Runtime Complexity and Resource Visualizer for Students**

AlgoScope runs a Python program across multiple input sizes, measures process-level resource behavior, and generates an HTML report with charts and an estimated Big O growth pattern.

It is designed as an Operating Systems final project demo: instead of only discussing Big O formulas, it shows how real programs consume wall time, CPU time, memory, and system calls under Linux.

## Features

- Runs the target program as a separate process for each input size.
- Measures wall time, user CPU time, system CPU time, and peak RSS via `/usr/bin/time`.
- Falls back to `os.wait4` resource accounting on systems where `/usr/bin/time -v` is unavailable.
- Measures syscall counts and top syscalls with `strace -c` when available.
- Fits observed runtime against `O(1)`, `O(log n)`, `O(n)`, `O(n log n)`, and `O(n^2)`.
- Produces a CLI table, JSON data, and an HTML report with SVG charts.
- Optionally generates an OS-focused LLM summary with GitHub Copilot SDK.
- Includes demo programs for linear search, bubble sort, Python sort, and I/O-heavy workloads.

## Project Structure

- `analyzer.py`: compatibility CLI entrypoint.
- `main.py`: uv-friendly CLI entrypoint.
- `algoscope/cli.py`: argument parsing and application workflow.
- `algoscope/probes.py`: OS probes for process timing, memory usage, and `strace` syscall summaries.
- `algoscope/complexity.py`: Big O model fitting.
- `algoscope/report.py`: JSON and HTML report generation.
- `algoscope/summary.py`: optional GitHub Copilot SDK summary generation focused on OS observability.
- `algoscope/models.py`: shared typed data objects.
- `examples/`: built-in workload demos.

## Quick Start

```bash
python3 analyzer.py --case bubble_sort
```

Open the generated HTML report from the printed path, for example:

```text
reports/bubble_sort-report.html
```

A committed sample report is available at `docs/bubble_sort-report.html`.

To include an LLM-generated summary focused on OS monitoring:

```bash
uv run algoscope --case bubble_sort --llm-summary auto
```

`--llm-summary auto` records an unavailable note if Copilot authentication or networking is not available. Use `--llm-summary on` when you want the command to fail instead.

The LLM summary sends the report measurements, probe commands, platform metadata, and program name to GitHub Copilot. Do not enable it for private data unless that disclosure is acceptable.

## Built-in Demos

```bash
python3 analyzer.py --case linear_search
python3 analyzer.py --case bubble_sort
python3 analyzer.py --case python_sort
python3 analyzer.py --case io_heavy
```

You can override input sizes:

```bash
python3 analyzer.py --case bubble_sort --sizes 100 300 600 1000
```

## Analyze Your Own Python Program

The target program must accept the input size as its first command-line argument:

```bash
python3 analyzer.py --program path/to/target.py --sizes 100 500 1000 2000
```

Example target contract:

```python
import sys

n = int(sys.argv[1])
# run workload of size n
```

## Linux Setup

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 strace time
```

`strace` is optional. If it is missing, AlgoScope still generates timing and memory charts, while syscall fields show `n/a`. On macOS or restricted sandboxes, AlgoScope uses `os.wait4` as a fallback for CPU time and RSS, but the project is still designed around Linux observability tools.

## Presentation Note

AlgoScope estimates the closest observed growth pattern. It is not a formal proof of algorithmic complexity. The OS value comes from measuring actual process behavior: wall time, user time, system time, peak memory, and syscall activity.
