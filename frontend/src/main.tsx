import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type JobState = "idle" | "queued" | "running" | "completed" | "failed";
type RunStatus = "ok" | "timeout_killed" | "memory_killed" | "runtime_error" | "probe_failed";

type DemoCase = {
  key: string;
  label: string;
  sizes: number[];
  code: string;
};

type Measurement = {
  size: number;
  status: RunStatus;
  wall_ms: number | null;
  user_ms: number | null;
  system_ms: number | null;
  memory_kb: number | null;
  syscall_count: number | null;
  top_syscalls: Array<[string, number]>;
  exit_code?: number | null;
  stdout_excerpt?: string | null;
  stderr_excerpt?: string | null;
};

type AnalysisResult = {
  status: "completed" | "failed";
  estimated_complexity: string;
  measurements: Measurement[];
  model_scores: Array<{ name: string; normalized_rmse: number }>;
  summary: { title: string; body: string; provider: string; status: string } | null;
  metadata: Record<string, unknown>;
};

type SyscallExplanation = {
  name: string;
  calls: number;
  meaning: string;
  signal: string;
};

type JobRecord = {
  job_id: string;
  status: Exclude<JobState, "idle">;
  result: AnalysisResult | null;
  error: string | null;
};

const fallbackCode = `import sys

# Growth runs pass each input size as argv[1].
n = int(sys.argv[1])
items = list(range(n))
target = n - 1

for value in items:
    if value == target:
        break

print(f"searched {n} items; target={target}")
`;

