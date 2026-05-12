"""HTML and JSON report rendering."""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from algoscope.models import ComplexityScore, Measurement
from algoscope.utils import fmt_int, fmt_ms


class HtmlReportRenderer:
    """Render AlgoScope measurements into a static HTML report."""

    def render(
        self,
        program: Path,
        rows: list[Measurement],
        estimate: str,
        scores: list[ComplexityScore],
        metadata: dict[str, Any],
        output_dir: Path,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", program.stem).strip("-") or "report"
        report_path = output_dir / f"{slug}-report.html"
        json_path = output_dir / f"{slug}-data.json"

        self._write_json(json_path, program, rows, estimate, scores, metadata)
        report_path.write_text(
            self._render_html(program, rows, estimate, scores, metadata, json_path),
            encoding="utf-8",
        )
        return report_path

    @staticmethod
    def _write_json(
        json_path: Path,
        program: Path,
        rows: list[Measurement],
        estimate: str,
        scores: list[ComplexityScore],
        metadata: dict[str, Any],
    ) -> None:
        data = {
            "program": str(program),
            "estimated_complexity": estimate,
            "metadata": metadata,
            "measurements": [asdict(row) for row in rows],
            "model_scores": [asdict(score) for score in scores],
        }
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _render_html(
        self,
        program: Path,
        rows: list[Measurement],
        estimate: str,
        scores: list[ComplexityScore],
        metadata: dict[str, Any],
        json_path: Path,
    ) -> str:
        table_rows = self._render_measurement_rows(rows)
        score_rows = self._render_score_rows(scores)
        unavailable_note = ""
        if metadata.get("strace") == "unavailable":
            unavailable_note = (
                '<p class="note">strace is unavailable on this machine, so syscall data is marked n/a. '
                "Run on Linux with strace installed to enable this OS-level metric.</p>"
            )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AlgoScope Report - {html.escape(program.name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #1e2428;
      --muted: #65717a;
      --line: #d7ddd8;
      --accent: #1c7c70;
      --accent-2: #b54036;
      --note: #fff6dc;
      --note-border: #ead89a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    header, main {{ max-width: 1100px; margin: 0 auto; padding: 28px; }}
    header {{ padding-top: 42px; }}
    h1 {{ margin: 0 0 8px; font-size: 36px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; letter-spacing: 0; }}
    p {{ color: var(--muted); margin: 0 0 14px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin-top: 22px;
    }}
    .metric, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 16px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 24px; }}
    main {{ display: grid; gap: 18px; padding-top: 8px; }}
    section {{ padding: 18px; overflow: hidden; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: right; padding: 10px 9px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th:first-child, td:first-child, th:last-child, td:last-child {{ text-align: left; }}
    th {{ color: var(--muted); font-weight: 650; }}
    svg {{ width: 100%; height: auto; display: block; }}
    .axis {{ stroke: #8b9690; stroke-width: 1; }}
    .series {{ fill: none; stroke: var(--accent); stroke-width: 3; }}
    circle {{ fill: var(--accent-2); }}
    text {{ fill: var(--muted); font-size: 12px; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 18px; }}
    .note, .sticky {{ background: var(--note); border: 1px solid var(--note-border); border-radius: 8px; color: #6f5712; padding: 10px 12px; }}
    .os-grid {{ display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.6fr); gap: 16px; align-items: start; }}
    .sticky p {{ color: #6f5712; margin-bottom: 8px; }}
    details {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 10px;
      background: #fbfcfb;
    }}
    summary {{ cursor: pointer; font-weight: 700; }}
    .status {{ color: var(--muted); font-weight: 500; }}
    .command {{
      display: block;
      margin: 10px 0;
      padding: 10px;
      border-radius: 6px;
      overflow-x: auto;
      background: #eef1ef;
      color: #263033;
      white-space: nowrap;
    }}
    code {{ background: #eef1ef; border-radius: 4px; padding: 2px 5px; }}
    @media (max-width: 760px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      .os-grid {{ grid-template-columns: 1fr; }}
      th, td {{ font-size: 13px; padding: 8px 6px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>AlgoScope</h1>
    <p>A Linux-based Runtime Complexity and Resource Visualizer for Students.</p>
    <div class="summary">
      <div class="metric"><span>Program</span><strong>{html.escape(program.name)}</strong></div>
      <div class="metric"><span>Estimated Big O</span><strong>{html.escape(estimate)}</strong></div>
      <div class="metric"><span>Input Range</span><strong>{rows[0].size:,} - {rows[-1].size:,}</strong></div>
      <div class="metric"><span>Time Tool</span><strong>{html.escape(str(metadata.get("time_tool", "n/a")))}</strong></div>
    </div>
  </header>
  <main>
    {unavailable_note}
    <section>
      <h2>Measurements</h2>
      <table>
        <thead>
          <tr>
            <th>Input size</th><th>Wall ms</th><th>User ms</th><th>System ms</th><th>Memory KB</th><th>Syscalls</th><th>Top syscalls</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </section>
    <div class="charts">
      <section>
        <h2>Input Size vs Execution Time</h2>
        {self._scaled_points(rows, lambda row: row.wall_ms)}
      </section>
      <section>
        <h2>Input Size vs Memory Usage</h2>
        {self._scaled_points(rows, lambda row: row.memory_kb)}
      </section>
      <section>
        <h2>Input Size vs Syscall Count</h2>
        {self._scaled_points(rows, lambda row: row.syscall_count)}
      </section>
    </div>
    <section>
      <h2>Big O Model Fit</h2>
      <p>This estimates the closest observed growth pattern, not a formal proof of time complexity.</p>
      <table>
        <thead><tr><th>Model</th><th>Normalized RMSE</th><th>RMSE</th></tr></thead>
        <tbody>{score_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>OS Observability Context</h2>
      <div class="os-grid">
        <div>
          <p>Each input size launches the target as a separate process. AlgoScope records wall time, user CPU time, system CPU time, maximum resident set size, and syscall summaries when Linux <code>strace -c</code> is available.</p>
          <h3>Shell Commands & OS Probes</h3>
          {self._render_probe_commands(metadata)}
        </div>
        <aside class="sticky">
          <h3>Student Notes</h3>
          <p><strong>Process:</strong> every row starts a new child process for the target program.</p>
          <p><strong>CPU time:</strong> user time is code running in user mode; system time is kernel work on behalf of the process.</p>
          <p><strong>Memory:</strong> RSS is the peak resident memory observed for that process.</p>
          <p><strong>Syscalls:</strong> high read/write/openat counts usually indicate I/O overhead rather than pure algorithm cost.</p>
        </aside>
      </div>
      <p>Raw data is saved next to this report as <code>{html.escape(json_path.name)}</code>.</p>
    </section>
  </main>
</body>
</html>
"""

    @staticmethod
    def _render_measurement_rows(rows: list[Measurement]) -> str:
        return "\n".join(
            f"""
        <tr>
          <td>{row.size:,}</td>
          <td>{fmt_ms(row.wall_ms)}</td>
          <td>{fmt_ms(row.user_ms)}</td>
          <td>{fmt_ms(row.system_ms)}</td>
          <td>{fmt_int(row.memory_kb)}</td>
          <td>{fmt_int(row.syscall_count)}</td>
          <td>{html.escape(', '.join(f'{name}: {calls}' for name, calls in row.top_syscalls) or 'n/a')}</td>
        </tr>
        """
            for row in rows
        )

    @staticmethod
    def _render_score_rows(scores: list[ComplexityScore]) -> str:
        return "\n".join(
            f"""
        <tr>
          <td>{html.escape(score.name)}</td>
          <td>{score.normalized_rmse:.4f}</td>
          <td>{score.rmse:.4f}</td>
        </tr>
        """
            for score in scores
        )

    @staticmethod
    def _render_probe_commands(metadata: dict[str, Any]) -> str:
        commands = metadata.get("probe_commands", [])
        if not commands:
            return "<p>No OS probe commands were recorded.</p>"

        rendered = []
        for command in commands:
            title = html.escape(str(command.get("title", "Probe")))
            status = html.escape(str(command.get("status", "unknown")))
            rendered.append(
                f"""
          <details>
            <summary>{title} <span class="status">({status})</span></summary>
            <code class="command">{html.escape(str(command.get("command", "")))}</code>
            <p><strong>Purpose:</strong> {html.escape(str(command.get("purpose", "")))}</p>
            <p><strong>OS concept:</strong> {html.escape(str(command.get("os_concept", "")))}</p>
          </details>
          """
            )
        return "\n".join(rendered)

    @staticmethod
    def _scaled_points(rows: list[Measurement], value_getter) -> str:
        width, height = 760, 260
        pad_left, pad_top, pad_right, pad_bottom = 58, 24, 24, 44
        xs = [row.size for row in rows]
        ys = [value_getter(row) for row in rows]
        valid = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if not valid:
            return '<p class="note">No data available for this chart.</p>'
        x_min, x_max = min(x for x, _ in valid), max(x for x, _ in valid)
        y_min, y_max = 0.0, max(float(y) for _, y in valid)
        if x_min == x_max:
            x_max += 1
        if y_max == y_min:
            y_max += 1

        points = []
        for x, y in valid:
            px = pad_left + (x - x_min) / (x_max - x_min) * (width - pad_left - pad_right)
            py = pad_top + (1 - (float(y) - y_min) / (y_max - y_min)) * (height - pad_top - pad_bottom)
            points.append((px, py, x, y))

        line = " ".join(f"{px:.1f},{py:.1f}" for px, py, _, _ in points)
        circles = "\n".join(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4"><title>n={x}, value={y}</title></circle>'
            for px, py, x, y in points
        )
        labels = "\n".join(
            f'<text x="{px:.1f}" y="244" text-anchor="middle">{x}</text>'
            for px, _, x, _ in points
        )
        return f"""
    <svg viewBox="0 0 {width} {height}" role="img">
      <line class="axis" x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{height - pad_bottom}"></line>
      <line class="axis" x1="{pad_left}" y1="{height - pad_bottom}" x2="{width - pad_right}" y2="{height - pad_bottom}"></line>
      <polyline class="series" points="{line}"></polyline>
      {circles}
      {labels}
    </svg>
    """
