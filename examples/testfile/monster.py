#!/usr/bin/env python3
"""Active Watchdog Demo: A pure CPU & Memory Monster."""
import sys
import time

def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    print(f"[Monster] Starting computation for N={n}...")
    
    # 1. 故意引發記憶體與 CPU 暴走
    # 建立一個極大的 List 塞滿記憶體
    monster_leak = []
    
    for i in range(n * 2000):
        # 狂塞字串，把記憶體頂上去（引發記憶體看門狗）
        monster_leak.append("X" * 10000) 
        
        # 狂做無意義運算，把單核 CPU 頂到 100%（引發 CPU 看門狗）
        if i % 10 == 0:
            _ = [x**2 for x in range(2000)]
            
    print("[Monster] Done!") # 如果被殺掉，這行絕對印不出來
    return 0

if __name__ == "__main__":
    raise SystemExit(main())