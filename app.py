import streamlit as st
import subprocess
import psutil
import time
import os
import glob 
import signal
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
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
    # 啟動邏輯
    if "sentinel_pid" not in st.session_state:
        p = subprocess.Popen(["python3", "sentinel.py"])
        st.session_state.sentinel_pid = p.pid
        st.sidebar.success(f"Sentinel running (PID: {p.pid})")
    # 增加：如果 PID 記錄還在，但其實進程已經死掉，幫使用者重啟
    elif not psutil.pid_exists(st.session_state.sentinel_pid):
        del st.session_state.sentinel_pid
        st.rerun()

else:
    # 關閉邏輯
    if "sentinel_pid" in st.session_state:
        target_pid = st.session_state.sentinel_pid
        
        # [核心修正] 檢查 PID 是否真的存在，避免 ProcessLookupError
        if psutil.pid_exists(target_pid):
            try:
                os.kill(target_pid, signal.SIGKILL)
                st.sidebar.warning(f"Sentinel (PID: {target_pid}) killed.")
            except Exception as e:
                st.sidebar.error(f"Kill failed: {e}")
        else:
            st.sidebar.info("Sentinel process already gone.")
            
        # 無論是否成功殺掉，都要清除 session_state 記錄
        del st.session_state.sentinel_pid

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
                # 這裡修正為 len(parts) >= 3，或者直接檢查是否為 4
                parts = log.strip().split(',')
                if len(parts) >= 4:
                    # 加入顯示「原因 (reason)」的欄位
                    time_str = parts[0]
                    pid_str = parts[1]
                    status_str = parts[2]
                    reason_str = parts[3]
                    
                    st.write(f"🕒 **{time_str}** | PID: `{pid_str}` | 類別: `{status_str}` | 原因: `{reason_str}`")
                elif len(parts) == 3:
                    # 處理舊版的 Log (如果還有舊格式)
                    st.write(f"🕒 **{parts[0]}** | PID: `{parts[1]}` | 類別: `{parts[2]}`")
    else:
        st.write("No threats recorded yet.")

# ==========================================
# 3. Execution & Process Lifecycle Logging
# ==========================================
st.subheader("2. Benchmarking Engine")

if st.button("Execute Profile Run", type="primary"):
    with st.spinner("Initializing Benchmarking Engine..."):
        # 1. 定義絕對路徑，消除環境差異
        abs_program_path = os.path.abspath(program_path)
        abs_analyzer_path = os.path.abspath("analyzer.py")
        abs_cwd = os.getcwd() # 獲取當前專案根目錄
        
        # 2. 構建指令
        cmd = [
            "python3", abs_analyzer_path,
            "--program", abs_program_path,
            "--sizes", "100", "200", "300", "400", "500",
            "--repeats", str(repeats),
            "--mode", mode  # 直接傳入 UI 選擇的 'normal' 或 'eco'
        ]
        
        # 3. 複製當前環境並加入專案路徑，解決 ModuleNotFound 問題
        my_env = os.environ.copy()
        my_env["PYTHONPATH"] = abs_cwd
        
        try:
            # 執行分析器
            result = subprocess.run(
                cmd, 
                env=my_env,          # 注入環境變數
                cwd=abs_cwd,         # 強制在專案根目錄執行
                capture_output=True, # 完整捕捉錯誤輸出
                text=True, 
                timeout=60
            )
            
            # 處理輸出
            if result.returncode == 0:
                st.success("Execution Completed Successfully.")
                st.text_area("Console Output", value=result.stdout, height=200)
            else:
                st.error(f"❌ Backend returned exit code {result.returncode}")
                # 這裡會顯示導致失敗的詳細原因（如 psutil 缺失或路徑錯誤）
                st.error("Error Details:")
                st.text_area("Stderr", value=result.stderr, height=300)
                
        except Exception as e:
            st.error(f"❌ Execution Failure: {str(e)}")
            st.code(f"Command attempted: {' '.join(cmd)}")

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
