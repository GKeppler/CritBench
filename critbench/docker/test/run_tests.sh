#!/usr/bin/env bash
# ==========================================================================
# run_tests.sh  —  IED server test battery
#
# Tests the running critbench-ied Docker container end-to-end:
#   1.  Health / liveness
#   2.  State API structure
#   3.  MMS data-model discovery
#   4.  MMS read — all key paths
#   5.  MMS write + state sync (SPCSO, AnIn, PTOC1)
#   6.  IEC 104 interrogation (via state API)
#   7.  State API IEC 104 write endpoint
#   8.  mms_client binary (relay channel)
#   9.  PTOC1 protection threshold state-API path correctness
#  10.  Concurrent write safety (parallel writes, no crash)
#
# Usage:
#   ./run_tests.sh [ied-host]
#   (default host: localhost, ports exposed via docker-compose: 18080 / 10102 / 12404)
#
# Prerequisites (run from the host, or from inside an agent container):
#   curl, python3   — available on most systems
#   c104            — only needed for test 6b (skipped if not installed)
#
# Exit code: 0 if all tests pass, 1 if any fail.
# ==========================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override via env or first positional argument
# ---------------------------------------------------------------------------
IED_HOST="${1:-localhost}"
STATE_PORT="${STATE_PORT:-18080}"           # host-mapped port for 8080
MMS_PORT="${MMS_PORT:-10102}"              # host-mapped port for 102
IEC104_PORT="${IEC104_PORT:-12404}"        # host-mapped port for 2404
MMS_CLIENT="${MMS_CLIENT:-/opt/libiec61850/bin/mms_client}"

# When running INSIDE the agent/ied container the ports are internal
if [ "${IED_HOST}" = "ied-server" ]; then
    STATE_PORT=8080
    MMS_PORT=102
    IEC104_PORT=2404
fi

STATE_API="http://${IED_HOST}:${STATE_PORT}"
MMS_HOST="${IED_HOST}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
SKIP=0

_pass() { echo "  [PASS] $1"; ((PASS++)) || true; }
_fail() { echo "  [FAIL] $1"; ((FAIL++)) || true; }
_skip() { echo "  [SKIP] $1"; ((SKIP++)) || true; }
_section() { echo; echo "── $1 ──────────────────────────────────────────"; }

require_curl() {
    if ! command -v curl &>/dev/null; then
        echo "ERROR: curl is required but not found." >&2
        exit 1
    fi
}

require_python() {
    if ! command -v python3 &>/dev/null; then
        echo "ERROR: python3 is required but not found." >&2
        exit 1
    fi
}

http_get() {
    curl -sf --max-time 5 "$1"
}

http_post_json() {
    curl -sf --max-time 5 -X POST -H "Content-Type: application/json" -d "$2" "$1"
}

# Navigate a JSON response by dot-path and return the leaf value (Python)
json_get() {
    local json="$1" path="$2"
    python3 - <<EOF
import json, sys
data = json.loads('''${json}''')
parts = "${path}".split(".")
cur = data
for p in parts:
    if isinstance(cur, dict) and p in cur:
        cur = cur[p]
    else:
        print("__MISSING__")
        sys.exit(0)
print(cur)
EOF
}

require_curl
require_python

echo "=========================================="
echo "  CritBench IED Server Test Battery"
echo "  Target: ${STATE_API}"
echo "=========================================="

# ===========================================================================
# 1. Health / liveness
# ===========================================================================
_section "1. Health / liveness"

resp=$(http_get "${STATE_API}/health") && true
if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
    _pass "GET /health → {status: ok}"
else
    _fail "GET /health — unexpected response: ${resp:-<no response>}"
fi

# ===========================================================================
# 2. State API — top-level structure
# ===========================================================================
_section "2. State API structure"

state=$(http_get "${STATE_API}/state") || { _fail "GET /state failed"; state="{}"; }

for key in mms iec104; do
    if echo "$state" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if '${key}' in d else 1)" 2>/dev/null; then
        _pass "GET /state contains key '${key}'"
    else
        _fail "GET /state missing key '${key}'"
    fi
done

for subkey in simpleIOGenericIO simpleIOprotection; do
    if echo "$state" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if '${subkey}' in d.get('mms',{}) else 1)" 2>/dev/null; then
        _pass "  mms.${subkey} exists"
    else
        _fail "  mms.${subkey} missing from state"
    fi
