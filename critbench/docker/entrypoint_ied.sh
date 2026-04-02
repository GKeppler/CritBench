#!/usr/bin/env bash
#
# Entrypoint for the IED server container.
# Starts the libiec61850 MMS server, an IEC 104 server stub,
# and the HTTP state API — all in the background — then waits.
#
set -e

echo "[entrypoint] Starting IED services …"

# 1. Start libiec61850 MMS server (port 102)
#    Use GOOSE_INTERFACE env var (default: eth0) for GOOSE multicast.
GOOSE_IFACE="${GOOSE_INTERFACE:-eth0}"
if [ -x /opt/iec61850/critbench_ied_server ]; then
    echo "[entrypoint]  → MMS server (port 102, GOOSE on ${GOOSE_IFACE})"
    GOOSE_INTERFACE="${GOOSE_IFACE}" /opt/iec61850/critbench_ied_server &
    MMS_PID=$!
else
    echo "[entrypoint]  ⚠ critbench_ied_server binary not found, skipping"
    MMS_PID=""
fi

# 2. Start IEC 104 server stub (port 2404)
#    lib60870 examples or a simple c104-based Python script
if [ -f /opt/iec104/iec104_server.py ]; then
    echo "[entrypoint]  → IEC 104 server (port 2404)"
    python3 /opt/iec104/iec104_server.py &
    IEC104_PID=$!
else
    echo "[entrypoint]  ⚠ IEC 104 server not found, skipping"
    IEC104_PID=""
fi

# 3. Start HTTP state API (port 8080)
echo "[entrypoint]  → State API (port 8080)"
python3 /opt/state_api/ied_state_api.py &
STATE_PID=$!

# Wait for any child to exit (or trap signals)
trap 'echo "[entrypoint] Shutting down …"; kill $MMS_PID $IEC104_PID $STATE_PID 2>/dev/null; wait' SIGTERM SIGINT

echo "[entrypoint] All services started. Waiting …"
wait
