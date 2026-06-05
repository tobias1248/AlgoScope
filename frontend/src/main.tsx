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

type JobRecord = {
  job_id: string;
  status: Exclude<JobState, "idle">;
  result: AnalysisResult | null;
  error: string | null;
};

const fallbackCode = `import sys

n = int(sys.argv[1])
items = list(range(n))
target = n - 1

for value in items:
    if value == target:
        break
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
  const [runner, setRunner] = useState<"auto" | "docker" | "local">("auto");
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
        .then((response) => response.json())
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

  function applyDemo(key: string) {
    setSelectedDemo(key);
    const demo = demos.find((item) => item.key === key);
    if (!demo) {
      return;
    }
    setCode(demo.code);
    setSizes(demo.sizes.join(" "));
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
        runner,
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
              <p>Submitted code must read the input size from argv[1].</p>
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
        </div>

        <aside className="control-pane">
          <h2>Run controls</h2>
          <label>
            Input sizes
            <input value={sizes} onChange={(event) => setSizes(event.target.value)} />
          </label>
          <div className="control-grid">
            <label>
              Repeats
              <input type="number" min={1} max={5} value={repeats} onChange={(event) => setRepeats(Number(event.target.value))} />
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
            </label>
            <label>
              Memory MB
              <input type="number" min={64} max={2048} value={memoryMb} onChange={(event) => setMemoryMb(Number(event.target.value))} />
            </label>
            <label>
              Runner
              <select value={runner} onChange={(event) => setRunner(event.target.value as "auto" | "docker" | "local")}>
                <option value="auto">Auto</option>
                <option value="docker">Docker</option>
                <option value="local">Local dev</option>
              </select>
            </label>
          </div>
          <div className="segmented">
            {(["auto", "on", "off"] as const).map((mode) => (
              <button key={mode} className={syscalls === mode ? "active" : ""} onClick={() => setSyscalls(mode)}>
                syscalls {mode}
              </button>
            ))}
          </div>
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
        <div className="metric-row">
          <Metric label="Observed Big O" value={result?.estimated_complexity ?? "n/a"} />
          <Metric label="Successful points" value={String(result?.metadata.successful_measurements ?? 0)} />
          <Metric label="Abnormal points" value={String(abnormalRows.length)} tone={abnormalRows.length ? "warn" : "normal"} />
          <Metric label="Runner" value={String(result?.metadata.runner ?? "n/a")} />
        </div>

        {error ? <pre className="error-box">{error}</pre> : null}

        <div className="result-grid">
          <Panel title="Runtime trend">
            <LineChart rows={okRows} field="wall_ms" unit="ms" />
          </Panel>
          <Panel title="Memory trend">
            <LineChart rows={okRows} field="memory_kb" unit="KB" />
          </Panel>
          <Panel title="Syscall profile">
            <SyscallTable rows={result?.measurements ?? []} />
          </Panel>
          <Panel title="AI summary">
            <Summary result={result} />
          </Panel>
        </div>

        <Panel title="Measurements">
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

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
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
  const latest = [...rows].reverse().find((row) => row.top_syscalls.length > 0);
  if (!latest) {
    return <div className="empty">No syscall data yet. Use Linux with strace for complete syscall counts.</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Syscall</th>
          <th>Calls</th>
        </tr>
      </thead>
      <tbody>
        {latest.top_syscalls.map(([name, calls]) => (
          <tr key={name}>
            <td>{name}</td>
            <td>{formatNumber(calls)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Summary({ result }: { result: AnalysisResult | null }) {
  if (!result) {
    return <div className="empty">Run an analysis to generate an educational summary.</div>;
  }
  if (!result.summary) {
    return <div className="empty">AI summary is off or unavailable.</div>;
  }
  return (
    <div className="summary">
      <p className="summary-title">{result.summary.title}</p>
      <p className="summary-status">
        {result.summary.status} · {result.summary.provider}
      </p>
      <pre>{result.summary.body}</pre>
    </div>
  );
}

function MeasurementTable({ rows }: { rows: Measurement[] }) {
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
          <tr key={row.size} className={row.status === "ok" ? "" : "bad-row"}>
            <td>{formatNumber(row.size)}</td>
            <td>{row.status}</td>
            <td>{formatMs(row.wall_ms)}</td>
            <td>{formatMs(row.user_ms)}</td>
            <td>{formatMs(row.system_ms)}</td>
            <td>{row.memory_kb ? `${formatNumber(row.memory_kb)} KB` : "n/a"}</td>
            <td>{row.syscall_count ? formatNumber(row.syscall_count) : "n/a"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatMs(value: number | null) {
  return value == null ? "n/a" : `${value.toFixed(value >= 100 ? 0 : 1)} ms`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(Math.round(value));
}

createRoot(document.getElementById("root")!).render(<App />);
