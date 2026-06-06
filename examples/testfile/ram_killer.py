import time
data = []
try:
    while True:
        # 每次增加 10MB
        data.append(' ' * (10 * 1024 * 1024)) 
        time.sleep(0.05)
except MemoryError:
    print("Memory exhausted!")
