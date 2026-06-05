# AlgoScope

**AlgoScope: A web-based Runtime Complexity and Resource Visualizer for Students**

AlgoScope runs a Python program across multiple input sizes, measures process-level resource behavior, and shows an educational React dashboard with charts and an estimated Big O growth pattern.

It is designed as an Operating Systems final project demo: instead of only discussing Big O formulas, it shows how real programs consume wall time, CPU time, memory, and system calls under Linux.

## Features

- Provides a React + FastAPI web demo for submitted Python programs.
- Runs the target program as a separate process for each input size.
- Measures wall time, user CPU time, system CPU time, and peak RSS via `/usr/bin/time`.
- Falls back to `os.wait4` resource accounting on systems where `/usr/bin/time -v` is unavailable.
- Measures syscall counts and top syscalls with `strace -c` when available.
- Fits observed runtime against `O(1)`, `O(log n)`, `O(n)`, `O(n log n)`, and `O(n^2)`.
- Produces a CLI table, JSON data, and an HTML report with SVG charts.
- Optionally generates an OS-focused LLM summary with GitHub Copilot SDK.
- Includes demo programs for linear search, bubble sort, Python sort, and I/O-heavy workloads.
- Includes a comparison report showing two O(n) programs with different OS behavior.
- Supports a Docker runner image for sandboxed demo execution, with a local development runner fallback when Docker is unavailable.

## Project Structure

- `analyzer.py`: compatibility CLI entrypoint.
- `main.py`: uv-friendly CLI entrypoint.
- `algoscope/cli.py`: argument parsing and application workflow.
- `algoscope/api.py`: FastAPI app for the web demo.
- `algoscope/service.py`: web-first analysis workflow returning structured JSON.
- `algoscope/sandbox.py`: Docker and local development runners with timeout and memory limits.
- `algoscope/web_models.py`: web-facing request/result contracts.
- `algoscope/comparison.py`: built-in comparison workflows.
- `algoscope/probes.py`: OS probes for process timing, memory usage, and `strace` syscall summaries.
- `algoscope/complexity.py`: Big O model fitting.
- `algoscope/report.py`: JSON and HTML report generation.
- `algoscope/summary.py`: optional GitHub Copilot SDK summary generation focused on OS observability.
- `algoscope/models.py`: shared typed data objects.
- `frontend/`: React + Vite analysis dashboard.
- `docker/runner.Dockerfile`: Python runner image with `time` and `strace`.
- `examples/`: built-in workload demos.

## Web Demo Quick Start

Install Python dependencies:

```bash
uv sync
```

Start the FastAPI backend:

```bash
uv run algoscope-api
```

In another terminal, start the React app:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The frontend proxies `/api` requests to the backend at `http://127.0.0.1:8000`.

### Docker Runner

For sandboxed execution, build the runner image:

```bash
docker build -f docker/runner.Dockerfile -t algoscope-runner:latest .
```

Then choose `Docker` in the web UI runner selector, or send `"runner": "docker"` to `POST /api/analyses`.

If Docker is not installed, `runner: auto` falls back to the local development runner. Local mode is useful for a quick demo on a trusted machine, but it should not be used for untrusted public submissions.

Submitted code is staged under `.algoscope-runs/` before execution. This keeps Docker bind mounts inside the project tree, which is required by some Docker installations such as snap Docker. The directory is ignored by git and cleaned up after each run.

### API Shape

Create an analysis:

```bash
curl -X POST http://127.0.0.1:8000/api/analyses \
  -H 'content-type: application/json' \
  -d '{"code":"import sys\nn=int(sys.argv[1])\nprint(sum(range(n)))\n","sizes":[1000,2000,4000],"repeats":1,"syscalls":"off","llm_summary":"off","runner":"local"}'
```

Poll the returned job:

```bash
curl http://127.0.0.1:8000/api/analyses/<job_id>
```

Job status is separate from measurement status. A job can complete while individual input sizes are marked `timeout_killed`, `memory_killed`, `runtime_error`, or `probe_failed`.

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

## OS Behavior Comparison

Generate the pitch-focused comparison report:

```bash
uv run algoscope --comparison same-on
```

This runs two O(n) programs:

- `examples/cpu_loop.py`: CPU-bound user-space arithmetic.
- `examples/file_writer.py`: I/O-bound file creation and writes.

The report compares user time, system time, memory usage, syscall count, and top syscalls to show that programs with the same Big O can have very different Linux runtime behavior.

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