function App() {
  const [demos, setDemos] = useState<DemoCase[]>([]);
  const [selectedDemo, setSelectedDemo] = useState("custom");
  const [code, setCode] = useState(fallbackCode);
  const [sizes, setSizes] = useState("20000 60000 120000 220000");
  const [repeats, setRepeats] = useState(2);
  const [timeoutSeconds, setTimeoutSeconds] = useState(4);
  const [memoryMb, setMemoryMb] = useState(256);
  const [syscalls, setSyscalls] = useState<"auto" | "on" | "off">("auto");
  const [summaryMode, setSummaryMode] = useState<"off" | "auto" | "on">("auto");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobState>("idle");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/demo-cases")
      .then((response) => response.json())
      .then((items: DemoCase[]) => {
        setDemos(items);
        const first = items[0];
        if (first) {
          setSelectedDemo(first.key);
          setCode(first.code);
          setSizes(first.sizes.join(" "));
        }
      })
      .catch(() => {
        setDemos([]);
      });
  }, []);

  useEffect(() => {
    if (!jobId || jobStatus === "completed" || jobStatus === "failed") {
      return;
    }
    const interval = window.setInterval(() => {
      fetch(`/api/analyses/${jobId}`)
        .then(async (response) => {
          if (!response.ok) {
            const body = await response.text();
            throw new Error(body || `Analysis job lookup failed with HTTP ${response.status}`);
          }
          return response.json();
        })
        .then((job: JobRecord) => {
          setJobStatus(job.status);
          setError(job.error);
          if (job.result) {
            setResult(job.result);
          }
        })
        .catch((exc: Error) => {
          setJobStatus("failed");
          setError(exc.message);
        });
    }, 900);
    return () => window.clearInterval(interval);
  }, [jobId, jobStatus]);

  const parsedSizes = useMemo(
    () =>
      sizes
        .split(/[\s,]+/)
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isFinite(value) && value > 0),
    [sizes],
  );

  const okRows = useMemo(
    () => result?.measurements.filter((row) => row.status === "ok" || row.status === "probe_failed") ?? [],
    [result],
  );
  const abnormalRows = useMemo(
    () => result?.measurements.filter((row) => row.status !== "ok") ?? [],
    [result],
  );
  const warnings = useMemo(() => metadataList(result?.metadata.warnings), [result]);
  const resourceSummary = useMemo(() => summarizeResources(result?.measurements ?? []), [result]);

  function applyDemo(key: string) {
    setSelectedDemo(key);
    const demo = demos.find((item) => item.key === key);
    if (!demo) {
      return;
    }
    setCode(demo.code);
    setSizes(demo.sizes.join(" "));
  }

  function applyInspectOnce() {
    setSizes("1");
    setRepeats(1);
    setSyscalls("auto");
  }

  function applyGrowthRun() {
    setSizes("100 500 1000 2000");
    setRepeats(2);
    setSyscalls("auto");
  }

  async function runAnalysis() {
    setResult(null);
    setError(null);
    setJobStatus("queued");
    const response = await fetch("/api/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        sizes: parsedSizes,
        repeats,
        syscalls,
        timeout_seconds: timeoutSeconds,
        memory_mb: memoryMb,
        llm_summary: summaryMode,
        runner: "auto",
      }),
    });
    if (!response.ok) {
      setJobStatus("failed");
      setError(await response.text());
      return;
    }
    const payload = (await response.json()) as { job_id: string };
    setJobId(payload.job_id);
  }

  const isBusy = jobStatus === "queued" || jobStatus === "running";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OS runtime lab</p>
          <h1>AlgoScope</h1>
        </div>
        <div className={`status-pill status-${jobStatus}`}>{jobStatus}</div>
      </header>

      <section className="workspace">
        <div className="code-pane">
          <div className="pane-header">
            <div>
              <h2>Program</h2>
              <p>Growth runs pass input size as sys.argv[1]. Inspect once can run plain scripts like print("Hello World").</p>
            </div>
            <select value={selectedDemo} onChange={(event) => applyDemo(event.target.value)}>
              <option value="custom">Custom</option>
              {demos.map((demo) => (
                <option key={demo.key} value={demo.key}>
                  {demo.label}
                </option>
              ))}
            </select>
          </div>
          <textarea
            spellCheck={false}
            value={code}
            onChange={(event) => {
              setSelectedDemo("custom");
              setCode(event.target.value);
            }}
          />
          <div className="inline-output">
            <div className="inline-output-head">
              <h2>Program output</h2>
              <span>stdout excerpt</span>
            </div>
            <ProgramOutput rows={result?.measurements ?? []} compact />
          </div>
        </div>

        <aside className="control-pane">
          <h2>Experiment settings</h2>
          <div className="mode-actions" aria-label="Experiment presets">
            <button type="button" onClick={applyInspectOnce}>
              Inspect once
            </button>
            <button type="button" onClick={applyGrowthRun}>
              Growth run
            </button>
          </div>
          <label>
            Input sizes
            <input value={sizes} onChange={(event) => setSizes(event.target.value)} />
            <span className="field-help">Use 1 for one-shot syscall inspection. Use multiple values only when code reads sys.argv[1].</span>
          </label>
          <div className="control-grid">
            <label>
              Repeats
              <input type="number" min={1} max={5} value={repeats} onChange={(event) => setRepeats(Number(event.target.value))} />
              <span className="field-help">Median timing samples per size.</span>
            </label>
            <label>
              Timeout
              <input
                type="number"
                min={0.25}
                max={30}
                step={0.25}
                value={timeoutSeconds}
                onChange={(event) => setTimeoutSeconds(Number(event.target.value))}
              />
              <span className="field-help">Wall-clock kill threshold.</span>
            </label>
            <label>
              Memory MB
              <input type="number" min={64} max={2048} value={memoryMb} onChange={(event) => setMemoryMb(Number(event.target.value))} />
              <span className="field-help">Memory ceiling for the submitted program.</span>
            </label>
          </div>
          <p className="control-label">Syscall probe</p>
          <div className="segmented">
            {(["auto", "on", "off"] as const).map((mode) => (
              <button key={mode} className={syscalls === mode ? "active" : ""} onClick={() => setSyscalls(mode)}>
                syscalls {mode}
              </button>
            ))}
          </div>
          <p className="control-label">Copilot notes</p>
          <div className="segmented">
            {(["auto", "off", "on"] as const).map((mode) => (
              <button key={mode} className={summaryMode === mode ? "active" : ""} onClick={() => setSummaryMode(mode)}>
                AI {mode}
              </button>
            ))}
          </div>
          <button className="run-button" disabled={isBusy || parsedSizes.length === 0} onClick={runAnalysis}>
            {isBusy ? "Running..." : "Run analysis"}
          </button>
          {result?.metadata.runner_warning ? <p className="warning">{String(result.metadata.runner_warning)}</p> : null}
        </aside>
      </section>

      <section className="results">
        <div className="section-head">
          <div>
            <h2>Resource signals</h2>
            <p>Start here: these are the OS-level effects produced by the submitted program.</p>
          </div>
        </div>

        <div className="metric-row resource-metrics">
          <Metric label="Peak RSS" value={resourceSummary.peakMemory} />
          <Metric label="Latest syscalls" value={resourceSummary.latestSyscalls} />
          <Metric label="Peak system time" value={resourceSummary.peakSystemTime} />
          <Metric label="Abnormal runs" value={String(abnormalRows.length)} tone={abnormalRows.length ? "warn" : "normal"} />
        </div>

        {error ? <pre className="error-box">{error}</pre> : null}
        <Warnings warnings={warnings} />

        <div className="resource-grid">
          <Panel title="Syscall profile" description="Syscall counts come from strace and highlight kernel-facing I/O and process activity.">
            <SyscallTable rows={result?.measurements ?? []} />
          </Panel>
          <Panel title="Syscall explanation" description="Explains why the displayed syscalls matter for the submitted program.">
            <SyscallExplanation result={result} />
          </Panel>
          <Panel title="Memory trend" description="Peak RSS shows the largest resident memory footprint observed for each input size.">
            <LineChart rows={okRows} field="memory_kb" unit="KB" />
          </Panel>
          <Panel title="Runtime trend" description="Wall time includes process startup and measurement overhead; user time in the table shows CPU work inside Python.">
            <LineChart rows={okRows} field="wall_ms" unit="ms" />
          </Panel>
        </div>

        <div className="diagnostic-grid">
          <Panel title="Analysis notes" description="Local observations are always available; the LLM summary appears when configured and authenticated.">
            <Summary result={result} />
          </Panel>
        </div>

        <div className="secondary-band">
          <Panel title="Complexity fit" description="Big O is placed after resource behavior because it is an observed timing fit, not a proof of the algorithm.">
            <div className="complexity-strip">
              <ComplexityFact label="Observed Big O" value={result?.estimated_complexity ?? "n/a"} />
              <ComplexityFact label="Fit confidence" value={String(result?.metadata.confidence ?? "n/a")} tone={warnings.length ? "warn" : "normal"} />
              <ComplexityFact label="Successful points" value={String(result?.metadata.successful_measurements ?? 0)} />
            </div>
          </Panel>
        </div>

        <Panel title="Measurements" description="Expand a row to inspect exit code, stdout, stderr, and execution details.">
          <MeasurementTable rows={result?.measurements ?? []} />
        </Panel>
      </section>
    </main>
  );
}

