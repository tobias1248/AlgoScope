import psutil, signal, time, os, datetime, threading

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

def get_last_threat_log():
    if not os.path.exists("threat_log.txt"):
        return None
    try:
        with open("threat_log.txt", "r") as f:
            lines = f.readlines()
            return lines[-1].strip() if lines else None
    except:
        return None

class SentinelRunner:
    _running = False
    _thread = None

    @classmethod
    def start(cls):
        if not cls._running:
            cls._running = True
            cls._thread = threading.Thread(target=cls.sentinel_mode, daemon=True)
            cls._thread.start()

    @classmethod
    def stop(cls):
        cls._running = False

    @staticmethod
    def sentinel_mode():
        print("System Sentinel Active...")
        while SentinelRunner._running:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'num_threads']):
                try:
                    rss_mb = (proc.info['memory_info'].rss / (1024 * 1024)) if proc.info['memory_info'] else 0
                    cpu = proc.info['cpu_percent'] or 0
                    num_threads = proc.info['num_threads'] or 0
                    
                    violation_reasons = []
                    if cpu > 80.0: violation_reasons.append(f"CPU({cpu:.1f}%)")
                    if rss_mb > 1000: violation_reasons.append(f"MEM({rss_mb:.0f}MB)")
                    if num_threads > 200: violation_reasons.append(f"THR({num_threads})")

                    if violation_reasons:
                        if proc.pid != os.getpid() and "python" in proc.info['name'].lower():
                            if is_managed_process(proc): continue
                            
                            reason_str = "+".join(violation_reasons)
                            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
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