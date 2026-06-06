#!/usr/bin/env python3
"""I/O-heavy demo: many small file writes and reads."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

def main() -> int:
    # 增加 n 的預設值，確保能製造足夠的壓力
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    checksum = 0
    
    with tempfile.TemporaryDirectory(prefix="algoscope-") as tmp:
        root = Path(tmp)
        
        # 增加寫入負載：每個檔案塞入更大的 payload
        for i in range(n):
            path = root / f"item-{i}.txt"
            # 讓 payload 變大，強制增加 IO 總量
            payload = f"{i},{i * i}," + ("x" * 1024) + "\n" 
            path.write_text(payload, encoding="utf-8")
            
            # 每寫入 50 個檔案稍微暫停，讓 Watchdog 有時間感應
            if i % 50 == 0:
                time.sleep(0.01)
        
        # 讀取負載
        for i in range(n):
            path = root / f"item-{i}.txt"
            content = path.read_text(encoding="utf-8")
            checksum += len(content)
            
    print(checksum)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
