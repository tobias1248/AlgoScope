import { useEffect, useState } from 'react';

function MonitorPanel() {
  const [stats, setStats] = useState({ cpu: 0, ram: 0, last_killed: null });

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/system-stats');
    ws.onmessage = (event) => {
      setStats(JSON.parse(event.data));
    };
    return () => ws.close();
  }, []);

  return (
    <div style={{ border: '1px solid #ddd', padding: '15px', borderRadius: '8px', margin: '10px' }}>
      <h3>System Monitor</h3>
      <p>CPU: {stats.cpu}% | RAM: {stats.ram}%</p>
      {stats.last_killed && (
        <div style={{ color: 'red', fontWeight: 'bold' }}>
          🚨 Last Event: {stats.last_killed}
        </div>
      )}
    </div>
  );
}
export default MonitorPanel;