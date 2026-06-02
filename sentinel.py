import psutil
import signal
import time
import os
import datetime  # 必須加上這行，否則會報錯

def is_managed_process(proc):
    """檢查該進程是否屬於 AlgoScope 家族"""
    try:
        parent = proc.parent()
        for _ in range(5):
            if parent is None: break
            # 檢查父進程的指令列，確認是否包含 analyzer.py 或 app.py
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
        # 修正縮排：將 for 和 try 對齊
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'num_threads']):
            try:
                # 監控條件
                if (proc.info['cpu_percent'] > 80.0 or 
                    (proc.info['memory_percent'] or 0) > 40.0 or 
                    (proc.info['num_threads'] or 0) > 200):
                    
                    if proc.pid != os.getpid() and proc.info['name'] == 'python3':
                        msg = "Managed" if is_managed_process(proc) else "MALICIOUS"
                        
                        # 紀錄並撲殺
                        now = datetime.datetime.now().strftime("%H:%M:%S")
                        print(f"[{now}] 🔥 Detected {msg} Process: {proc.pid}, Killing...")
                        
                        # 寫入威脅紀錄檔 (供 app.py 讀取計數)
                        with open("threat_log.txt", "a") as f:
                            f.write("1\n")
                            
                        proc.send_signal(signal.SIGKILL)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        time.sleep(0.5)

if __name__ == "__main__":
    sentinel_mode()