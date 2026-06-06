import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Code,
  Group,
  MantineProvider,
  NumberInput,
  Paper,
  ScrollArea,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
  createTheme,
} from "@mantine/core";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import {
  IconActivityHeartbeat,
  IconAlertTriangle,
  IconBolt,
  IconBrandPython,
  IconChartDots,
  IconCpu,
  IconPlayerPlay,
  IconTerminal2,
} from "@tabler/icons-react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

type SyscallDictionaryEntry = {
  name: string;
  category: string;
  meaning: string;
  pythonTrigger: string;
  note: string;
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

const SYSCALL_DICTIONARY: SyscallDictionaryEntry[] = [
  {
    name: "rt_sigaction",
    category: "signal",
    meaning: "Installs or reads a signal handler for the process.",
    pythonTrigger: "Python configures handlers for signals such as SIGINT, SIGPIPE, and runtime-managed signal behavior during startup.",
    note: "Seeing this in tiny scripts usually says more about interpreter startup than about the algorithm itself.",
  },
  {
    name: "rt_sigprocmask",
    category: "signal",
    meaning: "Reads or changes the set of blocked signals for the current thread.",
    pythonTrigger: "The interpreter or libraries may adjust signal masks around startup, subprocess, threading, or protected runtime sections.",
    note: "Use it to discuss how Unix processes control which asynchronous events can interrupt execution.",
  },
  {
    name: "execve",
    category: "process",
    meaning: "Replaces the current process image with a new program.",
    pythonTrigger: "AlgoScope launches Python for each input size, so process startup normally includes execve.",
    note: "This marks program launch, not work done by the submitted algorithm.",
  },
  {
    name: "brk",
    category: "memory",
    meaning: "Moves the process heap boundary.",
    pythonTrigger: "Python object allocation, list growth, imports, and interpreter startup can request heap space.",
    note: "Rising brk activity can indicate heap allocation pressure, but mmap is also common for larger allocations.",
  },
  {
    name: "mmap",
    category: "memory",
    meaning: "Maps files or anonymous memory into the process address space.",
    pythonTrigger: "Python and the dynamic loader map shared libraries, bytecode, locale data, and anonymous memory regions.",
    note: "In Python traces, mmap often reflects runtime setup and library loading as much as user code.",
  },
  {
    name: "munmap",
    category: "memory",
    meaning: "Unmaps a memory region from the process address space.",
    pythonTrigger: "Cleanup after mapped files, temporary runtime regions, or allocator-managed memory can trigger munmap.",
    note: "Pair it with mmap to explain lifecycle: map a region, use it, release it.",
  },
  {
    name: "openat",
    category: "file",
    meaning: "Opens a path relative to a directory file descriptor.",
    pythonTrigger: "Imports, module lookup, reading source files, temp files, and ordinary file I/O commonly use openat.",
    note: "High openat counts usually point to filesystem lookup or file-heavy workloads.",
  },
  {
    name: "newfstatat",
    category: "file",
    meaning: "Reads metadata for a path.",
    pythonTrigger: "Python import resolution and file existence checks often inspect path metadata.",
    note: "It answers questions such as whether a path exists and what type/size/permissions it has.",
  },
  {
    name: "read",
    category: "file",
    meaning: "Reads bytes from a file descriptor.",
    pythonTrigger: "Loading modules, reading input files, pipes, or stdin can produce read calls.",
    note: "Compare read counts with write counts to separate input-heavy and output-heavy behavior.",
  },
  {
    name: "write",
    category: "file",
    meaning: "Writes bytes to a file descriptor.",
    pythonTrigger: "print(), logging, stdout, stderr, and file output use write underneath.",
    note: "Frequent writes usually mean output behavior, not CPU-bound computation.",
  },
  {
    name: "close",
    category: "file",
    meaning: "Releases an open file descriptor.",
    pythonTrigger: "Files, pipes, sockets, and runtime-opened descriptors are closed during cleanup.",
    note: "Close calls often track the lifecycle of earlier open/openat calls.",
  },
  {
    name: "lseek",
    category: "file",
    meaning: "Moves or checks the offset of an open file descriptor.",
    pythonTrigger: "Buffered file reading, module loading, and random-access file operations can seek.",
    note: "It is useful when explaining file-position state maintained by the kernel.",
  },
  {
    name: "ioctl",
    category: "device",
    meaning: "Sends a device-specific control request to a file descriptor.",
    pythonTrigger: "Terminal checks, descriptor configuration, and environment probing can issue ioctl.",
    note: "It is a catch-all interface; interpretation depends strongly on the descriptor.",
  },
  {
    name: "getdents64",
    category: "file",
    meaning: "Reads directory entries from a directory file descriptor.",
    pythonTrigger: "Directory scans, package discovery, and import-related filesystem traversal can call getdents64.",
    note: "This is the kernel-facing operation behind listing directory contents.",
  },
  {
    name: "futex",
    category: "scheduler",
    meaning: "Waits or wakes threads through a fast userspace mutex path.",
    pythonTrigger: "Threading, locks, runtime synchronization, and some libraries can use futex.",
    note: "Futex connects userspace lock state with kernel sleep/wakeup only when contention requires it.",
  },
  {
    name: "clone",
    category: "process",
    meaning: "Creates a new thread or process-like task.",
    pythonTrigger: "Threading, multiprocessing, subprocess helpers, or runtime-managed workers can trigger clone.",
    note: "It is the Linux primitive behind many process/thread creation APIs.",
  },
  {
    name: "arch_prctl",
    category: "process",
    meaning: "Sets architecture-specific thread/process state.",
    pythonTrigger: "The runtime loader and Python process startup configure thread-local storage on x86-64.",
    note: "For small Python scripts, this is usually startup machinery rather than algorithm behavior.",
  },
  {
    name: "set_tid_address",
    category: "process",
    meaning: "Registers where the kernel writes thread ID state for thread exit handling.",
    pythonTrigger: "Process startup and threading runtime initialization can register this address.",
    note: "It is part of Linux thread/process bookkeeping.",
  },
  {
    name: "set_robust_list",
    category: "scheduler",
    meaning: "Registers robust futex state for cleanup if a thread exits while holding a lock.",
    pythonTrigger: "Runtime initialization for threading and synchronization can set robust futex metadata.",
    note: "It supports safer lock recovery when threads terminate unexpectedly.",
  },
  {
    name: "prlimit64",
    category: "process",
    meaning: "Reads or sets process resource limits.",
    pythonTrigger: "AlgoScope and runtimes may inspect or apply limits for memory, CPU, files, or other resources.",
    note: "In this app, it is especially relevant because analyses run with timeout and memory limits.",
  },
];

const theme = createTheme({
  primaryColor: "teal",
  defaultRadius: "md",
  fontFamily:
    "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
  fontFamilyMonospace: "SFMono-Regular, Consolas, Liberation Mono, monospace",
  headings: {
    fontWeight: "800",
    sizes: {
      h1: { fontSize: "32px", lineHeight: "1.08" },
      h2: { fontSize: "18px", lineHeight: "1.25" },
      h3: { fontSize: "14px", lineHeight: "1.35" },
    },
  },
});

function App() {
  const [demos, setDemos] = useState<DemoCase[]>([]);
  const [selectedDemo, setSelectedDemo] = useState("custom");
  const [code, setCode] = useState(fallbackCode);
  const [sizes, setSizes] = useState("20000 60000 120000 220000");
  const [repeats, setRepeats] = useState(2);
  const [timeoutSeconds, setTimeoutSeconds] = useState(4);
  const [memoryMb, setMemoryMb] = useState(512);
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
    <Box component="main" className="app-shell">
      <Group className="topbar" justify="space-between" align="flex-end">
        <Stack gap={2}>
          <Text className="eyebrow">OS runtime lab</Text>
          <Group gap="sm" align="center">
            <ThemeIcon variant="light" size={38} radius="md" color="teal">
              <IconActivityHeartbeat size={22} />
            </ThemeIcon>
            <Title order={1}>AlgoScope</Title>
          </Group>
        </Stack>
        <Badge className={`status-pill status-${jobStatus}`} size="lg" variant="light">
          {jobStatus}
        </Badge>
      </Group>

      <section className="workspace">
        <Paper className="code-pane" radius="md" withBorder>
          <Group className="pane-header" justify="space-between" align="flex-start">
            <Stack gap={3}>
              <Group gap="xs">
                <ThemeIcon variant="subtle" color="teal" size={28}>
                  <IconBrandPython size={18} />
                </ThemeIcon>
                <Title order={2}>Program</Title>
              </Group>
              <Text c="dimmed" size="sm">
                Executed with Python; no shebang required. Growth runs pass <Code className="inline-code">n</Code> as{" "}
                <Code className="inline-code">sys.argv[1]</Code>.
              </Text>
            </Stack>
          </Group>
          <Box className="program-toolbar">
            <Select
              className="demo-select"
              size="xs"
              label="Demo"
              data={[
                { value: "custom", label: "Custom" },
                ...demos.map((demo) => ({ value: demo.key, label: demo.label })),
              ]}
              value={selectedDemo}
              onChange={(value) => applyDemo(value ?? "custom")}
              allowDeselect={false}
            />
          <TextInput
            className="sizes-input"
            size="xs"
            label="Input sizes"
            placeholder="100 500 1000"
            value={sizes}
            onChange={(event) => setSizes(event.target.value)}
          />
            <NumberInput
            className="compact-number"
            size="xs"
            label="Repeats"
            hideControls
            min={1}
            max={5}
            value={repeats}
            onChange={(value) => setRepeats(toNumber(value, 1))}
          />
          <NumberInput
            className="compact-number"
            size="xs"
            label="Timeout (sec)"
            hideControls
            min={0.25}
            max={30}
            step={0.25}
            value={timeoutSeconds}
            onChange={(value) => setTimeoutSeconds(toNumber(value, 4))}
          />
          <NumberInput
            className="compact-number"
            size="xs"
            label="Memory (MB)"
            hideControls
            min={64}
            max={2048}
            value={memoryMb}
            onChange={(value) => setMemoryMb(toNumber(value, 512))}
          />
          <Box className="toolbar-segment">
            <Text className="control-label">Syscalls</Text>
            <SegmentedControl
              size="xs"
              fullWidth
              data={["auto", "off", "on"]}
              value={syscalls}
              onChange={(value) => setSyscalls(value as typeof syscalls)}
            />
          </Box>
          <Box className="toolbar-segment">
            <Text className="control-label">Copilot</Text>
            <SegmentedControl
              size="xs"
              fullWidth
              data={["auto", "off", "on"]}
              value={summaryMode}
              onChange={(value) => setSummaryMode(value as typeof summaryMode)}
            />
          </Box>
          <Button size="xs" variant="default" onClick={applyInspectOnce}>
            Inspect
          </Button>
          <Button size="xs" variant="default" onClick={applyGrowthRun}>
            Growth
          </Button>
          <Button
            className="run-button"
            leftSection={<IconPlayerPlay size={18} />}
            loading={isBusy}
            disabled={parsedSizes.length === 0}
            onClick={runAnalysis}
            size="sm"
          >
            {isBusy ? "Running..." : "Run analysis"}
          </Button>
          </Box>
          {result?.metadata.runner_warning ? (
            <Alert color="yellow" icon={<IconAlertTriangle size={18} />} variant="light">
              {String(result.metadata.runner_warning)}
            </Alert>
          ) : null}
          <Textarea
            classNames={{ input: "code-editor" }}
            spellCheck={false}
            value={code}
            autosize
            minRows={18}
            onChange={(event) => {
              setSelectedDemo("custom");
              setCode(event.target.value);
            }}
          />
          <Box className="inline-output">
            <Group className="inline-output-head" justify="space-between">
              <Title order={3}>Program output</Title>
              <Badge variant="outline" color="gray">
                stdout excerpt
              </Badge>
            </Group>
            <ProgramOutput rows={result?.measurements ?? []} compact />
          </Box>
        </Paper>
      </section>

      <Stack component="section" className="results" gap="md">
        <Group className="section-head" justify="space-between" align="flex-end">
          <Stack gap={2}>
            <Title order={2}>Resource signals</Title>
            <Text c="dimmed" size="sm">
              Start here: these are the OS-level effects produced by the submitted program.
            </Text>
          </Stack>
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm" className="resource-metrics">
          <Metric icon={<IconCpu size={18} />} label="Peak RSS" value={resourceSummary.peakMemory} />
          <Metric icon={<IconTerminal2 size={18} />} label="Latest syscalls" value={resourceSummary.latestSyscalls} />
          <Metric icon={<IconBolt size={18} />} label="Peak system time" value={resourceSummary.peakSystemTime} />
          <Metric
            icon={<IconAlertTriangle size={18} />}
            label="Abnormal runs"
            value={String(abnormalRows.length)}
            tone={abnormalRows.length ? "warn" : "normal"}
          />
        </SimpleGrid>

        {error ? (
          <Alert color="red" icon={<IconAlertTriangle size={18} />} variant="light">
            <pre className="error-box">{error}</pre>
          </Alert>
        ) : null}
        <Warnings warnings={warnings} />

        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" className="resource-grid">
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
        </SimpleGrid>

        <Panel title="Analysis notes" description="Local observations are always available; the LLM summary appears when configured and authenticated.">
          <Summary result={result} />
        </Panel>

        <Panel title="Complexity fit" description="Big O is placed after resource behavior because it is an observed timing fit, not a proof of the algorithm.">
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <ComplexityFact icon={<IconChartDots size={18} />} label="Observed Big O" value={result?.estimated_complexity ?? "n/a"} />
            <ComplexityFact
              icon={<IconActivityHeartbeat size={18} />}
              label="Fit confidence"
              value={String(result?.metadata.confidence ?? "n/a")}
              tone={warnings.length ? "warn" : "normal"}
            />
            <ComplexityFact icon={<IconBolt size={18} />} label="Successful points" value={String(result?.metadata.successful_measurements ?? 0)} />
          </SimpleGrid>
        </Panel>

        <Panel title="Measurements" description="Expand a row to inspect exit code, stdout, stderr, and execution details.">
          <MeasurementTable rows={result?.measurements ?? []} />
        </Panel>
      </Stack>
    </Box>
  );
}

