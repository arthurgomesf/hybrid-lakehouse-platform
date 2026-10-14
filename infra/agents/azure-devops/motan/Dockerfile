FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    jq \
    libicu70 \
    python3 \
    python3-pip \
    tar \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o azcopy.tar.gz https://aka.ms/downloadazcopy-v10-linux \
    && tar -xzf azcopy.tar.gz \
    && cp ./azcopy_linux_amd64_*/azcopy /usr/local/bin/azcopy \
    && chmod +x /usr/local/bin/azcopy \
    && rm -rf azcopy.tar.gz azcopy_linux_amd64_*

RUN useradd --create-home --shell /bin/bash azp

WORKDIR /azp

COPY start.sh .
RUN chmod +x start.sh && chown -R azp:azp /azp

USER azp

CMD ["./start.sh"]
