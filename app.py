import streamlit as st
import subprocess
import psutil
import time
import os
import glob 
import signal
import streamlit.components.v1 as components
from pathlib import Path

# System Configuration
st.set_page_config(
    page_title="AlgoScope: Core Analytics Panel", 
    page_icon="📊", 
    layout="wide"
)
st.markdown("""
    <style>
    footer {visibility: hidden;}
    .stAppHeader {background-color: transparent;}
    </style>
    """, unsafe_allow_html=True)

# Main Title
st.title("AlgoScope: OS-Level Runtime & Resource Profiler")
st.markdown("An automated benchmarking platform integrated with an Active Auditing Watchdog.")
st.markdown("---")

# ==========================================
# 1. Host Infrastructure Monitoring
# ==========================================
st.subheader("1. Host Telemetry (Macro-auditing)")
col_cpu, col_mem = st.columns(2)

# Fetch system-wide resource metrics
host_cpu = psutil.cpu_percent(interval=None)
host_mem = psutil.virtual_memory().percent

with col_cpu:
    st.metric(label="Global CPU Utilization", value=f"{host_cpu} %")
    st.progress(int(host_cpu))

with col_mem:
    st.metric(label="Global Memory Utilization", value=f"{host_mem} %")
    st.progress(int(host_mem))

st.markdown("---")

# ==========================================
# 2. Control Panel & Policy Scheduler (Sidebar)
# ==========================================
st.sidebar.header("Control Panel")

# Target Workload Selection
base_dir = os.path.dirname(os.path.abspath(__file__))
search_path = os.path.join(base_dir, "examples", "*.py")

program_files = glob.glob(search_path)
available_programs = {os.path.basename(f): f for f in program_files}

selected_label = st.sidebar.selectbox("Target Workload", list(available_programs.keys()))
program_path = available_programs[selected_label]

# Watchdog Policy Enforcement
mode = st.sidebar.radio("Active Auditing Policy", ["eco", "normal"])

# Policy Context Tooltips
if mode == "eco":
    st.sidebar.caption("🔒 **Eco Mode Enforcement:** Strict resource quotas applied (CPU 60%, Mem 150MB). Transgressions trigger immediate SIGKILL.")
    default_cpu = 60
else:
    st.sidebar.caption("🔓 **Normal Mode Enforcement:** Full core optimization allowed. High CPU threshold provided as system protection.")
    default_cpu = 99

# Threshold Tuning
cpu_threshold = st.sidebar.slider("CPU Quota Threshold (%)", 10, 100, default_cpu)
repeats = st.sidebar.slider("Sample Runs (Repeats)", 1, 5, 3)

enable_sentinel = st.sidebar.checkbox("Enable System-wide Sentinel")

if enable_sentinel:
    # 這裡啟動背景進程
    # 技巧：使用 subprocess 啟動，並記錄 PID，這樣網頁關掉時可以順便砍掉 Sentinel
    if "sentinel_pid" not in st.session_state:
        p = subprocess.Popen(["python3", "sentinel.py"])
        st.session_state.sentinel_pid = p.pid
        st.sidebar.success(f"Sentinel running (PID: {p.pid})")
else:
    if "sentinel_pid" in st.session_state:
        os.kill(st.session_state.sentinel_pid, signal.SIGKILL)
        del st.session_state.sentinel_pid
        st.sidebar.warning("Sentinel disabled.")

# 即時監控按鈕功能
st.subheader("Live Threat Map (Real-time Audit)")

# 設置自動刷新：每 1000 毫秒 (1秒) 刷新一次，這只會更新 UI 元件，不會重跑整個程式
count = st_autorefresh(interval=1000, key="datarefresh")

# 建立固定容器
monitor_container = st.container()

