FROM python:3.12-slim

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JAZN_ROOT=/opt/jazn \
    JAZN_MCP_BIND_HOST=0.0.0.0 \
    JAZN_MCP_PORT=8080 \
    JAZN_MCP_DAEMON_URL=http://127.0.0.1:8787

WORKDIR /opt/jazn
COPY . /opt/jazn

RUN python -m pip install --no-cache-dir ".[mcp-http]" \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin jazn \
    && mkdir -p /opt/jazn/workspace_runtime \
    && chown -R 10001:10001 /opt/jazn

USER 10001:10001

EXPOSE 8080
VOLUME ["/opt/jazn/workspace_runtime"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3); raise SystemExit(0 if r.status == 200 else 1)"

STOPSIGNAL SIGTERM\n\nENTRYPOINT ["python", "-X", "utf8", "-m", "latka_jazn.mcp.deployment"]
