FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends time strace \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m runner
USER runner
WORKDIR /work

CMD ["python", "--version"]
