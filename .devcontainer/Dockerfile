FROM mcr.microsoft.com/devcontainers/python:1-3.13-bookworm

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
       libatomic1 \
       ffmpeg \
       libturbojpeg0 \
       libpcap-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/local/bin/python /bin/python3
RUN rm -f /etc/apt/sources.list.d/yarn.list
RUN pip install --upgrade pip
