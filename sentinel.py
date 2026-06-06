import psutil
import signal
import time
import os
import datetime

def is_managed_process(proc):
    try:
        parent = proc.parent()
        for _ in range(5):
            if parent is None: break
            cmdline = " ".join(parent.cmdline())
            if "analyzer.py" in cmdline or "app.py" in cmdline:
                return True
            parent = parent.parent()
    except:
        pass
    return False

def sentinel_mode():
    print("System Sentinel Active...")
    while True:
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'num_threads']):
            try:
                rss_mb = (proc.info['memory_info'].rss / (1024 * 1024)) if proc.info['memory_info'] else 0
                cpu = proc.info['cpu_percent'] or 0
                num_threads = proc.info['num_threads'] or 0
                
                # 1. 進行個別檢查並記錄原因
                violation_reasons = []
                if cpu > 80.0: violation_reasons.append(f"CPU({cpu:.1f}%)")
                if rss_mb > 1000: violation_reasons.append(f"MEM({rss_mb:.0f}MB)")
                if num_threads > 200: violation_reasons.append(f"THR({num_threads})")

                # 2. 如果有違規，進行記錄並撲殺
                if violation_reasons:
                    if proc.pid != os.getpid() and "python" in proc.info['name'].lower():
                        if is_managed_process(proc): continue
                        
                        # 合併原因，例如: "CPU(85.2%)+MEM(1200MB)"
                        reason_str = "+".join(violation_reasons)
                        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 寫入日誌
                        log_entry = f"{now},{proc.pid},MALICIOUS,{reason_str}\n"
                        with open("threat_log.txt", "a") as f:
                            f.write(log_entry)
                            f.flush()
                            os.fsync(f.fileno())
                            
                        print(f"[{now}] 🔥 Kill PID: {proc.pid} | Reason: {reason_str}")
                        proc.send_signal(signal.SIGKILL)
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        time.sleep(0.5) 

if __name__ == "__main__":
    sentinel_mode()