function Metric({ label, value, tone = "normal" }: { label: string; value: string; tone?: "normal" | "warn" }) {
  return (
    <div className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ComplexityFact({ label, value, tone = "normal" }: { label: string; value: string; tone?: "normal" | "warn" }) {
  return (
    <div className={`complexity-fact complexity-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Warnings({ warnings }: { warnings: string[] }) {
  if (!warnings.length) {
    return null;
  }
  return (
    <section className="warning-list">
      {warnings.map((warning) => (
        <p key={warning}>{warning}</p>
      ))}
    </section>
  );
}

function Panel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {description ? <p className="panel-description">{description}</p> : null}
      {children}
    </section>
  );
}

function LineChart({ rows, field, unit }: { rows: Measurement[]; field: "wall_ms" | "memory_kb"; unit: string }) {
  const points = rows
    .map((row) => ({ x: row.size, y: row[field] ?? 0 }))
    .filter((point) => point.y > 0);
  if (points.length < 2) {
    return <div className="empty">Need at least two successful measurements.</div>;
  }
  const width = 520;
  const height = 220;
  const pad = 36;
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const maxY = Math.max(...points.map((point) => point.y));
  const sx = (x: number) => pad + ((x - minX) / Math.max(1, maxX - minX)) * (width - pad * 2);
  const sy = (y: number) => height - pad - (y / Math.max(1, maxY)) * (height - pad * 2);
  const d = points.map((point, index) => `${index === 0 ? "M" : "L"} ${sx(point.x)} ${sy(point.y)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${field} chart`}>
      <line className="axis" x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} />
      <line className="axis" x1={pad} y1={pad} x2={pad} y2={height - pad} />
      <path className="chart-line" d={d} />
      {points.map((point) => (
        <g key={point.x}>
          <circle cx={sx(point.x)} cy={sy(point.y)} r="4" />
          <text x={sx(point.x)} y={sy(point.y) - 9} textAnchor="middle">
            {formatNumber(point.y)} {unit}
          </text>
        </g>
      ))}
    </svg>
  );
}

function SyscallTable({ rows }: { rows: Measurement[] }) {
  const syscallRows = rows.filter((row) => row.top_syscalls.length > 0 || row.syscall_count != null);
  if (!syscallRows.length) {
    return <div className="empty">No syscall data yet. Use Linux with strace for complete syscall counts.</div>;
  }
  const signatures = syscallRows.map((row) => row.top_syscalls.map(([name]) => name).join(","));
  const stableShape = signatures.length > 1 && new Set(signatures).size === 1;

  return (
    <div className="syscall-profile">
      {stableShape ? (
        <p className="inline-note">
          Top syscalls are the same across input sizes. For tiny scripts or code that ignores argv[1], Python startup and file lookup often dominate the
          profile.
        </p>
      ) : null}
      <table>
        <thead>
          <tr>
            <th>n</th>
            <th>Total</th>
            <th>Top syscalls</th>
          </tr>
        </thead>
        <tbody>
          {syscallRows.map((row) => (
            <tr key={row.size}>
              <td>{formatNumber(row.size)}</td>
              <td>{row.syscall_count == null ? "n/a" : formatNumber(row.syscall_count)}</td>
              <td>
                <div className="syscall-chips">
                  {row.top_syscalls.map(([name, calls]) => (
                    <span className="syscall-chip" key={`${row.size}-${name}`}>
                      <strong>{name}</strong>
                      {formatNumber(calls)}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SyscallExplanation({ result }: { result: AnalysisResult | null }) {
  if (!result) {
    return <div className="empty">Run with syscall probing enabled to explain kernel activity.</div>;
  }
  const explanations = syscallExplanations(result.metadata.syscall_explanations);
  const unavailableSummary = result.summary?.status === "unavailable" ? result.summary.body : null;
  if (!explanations.length && !result.summary) {
    return <div className="empty">No syscall explanation is available for this run.</div>;
  }
  return (
    <div className="syscall-explain">
      {result.summary?.status === "generated" ? (
        <div className="copilot-note">
          <span>Copilot</span>
          <pre>{result.summary.body}</pre>
        </div>
      ) : null}
      {unavailableSummary ? <p className="copilot-unavailable">{unavailableSummary}</p> : null}
      {explanations.map((item) => (
        <div className="syscall-note" key={item.name}>
          <div>
            <strong>{item.name}</strong>
            <span>{formatNumber(item.calls)} calls</span>
          </div>
          <p>{item.meaning}</p>
          <p>{item.signal}</p>
        </div>
      ))}
    </div>
  );
}

function Summary({ result }: { result: AnalysisResult | null }) {
  if (!result) {
    return <div className="empty">Run an analysis to generate notes.</div>;
  }
  const observations = metadataList(result.metadata.local_observations);
  return (
    <div className="summary">
      {observations.length ? (
        <ul>
          {observations.map((observation) => (
            <li key={observation}>{observation}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ProgramOutput({ rows, compact = false }: { rows: Measurement[]; compact?: boolean }) {
  const rowsWithOutput = rows.filter((row) => row.stdout_excerpt);
  if (!rowsWithOutput.length) {
    return <div className={compact ? "empty empty-compact" : "empty"}>No stdout captured yet.</div>;
  }
  return (
    <div className={compact ? "output-list output-list-compact" : "output-list"}>
      {rowsWithOutput.map((row) => (
        <div className="output-item" key={row.size}>
          <span>n={formatNumber(row.size)}</span>
          <pre>{row.stdout_excerpt}</pre>
        </div>
      ))}
    </div>
  );
}

function MeasurementTable({ rows }: { rows: Measurement[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (!rows.length) {
    return <div className="empty">No measurements yet.</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>n</th>
          <th>Status</th>
          <th>Wall</th>
          <th>User</th>
          <th>System</th>
          <th>RSS</th>
          <th>Syscalls</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <React.Fragment key={row.size}>
            <tr className={row.status === "ok" ? "" : "bad-row"}>
              <td>
                <button className="row-toggle" onClick={() => setExpanded(expanded === row.size ? null : row.size)}>
                  {formatNumber(row.size)}
                </button>
              </td>
              <td>{row.status}</td>
              <td>{formatMs(row.wall_ms)}</td>
              <td>{formatMs(row.user_ms)}</td>
              <td>{formatMs(row.system_ms)}</td>
              <td>{row.memory_kb ? `${formatNumber(row.memory_kb)} KB` : "n/a"}</td>
              <td>{row.syscall_count ? formatNumber(row.syscall_count) : "n/a"}</td>
            </tr>
            {expanded === row.size ? (
              <tr className="detail-row">
                <td colSpan={7}>
                  <div className="detail-grid">
                    <Detail label="Exit code" value={row.exit_code == null ? "n/a" : String(row.exit_code)} />
                    <Detail label="Stdout" value={row.stdout_excerpt || "n/a"} block />
                    <Detail label="Stderr" value={row.stderr_excerpt || "n/a"} block />
                  </div>
                </td>
              </tr>
            ) : null}
          </React.Fragment>
        ))}
      </tbody>
    </table>
  );
}

function Detail({ label, value, block = false }: { label: string; value: string; block?: boolean }) {
  return (
    <div className={block ? "detail detail-block" : "detail"}>
      <span>{label}</span>
      {block ? <pre>{value}</pre> : <strong>{value}</strong>}
    </div>
  );
}

function formatMs(value: number | null) {
  if (value == null) {
    return "n/a";
  }
  if (value === 0) {
    return "<10 ms";
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ms`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(Math.round(value));
}

function summarizeResources(rows: Measurement[]) {
  const memoryValues = rows.map((row) => row.memory_kb).filter((value): value is number => value != null);
  const systemValues = rows.map((row) => row.system_ms).filter((value): value is number => value != null);
  const latestSyscallRow = [...rows].reverse().find((row) => row.syscall_count != null);
  return {
    peakMemory: memoryValues.length ? `${formatNumber(Math.max(...memoryValues))} KB` : "n/a",
    latestSyscalls: latestSyscallRow?.syscall_count == null ? "n/a" : formatNumber(latestSyscallRow.syscall_count),
    peakSystemTime: systemValues.length ? formatMs(Math.max(...systemValues)) : "n/a",
  };
}

function metadataList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function syscallExplanations(value: unknown): SyscallExplanation[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is SyscallExplanation => {
    return (
      typeof item === "object" &&
      item !== null &&
      typeof (item as SyscallExplanation).name === "string" &&
      typeof (item as SyscallExplanation).calls === "number" &&
      typeof (item as SyscallExplanation).meaning === "string" &&
      typeof (item as SyscallExplanation).signal === "string"
    );
  });
}

createRoot(document.getElementById("root")!).render(<App />);
