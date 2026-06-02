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

st.subheader("Live Threat Map (Real-time Audit)")

# 讀取威脅計數
if not os.path.exists("threat_log.txt"): open("threat_log.txt", "w").close()
with open("threat_log.txt", "r") as f: threat_count = len(f.readlines())

col1, col2, col3 = st.columns(3)
col1.metric("CPU Load", f"{psutil.cpu_percent()}%")
col2.metric("Threats Blocked", threat_count)
col3.metric("System Status", "🛡️ Running" if "sentinel_pid" in st.session_state else "💤 IDLE")

# CPU 波動圖
cpu_history = [psutil.cpu_percent(interval=0.1) for _ in range(30)]
st.line_chart(cpu_history)

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