done

# IEC 104 common address 1 present
if echo "$state" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if '1' in d.get('iec104',{}) else 1)" 2>/dev/null; then
    _pass "  iec104.1 (common address) exists"
else
    _fail "  iec104.1 missing"
fi

# ===========================================================================
# 3. MMS data model discovery
# ===========================================================================
_section "3. MMS data-model discovery"

disc=$(http_get "${STATE_API}/mms/discover") || { _fail "GET /mms/discover failed"; disc="{}"; }

for ld in simpleIOGenericIO simpleIOprotection; do
    if echo "$disc" | python3 -c "
import json, sys
d = json.load(sys.stdin)
lds = [x['name'] for x in d.get('logicalDevices', [])]
sys.exit(0 if '${ld}' in lds else 1)" 2>/dev/null; then
        _pass "  discover: LD '${ld}' present"
    else
        _fail "  discover: LD '${ld}' missing"
    fi
done

# Check GGIO1 data objects
for do_name in SPCSO1 SPCSO2 SPCSO3 SPCSO4 Ind1 AnIn1 AnIn2; do
    if echo "$disc" | python3 -c "
import json, sys
d = json.load(sys.stdin)
dos = []
for ld in d.get('logicalDevices', []):
    for ln in ld.get('logicalNodes', []):
        dos.extend(ln.get('dataObjects', []))
sys.exit(0 if '${do_name}' in dos else 1)" 2>/dev/null; then
        _pass "  discover: DO '${do_name}' present"
    else
        _fail "  discover: DO '${do_name}' missing"
    fi
done

# PTOC1 StrVal
if echo "$disc" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for ld in d.get('logicalDevices', []):
    if ld['name'] == 'simpleIOprotection':
        for ln in ld.get('logicalNodes', []):
            if ln['name'] == 'PTOC1' and 'StrVal' in ln.get('dataObjects', []):
                sys.exit(0)
sys.exit(1)" 2>/dev/null; then
    _pass "  discover: PTOC1.StrVal in simpleIOprotection"
else
    _fail "  discover: PTOC1.StrVal missing from simpleIOprotection"
fi

# ===========================================================================
# 4. MMS reads — key paths
# ===========================================================================
_section "4. MMS read — key paths"

read_cases=(
    "simpleIOGenericIO/GGIO1\$CO\$SPCSO1\$ctlVal"
    "simpleIOGenericIO/GGIO1\$CO\$SPCSO2\$ctlVal"
    "simpleIOGenericIO/GGIO1\$CO\$SPCSO3\$ctlVal"
    "simpleIOGenericIO/GGIO1\$CO\$SPCSO4\$ctlVal"
    "simpleIOGenericIO/GGIO1\$ST\$Ind1\$stVal"
    "simpleIOGenericIO/GGIO1\$MX\$AnIn1\$mag\$f"
    "simpleIOGenericIO/GGIO1\$MX\$AnIn2\$mag\$f"
    "simpleIOprotection/PTOC1\$SP\$StrVal\$setMag\$f"
)

for ref in "${read_cases[@]}"; do
    resp=$(http_get "${STATE_API}/mms/read?ref=${ref}") || resp=""
    if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if 'value' in d else 1)" 2>/dev/null; then
        val=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin)['value'])")
        _pass "  read ${ref} → ${val}"
    else
        _fail "  read ${ref} — no 'value' in response: ${resp:-<empty>}"
    fi
done

# PTOC1 initial value should be 500.0
ptoc_resp=$(http_get "${STATE_API}/mms/read?ref=simpleIOprotection/PTOC1\$SP\$StrVal\$setMag\$f") || ptoc_resp=""
ptoc_val=$(echo "$ptoc_resp" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('value','__MISSING__'))" 2>/dev/null || echo "__ERR__")
if python3 -c "import sys; v=float('${ptoc_val}'); sys.exit(0 if abs(v-500.0)<1e-3 else 1)" 2>/dev/null; then
    _pass "  PTOC1.StrVal.setMag.f initial value = 500.0"
else
    _fail "  PTOC1.StrVal.setMag.f initial value wrong: ${ptoc_val} (expected 500.0)"
fi

# ===========================================================================
# 5. MMS write + state sync
# ===========================================================================
_section "5. MMS write + state sync"