function Metric({ icon, label, value, tone = "normal" }: { icon: React.ReactNode; label: string; value: string; tone?: "normal" | "warn" }) {
  return (
    <Paper className={`metric metric-${tone}`} radius="md" withBorder>
      <Group justify="space-between" align="flex-start">
        <Stack gap={5}>
          <Text className="metric-label">{label}</Text>
          <Text className="metric-value">{value}</Text>
        </Stack>
        <ThemeIcon variant="light" color={tone === "warn" ? "red" : "teal"} size={34} radius="md">
          {icon}
        </ThemeIcon>
      </Group>
    </Paper>
  );
}

function ComplexityFact({
  icon,
  label,
  value,
  tone = "normal",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "normal" | "warn";
}) {
  return (
    <Box className={`complexity-fact complexity-${tone}`}>
      <Group gap="xs" align="center">
        <ThemeIcon variant="subtle" color={tone === "warn" ? "red" : "teal"} size={28}>
          {icon}
        </ThemeIcon>
        <Text className="metric-label">{label}</Text>
      </Group>
      <Text className="complexity-value">{value}</Text>
    </Box>
  );
}

function Warnings({ warnings }: { warnings: string[] }) {
  if (!warnings.length) {
    return null;
  }
  return (
    <Alert component="section" className="warning-list" color="yellow" icon={<IconAlertTriangle size={18} />} variant="light">
      {warnings.map((warning) => (
        <Text key={warning} size="sm">
          {warning}
        </Text>
      ))}
    </Alert>
  );
}

