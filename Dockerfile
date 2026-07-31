FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# No pip dependencies - stdlib only. Copying the source is the only "install" step.
COPY video_editor/ ./video_editor/

# Projects (JSON + copied media) are meant to be a mounted persistent volume
# in any real deployment - this default just gives a sane fallback for a
# plain `docker run` with no volume attached.
ENV PROJECTS_DIR=/data/projects
RUN mkdir -p /data/projects

EXPOSE 7777

ENTRYPOINT ["python3", "-m", "video_editor"]
