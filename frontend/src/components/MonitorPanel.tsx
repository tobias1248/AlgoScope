import { useEffect, useState } from 'react';
import { Paper, Group, Stack, Text, Title, Badge, Button, RingProgress, Center } from '@mantine/core';
import { IconShieldCheck, IconShieldOff, IconAlertTriangle } from '@tabler/icons-react';

function MonitorPanel() {
  const [stats, setStats] = useState({ cpu: 0, ram: 0, last_killed: null });
  const [isSentinelOn, setIsSentinelOn] = useState(false);

  const toggleSentinel = async () => {
    const newState = !isSentinelOn;
    await fetch('http://127.0.0.1:8000/api/sentinel/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable: newState })
    });
    setIsSentinelOn(newState);
  };

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/system-stats');
    ws.onmessage = (event) => setStats(JSON.parse(event.data));
    return () => ws.close();
  }, []);

  return (
    <Paper withBorder p="md" radius="md" style={{ backgroundColor: 'var(--mantine-color-body)' }}>
      <Group justify="space-between" mb="md">
        <Title order={4}>System Sentinel</Title>
        <Button 
          variant={isSentinelOn ? "filled" : "outline"}
          color={isSentinelOn ? "red" : "teal"}
          leftSection={isSentinelOn ? <IconShieldOff size={16} /> : <IconShieldCheck size={16} />}
          onClick={toggleSentinel}
        >
          {isSentinelOn ? "Disable Sentinel" : "Enable Sentinel"}
        </Button>
      </Group>

      <Group grow>
        <Stack align="center" gap={0}>
          <Text size="xs" c="dimmed">CPU Usage</Text>
          <Text size="xl" fw={700}>{stats.cpu}%</Text>
        </Stack>
        <Stack align="center" gap={0}>
          <Text size="xs" c="dimmed">RAM Usage</Text>
          <Text size="xl" fw={700}>{stats.ram}%</Text>
        </Stack>
      </Group>

      {stats.last_killed && (
        <Badge fullWidth color="red" variant="light" mt="md" size="lg" leftSection={<IconAlertTriangle size={14} />}>
          Latest Kill: {stats.last_killed}
        </Badge>
      )}
    </Paper>
  );
}

export default MonitorPanel;