function Panel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <Paper component="section" className="panel" radius="md" withBorder>
      <Title order={2}>{title}</Title>
      {description ? (
        <Text className="panel-description" c="dimmed" size="sm">
          {description}
        </Text>
      ) : null}
      {children}
    </Paper>
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
    return <EmptyState>No syscall data yet. Use Linux with strace for complete syscall counts.</EmptyState>;
  }
  const signatures = syscallRows.map((row) => row.top_syscalls.map(([name]) => name).join(","));
  const stableShape = signatures.length > 1 && new Set(signatures).size === 1;

  return (
    <div className="syscall-profile">
      {stableShape ? (
        <Alert className="inline-note" color="orange" variant="light">
          Top syscalls are the same across input sizes. For tiny scripts or code that ignores argv[1], Python startup and file lookup often dominate the
          profile.
        </Alert>
      ) : null}
      <ScrollArea>
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>n</Table.Th>
              <Table.Th>Total</Table.Th>
              <Table.Th>Top syscalls</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {syscallRows.map((row) => (
              <Table.Tr key={row.size}>
                <Table.Td>{formatNumber(row.size)}</Table.Td>
                <Table.Td>{row.syscall_count == null ? "n/a" : formatNumber(row.syscall_count)}</Table.Td>
                <Table.Td>
                <div className="syscall-chips">
                  {row.top_syscalls.map(([name, calls]) => (
                    <Badge className="syscall-chip" key={`${row.size}-${name}`} variant="outline" color="gray">
                      <Code className="chip-code">{name}</Code>
                      {formatNumber(calls)}
                    </Badge>
                  ))}
                </div>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </div>
  );
}

function SyscallExplanation({ result }: { result: AnalysisResult | null }) {
  if (!result) {
    return (
      <div className="syscall-explain">
        <SyscallDictionary />
        <EmptyState compact>Run with syscall probing enabled to explain kernel activity.</EmptyState>
      </div>
    );
  }
  const explanations = syscallExplanations(result.metadata.syscall_explanations);
  const unavailableSummary = result.summary?.status === "unavailable" ? result.summary.body : null;
  const showLocalFallback = result.summary?.status !== "generated";
  if (!explanations.length && !result.summary) {
    return (
      <div className="syscall-explain">
        <SyscallDictionary />
        <EmptyState compact>No syscall explanation is available for this run.</EmptyState>
      </div>
    );
  }
  return (
    <div className="syscall-explain">
      <SyscallDictionary />
      {result.summary?.status === "generated" ? (
        <div className="copilot-note">
          <Text className="metric-label">Copilot</Text>
          <MarkdownBlock>{result.summary.body}</MarkdownBlock>
        </div>
      ) : null}
      {unavailableSummary ? <Text className="copilot-unavailable">{unavailableSummary}</Text> : null}
      {showLocalFallback ? explanations.map((item) => (
        <div className="syscall-note" key={item.name}>
          <div>
            <Code className="inline-code">{item.name}</Code>
            <Badge variant="light" color="gray">
              {formatNumber(item.calls)} calls
            </Badge>
          </div>
          <Text size="sm">{item.meaning}</Text>
          <Text c="dimmed" size="sm">
            {item.signal}
          </Text>
        </div>
      )) : null}
    </div>
  );
}

function SyscallDictionary() {
  const [selected, setSelected] = useState<string | null>(null);
  const entry = SYSCALL_DICTIONARY.find((item) => item.name === selected);
  return (
    <Paper className="syscall-dictionary" radius="md" withBorder>
      <Select
        label="Syscall dictionary"
        placeholder="Search a prepared syscall"
        size="xs"
        searchable
        clearable
        data={SYSCALL_DICTIONARY.map((item) => ({
          value: item.name,
          label: `${item.name} · ${item.category}`,
        }))}
        value={selected}
        onChange={setSelected}
      />
      {entry ? (
        <div className="dictionary-result">
          <Group justify="space-between" align="center" gap="xs">
            <Code className="inline-code">{entry.name}</Code>
            <Badge variant="light" color="teal">
              {entry.category}
            </Badge>
          </Group>
          <DictionaryFact label="Meaning" value={entry.meaning} />
          <DictionaryFact label="Python trigger" value={entry.pythonTrigger} />
          <DictionaryFact label="OS note" value={entry.note} />
        </div>
      ) : null}
    </Paper>
  );
}

function DictionaryFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="dictionary-fact">
      <Text className="metric-label">{label}</Text>
      <Text size="sm">{value}</Text>
    </div>
  );
}