# --- 5a. SPCSO2 ctlVal ---
resp=$(http_post_json "${STATE_API}/mms/write" '{"ref":"simpleIOGenericIO/GGIO1$CO$SPCSO2$ctlVal","value":true}') || resp=""
if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='written' else 1)" 2>/dev/null; then
    _pass "  write SPCSO2.ctlVal=true → status=written"
else
    _fail "  write SPCSO2.ctlVal failed: ${resp:-<empty>}"
fi

# Verify state reflects the write
state2=$(http_get "${STATE_API}/state") || state2="{}"
spcso2=$(echo "$state2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d['mms']['simpleIOGenericIO']['GGIO1']['CO']['SPCSO2']['ctlVal'])" 2>/dev/null || echo "__ERR__")
if [ "$spcso2" = "True" ] || [ "$spcso2" = "true" ]; then
    _pass "  state.mms.simpleIOGenericIO.GGIO1.CO.SPCSO2.ctlVal = true after write"
else
    _fail "  state.mms.simpleIOGenericIO.GGIO1.CO.SPCSO2.ctlVal = ${spcso2} (expected true)"
fi

# Reset
http_post_json "${STATE_API}/mms/write" '{"ref":"simpleIOGenericIO/GGIO1$CO$SPCSO2$ctlVal","value":false}' >/dev/null || true

# --- 5b. AnIn2 mag.f ---
resp=$(http_post_json "${STATE_API}/mms/write" '{"ref":"simpleIOGenericIO/GGIO1$MX$AnIn2$mag$f","value":77.5}') || resp=""
if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='written' else 1)" 2>/dev/null; then
    _pass "  write AnIn2.mag.f=77.5 → status=written"
else
    _fail "  write AnIn2.mag.f failed: ${resp:-<empty>}"
fi

state3=$(http_get "${STATE_API}/state") || state3="{}"
anin2=$(echo "$state3" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d['mms']['simpleIOGenericIO']['GGIO1']['MX']['AnIn2']['mag']['f'])" 2>/dev/null || echo "__ERR__")
if python3 -c "import sys; sys.exit(0 if abs(float('${anin2}')-77.5)<0.01 else 1)" 2>/dev/null; then
    _pass "  state.mms...AnIn2.mag.f = ${anin2} after write"
else
    _fail "  state.mms...AnIn2.mag.f = ${anin2} (expected ~77.5)"
fi

# Reset
http_post_json "${STATE_API}/mms/write" '{"ref":"simpleIOGenericIO/GGIO1$MX$AnIn2$mag$f","value":0}' >/dev/null || true

# --- 5c. PTOC1 StrVal setMag.f ---
resp=$(http_post_json "${STATE_API}/mms/write" '{"ref":"simpleIOprotection/PTOC1$SP$StrVal$setMag$f","value":9999.0}') || resp=""
if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='written' else 1)" 2>/dev/null; then
    _pass "  write PTOC1.StrVal.setMag.f=9999.0 → status=written"
else
    _fail "  write PTOC1.StrVal.setMag.f failed: ${resp:-<empty>}"
fi

state4=$(http_get "${STATE_API}/state") || state4="{}"
ptoc_after=$(echo "$state4" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d['mms']['simpleIOprotection']['PTOC1']['SP']['StrVal']['setMag']['f'])" 2>/dev/null || echo "__ERR__")
if python3 -c "import sys; sys.exit(0 if abs(float('${ptoc_after}')-9999.0)<0.1 else 1)" 2>/dev/null; then
    _pass "  state.mms.simpleIOprotection.PTOC1.SP.StrVal.setMag.f = ${ptoc_after}"
else
    _fail "  PTOC1 state after write: ${ptoc_after} (expected 9999.0)"
fi

# Reset
http_post_json "${STATE_API}/mms/write" '{"ref":"simpleIOprotection/PTOC1$SP$StrVal$setMag$f","value":500.0}' >/dev/null || true

# --- 5d. Write non-existent path → should fail gracefully ---
resp_bad=$(http_post_json "${STATE_API}/mms/write" '{"ref":"nonexistent/path","value":1}' 2>/dev/null) || resp_bad="ERROR"
if echo "$resp_bad" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if 'error' in d or d.get('status')=='written' else 1)" 2>/dev/null; then
    _pass "  write to non-existent path handled (no 500 crash)"
else
    _fail "  write to non-existent path caused unexpected response: ${resp_bad}"
