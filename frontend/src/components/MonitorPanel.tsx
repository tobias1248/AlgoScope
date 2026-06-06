import { useEffect, useState } from 'react';
import { Paper, Group, Stack, Text, Title, Badge, Button, Table, ScrollArea, Divider, ThemeIcon, Flex, Alert } from '@mantine/core';
import { IconShieldCheck, IconShieldOff, IconActivity, IconAlertTriangle } from '@tabler/icons-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

type SystemStats = {
  cpu: number;
  ram: number;
  last_killed: string | null;
};

type ChartPoint = {
  time: string;
  cpu: number;
  ram: number;
};

type ThreatLog = {
  time: string;
  pid: string;
  reason: string;
};

function MonitorPanel() {
  const [stats, setStats] = useState<SystemStats>({ cpu: 0, ram: 0, last_killed: null });
  const [chartData, setChartData] = useState<ChartPoint[]>([]);
  const [logs, setLogs] = useState<ThreatLog[]>([]);
  const [isSentinelOn, setIsSentinelOn] = useState(false);

  const CPU_COLOR = "#0ca678"; // teal
  const RAM_COLOR = "#1c7ed6"; // blue
  
  // 1. WebSocket 即時數據處理 (含折線圖數據積累)
  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/system-stats`);
    ws.onmessage = (event) => {
      const newData = JSON.parse(event.data) as SystemStats;
      setStats(newData);
      
      // 更新折線圖數據，只保留最近 20 筆
      setChartData(prev => {
        const updated = [...prev, { time: new Date().toLocaleTimeString(), cpu: newData.cpu, ram: newData.ram }];
        if (updated.length > 20) return updated.slice(1);
        return updated;
      });
    };
    return () => ws.close();
  }, []);

  // 2. 歷史紀錄抓取
  const fetchLogs = async () => {
    try {
      const res = await fetch('/api/sentinel/logs');
      const data = (await res.json()) as ThreatLog[];
      setLogs(data);
    } catch (err) { console.error(err); }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, []);

  // 3. 哨兵開關
  const toggleSentinel = async () => {
    const newState = !isSentinelOn;
    await fetch('/api/sentinel/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable: newState })
    });
    setIsSentinelOn(newState);
  };

  const lastKilledParts = stats.last_killed?.split(',') ?? [];

return (
    <Paper withBorder p="xl" radius="lg" shadow="xl" mb="xl" bg="var(--mantine-color-body)" style={{ borderTop: `4px solid ${isSentinelOn ? 'red' : 'teal'}` }}>
      {/* 標頭區 - 增加視覺重量 */}
      <Group justify="space-between" mb="xl">
        <Group gap="md">
          <ThemeIcon size={48} radius="md" variant="light" color={isSentinelOn ? "red" : "teal"}>
            <IconShieldCheck size={28} />
          </ThemeIcon>
          <Stack gap={0}>
            <Title order={3} style={{ lineHeight: 1 }}>OS Runtime Sentinel</Title>
            <Text size="xs" c="dimmed">Active Process Protection & Resource Defense</Text>
          </Stack>
        </Group>
        <Button 
          variant={isSentinelOn ? "filled" : "outline"}
          color={isSentinelOn ? "red" : "teal"}
          size="md"
          leftSection={isSentinelOn ? <IconShieldOff size={20} /> : <IconActivity size={20} />}
          onClick={toggleSentinel}
          style={{ paddingLeft: '20px', paddingRight: '20px' }}
        >
          {isSentinelOn ? "Disable Sentinel" : "Enable Sentinel"}
        </Button>
      </Group>

      {/* 核心區：左側數據 + 右側加大圖表 */}
      <Flex gap="xl" align="flex-start" mb="xl" direction={{ base: 'column', md: 'row' }}>
        
        {/* 左側數據區 - 重新對齊與上色 */}
        <Stack gap="lg" style={{ flex: '0 0 240px' }}>
          <Stack gap="xs">
            <Paper withBorder p="md" radius="sm" bg="var(--mantine-color-gray-0)">
              <Text size="xs" fw={700} c="dimmed" tt="uppercase">CPU Load</Text>
              <Text size="38px" fw={900} style={{ color: CPU_COLOR, lineHeight: 1 }}>{stats.cpu}%</Text>
              <Badge color="teal" size="xs" variant="light" mt={3}>Teal Line</Badge>
            </Paper>
            <Paper withBorder p="md" radius="sm" bg="var(--mantine-color-gray-0)">
              <Text size="xs" fw={700} c="dimmed" tt="uppercase">RAM Usage</Text>
              <Text size="38px" fw={900} style={{ color: RAM_COLOR, lineHeight: 1 }}>{stats.ram}%</Text>
              <Badge color="blue" size="xs" variant="light" mt={3}>Blue Line</Badge>
            </Paper>
          </Stack>
          {stats.last_killed && (
            <Alert color="red" variant="filled" icon={<IconAlertTriangle size={18} />} title="Kill Event">
              PID: {lastKilledParts[1] ?? "unknown"} | {lastKilledParts.at(-1) ?? stats.last_killed}
            </Alert>
          )}
        </Stack>

        {/* 右側圖表區 - 顯著加大高度與視覺 */}
        <Paper withBorder p="lg" radius="sm" style={{ flex: 1, position: 'relative' }}>
          <Text size="sm" fw={700} c="dimmed" mb="lg" tt="uppercase">Live Activity Stream</Text>
          {/* 高度從 120px 增加到 280px，讓波動更清晰 */}
          <div style={{ height: 280, width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                <XAxis dataKey="time" hide />
                {/* 增加 YAxis 參考，domain [0, 100] 避免數據壓平 */}
                <YAxis type="number" domain={[0, 100]} hide={true} />
                <Tooltip 
                  contentStyle={{ border: 'none', borderRadius: '4px', boxShadow: 'sm' }} 
                  labelStyle={{ display: 'none' }} 
                />
                {/* ReferenceLine 幫助定位 Y=0 和 Y=100 的邊界 */}
                <ReferenceLine y={0} stroke="#ddd" />
                <ReferenceLine y={100} stroke="#ddd" />
                {/* 統一線條樣式：步進式線條更像數據 */}
                <Line type="step" dataKey="cpu" stroke={CPU_COLOR} strokeWidth={3} dot={false} isAnimationActive={false} />
                <Line type="step" dataKey="ram" stroke={RAM_COLOR} strokeWidth={3} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Paper>
      </Flex>

      <Divider my="xl" label="Threat History & Audit Logs" labelPosition="center" />

      {/* 底部紀錄表格 - 維持精緻感 */}
      <ScrollArea h={180}>
        <Table verticalSpacing="xs" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Timestamp</Table.Th><Table.Th>Process ID</Table.Th><Table.Th>Termination Reason</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {logs.map((log, i) => (
              <Table.Tr key={i}>
                <Table.Td>{log.time}</Table.Td>
                <Table.Td><Badge variant="outline" color="gray">{log.pid}</Badge></Table.Td>
                <Table.Td><Text size="sm" fw={500} c="red">{log.reason}</Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Paper>
  );
}

export default MonitorPanel;