function Summary({ result }: { result: AnalysisResult | null }) {
  if (!result) {
    return <EmptyState>Run an analysis to generate notes.</EmptyState>;
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
    return <EmptyState compact={compact}>No stdout captured yet.</EmptyState>;
  }
  return (
    <div className={compact ? "output-list output-list-compact" : "output-list"}>
      {rowsWithOutput.map((row) => (
        <div className="output-item" key={row.size}>
          <Text className="metric-label">n={formatNumber(row.size)}</Text>
          <pre>{row.stdout_excerpt}</pre>
        </div>
      ))}
    </div>
  );
}

function MeasurementTable({ rows }: { rows: Measurement[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (!rows.length) {
    return <EmptyState>No measurements yet.</EmptyState>;
  }
  return (
    <ScrollArea>
      <Table verticalSpacing="sm" highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>n</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Wall</Table.Th>
            <Table.Th>User</Table.Th>
            <Table.Th>System</Table.Th>
            <Table.Th>RSS</Table.Th>
            <Table.Th>Syscalls</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <React.Fragment key={row.size}>
              <Table.Tr className={row.status === "ok" ? "" : "bad-row"}>
                <Table.Td>
                  <Button variant="subtle" size="compact-sm" onClick={() => setExpanded(expanded === row.size ? null : row.size)}>
                    {formatNumber(row.size)}
                  </Button>
                </Table.Td>
                <Table.Td>
                  <Badge color={row.status === "ok" ? "teal" : "red"} variant="light">
                    {row.status}
                  </Badge>
                </Table.Td>
                <Table.Td>{formatMs(row.wall_ms)}</Table.Td>
                <Table.Td>{formatMs(row.user_ms)}</Table.Td>
                <Table.Td>{formatMs(row.system_ms)}</Table.Td>
                <Table.Td>{row.memory_kb ? `${formatNumber(row.memory_kb)} KB` : "n/a"}</Table.Td>
                <Table.Td>{row.syscall_count ? formatNumber(row.syscall_count) : "n/a"}</Table.Td>
              </Table.Tr>
              {expanded === row.size ? (
                <Table.Tr className="detail-row">
                  <Table.Td colSpan={7}>
                  <div className="detail-grid">
                    <Detail label="Exit code" value={row.exit_code == null ? "n/a" : String(row.exit_code)} />
                    <Detail label="Stdout" value={row.stdout_excerpt || "n/a"} block />
                    <Detail label="Stderr" value={row.stderr_excerpt || "n/a"} block />
                  </div>
                  </Table.Td>
                </Table.Tr>
              ) : null}
            </React.Fragment>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

function Detail({ label, value, block = false }: { label: string; value: string; block?: boolean }) {
  return (
    <div className={block ? "detail detail-block" : "detail"}>
      <Text className="metric-label">{label}</Text>
      {block ? <pre>{value}</pre> : <strong>{value}</strong>}
    </div>
  );
}

function MarkdownBlock({ children }: { children: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

function EmptyState({ children, compact = false }: { children: React.ReactNode; compact?: boolean }) {
  return (
    <Paper className={compact ? "empty empty-compact" : "empty"} radius="md" withBorder>
      <Text c="dimmed" size="sm">
        {children}
      </Text>
    </Paper>
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

function toNumber(value: string | number, fallback: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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

createRoot(document.getElementById("root")!).render(
  <MantineProvider theme={theme}>
    <ModalsProvider>
      <Notifications position="top-right" />
      <App />
    </ModalsProvider>
  </MantineProvider>,
);
