FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
 && apt-get install -y --no-install-recommends \
    build-essential git m4 scons zlib1g zlib1g-dev \
    libprotobuf-dev protobuf-compiler libprotoc-dev \
    libgoogle-perftools-dev python3-dev python-is-python3 \
    libboost-all-dev pkg-config tmux \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