if enable_sentinel:
    with monitor_container:
        # 採樣間隔設為 0，改用前一次的數據，這樣才不會阻塞 UI
        curr_cpu = psutil.cpu_percent(interval=None) 
        
        # 讀取威脅檔案
        try:
            with open("threat_log.txt", "r") as f:
                threat_count = len(f.readlines())
        except:
            threat_count = 0
            
        col1, col2, col3 = st.columns(3)
        col1.metric("CPU Load", f"{curr_cpu}%")
        col2.metric("Threats Blocked", threat_count)
        col3.metric("Status", "🛡️ Active")
        
        # CPU 歷史波動圖 (使用列表紀錄)
        if "cpu_history" not in st.session_state: st.session_state.cpu_history = [0]*30
        st.session_state.cpu_history.append(curr_cpu)
        if len(st.session_state.cpu_history) > 30: st.session_state.cpu_history.pop(0)
        
        st.line_chart(st.session_state.cpu_history)
else:
    monitor_container.info("Sentinel is OFF.")
    
with st.expander("🛡️ Recent Threat Log (Click to view history)"):
    if os.path.exists("threat_log.txt"):
        with open("threat_log.txt", "r") as f:
            logs = f.readlines()[-10:] # 只讀取最後 10 筆
            for log in reversed(logs):
                # 這裡假設你的 log 格式是 時間,PID,類型
                parts = log.strip().split(',')
                if len(parts) == 3:
                    st.write(f"🕒 **{parts[0]}** | 💀 PID: `{parts[1]}` | 類別: `{parts[2]}`")
    else:
        st.write("No threats recorded yet.")

# ==========================================
# 3. Execution & Process Lifecycle Logging
# ==========================================
st.subheader("2. Benchmarking Engine")

if st.button("Execute Profile Run", type="primary"):
    with st.spinner("Spawning process wrappers (time/strace) and initializing async watchdog thread..."):
        
        # 🌟 偵錯防線 1：檢查受測程式路徑到底對不對
        if not os.path.exists(program_path):
            st.error(f"❌ Target workload file not found at: `{program_path}`")
            st.info("Please verify that the 'examples/' directory exists and contains the target script.")
        else:
            # 🌟 偵錯防線 2：確保能同時抓到標準輸出 (stdout) 與錯誤輸出 (stderr)
            # 這樣萬一是 analyzer.py 本身當掉，我們才看得到原因
            cmd = [
                "python3", "analyzer.py",
                "--program", program_path,
                "--sizes", "500",
                "--repeats", str(repeats),
                "--mode", mode
            ]
            
            try:
                # 改用 capture_output=True 且不分流，讓 stderr 全部併入 stdout
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
                
                # UI Status Interceptor
                if "Watchdog Alert" in result.stdout:
                    st.error("⚠️ Policy Transgression Detected: Active Watchdog triggered SIGKILL termination.")
                elif result.returncode != 0:
                    st.warning(f"⚠️ Backend exited with non-zero code ({result.returncode}). See log below.")
                else:
                    st.success("Execution Completed: Target process terminated with Exit Code 0.")
                    
                # Core Stderr/Stdout Stream
                if result.stdout.strip():
                    st.text_area("Console Output (Kernel Stream Log)", value=result.stdout, height=250)
                else:
                    st.text_area("Console Output (Kernel Stream Log)", value="[Backend executed but returned no stdout/stderr stream output]", height=100)
                    
            except Exception as e:
                st.error(f"❌ Failed to execute benchmarking command: {str(e)}")

st.markdown("---")

# ==========================================
# 4. Embedded Analytical Visualizations
# ==========================================
st.subheader("3. Embedded Profiling Metrics")

# Parse target file properties to locate HTML asset
prog_name = Path(program_path).stem
report_file = Path(f"reports/{prog_name}-report.html")

if report_file.exists():
    st.caption(f"Active Report Asset: `{report_file.name}`")
    
    st.iframe(src=str(report_file), height=800)
else:
    st.info("Awaiting execution data. Trigger a profile run to populate metrics.")