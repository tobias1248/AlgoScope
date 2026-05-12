"""Command-line workflow for AlgoScope."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from algoscope.complexity import ComplexityEstimator
from algoscope.config import DEMO_CASES, ROOT
from algoscope.models import Measurement
from algoscope.probes import MeasurementCollector
from algoscope.report import HtmlReportRenderer
from algoscope.summary import LlmSummaryService
from algoscope.utils import fmt_int, fmt_ms


class AlgoScopeApp:
    """Application service that wires probes, fitting, and report rendering."""

    def __init__(self) -> None:
        self.estimator = ComplexityEstimator()
        self.renderer = HtmlReportRenderer()

    def run(self, args: argparse.Namespace) -> int:
        program, sizes = self._resolve_target(args)
        collector = MeasurementCollector(args.python, args.syscalls)
        rows, metadata = collector.collect(program, sizes, args.repeats)
        estimate, scores = self.estimator.estimate(rows)
        summary = LlmSummaryService(args.llm_summary, args.llm_timeout, args.llm_model).generate(
            program, rows, estimate, scores, metadata
        )
        report_path = self.renderer.render(program, rows, estimate, scores, metadata, args.output, summary)
        self._print_table(program, rows, estimate, report_path)
        if summary:
            print(f"LLM summary: {summary.status} ({summary.provider})")
        return 0

    @staticmethod
    def _resolve_target(args: argparse.Namespace) -> tuple[Path, list[int]]:
        if args.case:
            case = DEMO_CASES[args.case]
            program = Path(case["program"])
            sizes = args.sizes or list(case["sizes"])
        elif args.program:
            program = args.program
            sizes = args.sizes
            if not sizes:
                raise SystemExit("--sizes is required when using --program.")
        else:
            case = DEMO_CASES["bubble_sort"]
            program = Path(case["program"])
            sizes = list(case["sizes"])

        program = program.expanduser().resolve()
        if not program.exists():
            raise SystemExit(f"Program not found: {program}")
        if not sizes or any(size <= 0 for size in sizes):
            raise SystemExit("Sizes must be positive integers.")
        return program, sizes

    @staticmethod
    def _print_table(program: Path, rows: list[Measurement], estimate: str, report_path: Path) -> None:
        print(f"Program: {program}")
        print()
        print(
            f"{'Input size':>12} | {'Wall(ms)':>10} | {'User(ms)':>10} | "
            f"{'Sys(ms)':>9} | {'Memory(KB)':>11} | {'Syscalls':>9}"
        )
        print("-" * 82)
        for row in rows:
            print(
                f"{row.size:>12,} | {fmt_ms(row.wall_ms):>10} | {fmt_ms(row.user_ms):>10} | "
                f"{fmt_ms(row.system_ms):>9} | {fmt_int(row.memory_kb):>11} | {fmt_int(row.syscall_count):>9}"
            )
        print()
        print(f"Estimated complexity: {estimate}")
        print(f"HTML report: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Python program across input sizes and visualize time, memory, syscalls, and Big O fit."
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--program", type=Path, help="Target Python program. It must accept input size as argv[1].")
    target.add_argument("--case", choices=sorted(DEMO_CASES), help="Built-in demo case.")
    parser.add_argument("--sizes", type=int, nargs="+", help="Input sizes to test.")
    parser.add_argument("--repeats", type=int, default=3, help="Number of timing runs per input size.")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter used for the target program.")
    parser.add_argument("--output", type=Path, default=ROOT / "reports", help="Output directory for the report.")
    parser.add_argument(
        "--llm-summary",
        choices=["off", "auto", "on"],
        default="off",
        help="Generate an OS-focused report summary with GitHub Copilot SDK. 'auto' records failures in the report; 'on' fails the run if LLM generation fails.",
    )
    parser.add_argument("--llm-model", default=None, help="Optional Copilot model id for LLM summary generation.")
    parser.add_argument("--llm-timeout", type=float, default=45.0, help="Seconds to wait for LLM summary generation.")
    parser.add_argument(
        "--syscalls",
        choices=["auto", "on", "off"],
        default="auto",
        help="Collect syscall summary with strace -c when available.",
    )
    return parser.parse_args()


def main() -> int:
    return AlgoScopeApp().run(parse_args())