fi

# ===========================================================================
# 6. IEC 104 — state API interrogation endpoint
# ===========================================================================
_section "6. IEC 104 state API"

iec_state=$(http_get "${STATE_API}/iec104/state") || iec_state="{}"

for ioa in 11 12 21 22 51 52; do
    if echo "$iec_state" | python3 -c "
import json,sys
d=json.load(sys.stdin)
# response is dict keyed by CA, or direct IOA dict
data = d.get('1', d)
sys.exit(0 if '${ioa}' in data else 1)" 2>/dev/null; then
        val=$(echo "$iec_state" | python3 -c "
import json,sys
d=json.load(sys.stdin)
data = d.get('1', d)
print(data['${ioa}']['value'])" 2>/dev/null || echo "?")
        _pass "  iec104/state IOA ${ioa} → value=${val}"
    else
        _fail "  iec104/state missing IOA ${ioa}"
    fi
done

# IEC 104 write endpoint
resp=$(http_post_json "${STATE_API}/iec104/write" '{"common_address":1,"ioa":51,"value":true,"type":"C_SC_NA_1"}') || resp=""
if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='written' else 1)" 2>/dev/null; then
    _pass "  POST /iec104/write IOA=51 value=true → written"
else
    _fail "  POST /iec104/write failed: ${resp:-<empty>}"
fi

# Verify state updated
iec2=$(http_get "${STATE_API}/iec104/state?ca=1") || iec2="{}"
ioa51_val=$(echo "$iec2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('51',{}).get('value','__MISSING__'))" 2>/dev/null || echo "__ERR__")
if [ "$ioa51_val" = "True" ] || [ "$ioa51_val" = "true" ]; then
    _pass "  iec104.1.51.value = true after write"
else
    _fail "  iec104.1.51.value = ${ioa51_val} after write (expected true)"
fi

# Reset
http_post_json "${STATE_API}/iec104/write" '{"common_address":1,"ioa":51,"value":false,"type":"C_SC_NA_1"}' >/dev/null || true

# Setpoint float
resp=$(http_post_json "${STATE_API}/iec104/write" '{"common_address":1,"ioa":52,"value":42.5,"type":"C_SE_NC_1"}') || resp=""
if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='written' else 1)" 2>/dev/null; then
    iec3=$(http_get "${STATE_API}/iec104/state?ca=1") || iec3="{}"
    ioa52_val=$(echo "$iec3" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('52',{}).get('value','__MISSING__'))" 2>/dev/null || echo "__ERR__")
    if python3 -c "import sys; sys.exit(0 if abs(float('${ioa52_val}')-42.5)<0.01 else 1)" 2>/dev/null; then
        _pass "  iec104.1.52.value = ${ioa52_val} after setpoint write"
    else
        _fail "  iec104.1.52.value = ${ioa52_val} (expected 42.5)"
    fi
else
    _fail "  POST /iec104/write (setpoint) failed: ${resp:-<empty>}"
fi

# Reset
http_post_json "${STATE_API}/iec104/write" '{"common_address":1,"ioa":52,"value":0.0,"type":"C_SE_NC_1"}' >/dev/null || true

# ===========================================================================
# 7. mms_client binary (relay tool)
# ===========================================================================
_section "7. mms_client binary"

if [ -x "${MMS_CLIENT}" ]; then
    # Read PTOC1 via native MMS
    read_out=$("${MMS_CLIENT}" -h "${MMS_HOST}" -p "${MMS_PORT}" read \
        "simpleIOprotection/PTOC1\$SP\$StrVal\$setMag\$f" 2>/dev/null) || read_out=""
    if echo "$read_out" | grep -qiE '500|float|value'; then
        _pass "  mms_client read PTOC1.StrVal.setMag.f → ${read_out}"
    else
        _fail "  mms_client read returned unexpected: ${read_out:-<empty>}"
    fi

    # Write PTOC1 via native MMS
    write_out=$("${MMS_CLIENT}" -h "${MMS_HOST}" -p "${MMS_PORT}" write \
        "simpleIOprotection/PTOC1\$SP\$StrVal\$setMag\$f" "1234.0" 2>/dev/null) || write_out=""
    if echo "$write_out" | grep -qiE 'success|written|ok|1234'; then
        _pass "  mms_client write PTOC1.StrVal.setMag.f=1234.0 → ok"
    else
        _fail "  mms_client write returned: ${write_out:-<empty>}"
    fi
    # Reset via state API (avoid leaving test value)
    http_post_json "${STATE_API}/mms/write" \
        '{"ref":"simpleIOprotection/PTOC1$SP$StrVal$setMag$f","value":500.0}' >/dev/null || true

    # Discover via native MMS
    disc_out=$("${MMS_CLIENT}" -h "${MMS_HOST}" -p "${MMS_PORT}" discover 2>/dev/null | head -20) || disc_out=""
    if echo "$disc_out" | grep -qi 'simpleIO'; then
        _pass "  mms_client discover contains 'simpleIO'"
    else
        _fail "  mms_client discover returned: ${disc_out:-<empty>}"
    fi
