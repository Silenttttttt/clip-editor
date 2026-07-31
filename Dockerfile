FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# No pip dependencies - stdlib only. Copying the source is the only "install" step.
COPY clip_editor/ ./clip_editor/

# Projects (JSON + copied media) are meant to be a mounted persistent volume
# in any real deployment - this default just gives a sane fallback for a
# plain `docker run` with no volume attached.
ENV PROJECTS_DIR=/data/projects
RUN mkdir -p /data/projects

# Unbuffered stdout - matches the original script's own systemd unit
# (`python3 -u ...`). Without this, print()'d job/request logs sit in
# Python's block buffer (stdout isn't a TTY in a container) and never
# reach `docker logs`/`kubectl logs` until the buffer fills or the
# process exits - confirmed live: logs were empty during a real, working
# request until this was added.
ENV PYTHONUNBUFFERED=1

EXPOSE 7777

ENTRYPOINT ["python3", "-m", "clip_editor"]