else
    _skip "  mms_client not found at ${MMS_CLIENT} — skipping native MMS tests"
fi

# ===========================================================================
# 8. PTOC1 C-server → state API notify path correctness
# ===========================================================================
_section "8. PTOC1 C-server → state API path consistency"

# The C server calls notify_state_api("protection.PTOC1.StrVal.setMag.f", ...)
# but the state dict key is "simpleIOprotection".
# After a native write via mms_client, check which key in state dict is updated.
if [ -x "${MMS_CLIENT}" ]; then
    # Write 8765.0 via native MMS — this triggers notify_state_api in the C server
    "${MMS_CLIENT}" -h "${MMS_HOST}" -p "${MMS_PORT}" write \
        "simpleIOprotection/PTOC1\$SP\$StrVal\$setMag\$f" "8765.0" 2>/dev/null || true

    sleep 0.5  # allow the async notify to arrive

    state_n=$(http_get "${STATE_API}/state") || state_n="{}"

    # Check the correct key path
    correct_val=$(echo "$state_n" | python3 -c "
import json,sys
d=json.load(sys.stdin)
try:
    print(d['mms']['simpleIOprotection']['PTOC1']['SP']['StrVal']['setMag']['f'])
except KeyError:
    print('__MISSING__')" 2>/dev/null || echo "__ERR__")

    short_val=$(echo "$state_n" | python3 -c "
import json,sys
d=json.load(sys.stdin)
try:
    print(d['mms']['protection']['PTOC1']['StrVal']['setMag']['f'])
except KeyError:
    print('__MISSING__')" 2>/dev/null || echo "__MISSING__")

    if python3 -c "import sys; sys.exit(0 if abs(float('${correct_val}')-8765.0)<1.0 else 1)" 2>/dev/null; then
        _pass "  C-server notify updates mms.simpleIOprotection (correct path)"
    else
        _fail "  mms.simpleIOprotection.PTOC1.SP.StrVal.setMag.f = ${correct_val} after native write (expected ~8765.0)"
        if python3 -c "import sys; sys.exit(0 if abs(float('${short_val}')-8765.0)<1.0 else 1)" 2>/dev/null; then
            _fail "  → notify wrote to mms.protection (SHORT key) instead of mms.simpleIOprotection — path mismatch in critbench_ied_server.c"
        fi
    fi

    # Reset
    http_post_json "${STATE_API}/mms/write" \
        '{"ref":"simpleIOprotection/PTOC1$SP$StrVal$setMag$f","value":500.0}' >/dev/null || true
else
    _skip "  mms_client not available — skipping C-server notify path test"
fi

# ===========================================================================
# 9. Concurrent write safety
# ===========================================================================
_section "9. Concurrent write safety"

# Fire 10 parallel writes and verify the server is still up afterwards
for i in $(seq 1 10); do
    http_post_json "${STATE_API}/mms/write" \
        "{\"ref\":\"simpleIOGenericIO/GGIO1\$CO\$SPCSO${i%4+1}\$ctlVal\",\"value\":true}" \
        >/dev/null 2>&1 &
done
wait

health2=$(http_get "${STATE_API}/health") || health2=""
if echo "$health2" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
    _pass "  server still alive after 10 concurrent writes"
else
    _fail "  server did not respond to /health after concurrent writes"
fi

# ===========================================================================
# Summary
# ===========================================================================
echo
echo "=========================================="
echo "  Results: ${PASS} passed  |  ${FAIL} failed  |  ${SKIP} skipped"
echo "=========================================="

[ "${FAIL}" -eq 0 ]
