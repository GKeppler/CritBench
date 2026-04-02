/*
 * critbench_ied_server.c
 *
 * Custom IEC 61850 MMS + GOOSE server for CritBench VM-interaction tasks.
 *
 * Architecture
 * ============
 * This server replaces the stock server_example_basic_io.  Key differences:
 *
 *   1. DYNAMIC model (uses IedModel_create / CDC_* API from server_example_dynamic).
 *      No static_model.c/h compilation step required.
 *
 *   2. Two Logical Devices are created at startup:
 *        · GenericIO  (IEDname "simpleIO" → MMS name "simpleIOGenericIO")
 *           - LLN0, LPHD1
 *           - GGIO1: AnIn1-4 (MX), SPCSO1-4 (CO/ST), Ind1-4 (ST)
 *           - GOOSE GCB (gcb01) publishing SPCSO stVals and Ind stVals
 *        · protection  (MMS name "simpleIOprotection")
 *           - LLN0, PTOC1: StrVal (SP, ASG CDC) — protection threshold setting
 *
 *   3. Write/control handlers notify the HTTP state API on localhost:8080
 *      via a simple raw-socket HTTP POST.  This keeps the Python state dict
 *      in sync with the real MMS model so the evaluator can read final state.
 *
 *   4. GOOSE is published on the interface specified by the GOOSE_INTERFACE
 *      environment variable (default: eth0).  When SPCSO stVal or Ind stVal
 *      changes (via control handler or direct ST write), libiec61850 detects
 *      the GOOSE dataset member change and re-publishes with incremented stNum.
 *
 * Build (inside container after libiec61850 install):
 *   gcc -o /opt/iec61850/critbench_ied_server critbench_ied_server.c \
 *       -I/usr/local/include/libiec61850 \
 *       -liec61850 -lpthread -lm
 *
 * Usage: critbench_ied_server [tcp-port]
 */

#include "iec61850_server.h"
#include "hal_thread.h"

#include <arpa/inet.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* ======================================================================
 * Global state
 * ====================================================================== */

static volatile int running = 0;
static IedServer iedServer = NULL;

/* DataAttribute pointers — populated during model creation */
/* GGIO1 Ind stVals */
static DataAttribute *g_ind1_stVal, *g_ind2_stVal, *g_ind3_stVal, *g_ind4_stVal;
/* GGIO1 AnIn mag.f */
static DataAttribute *g_anIn1_magf, *g_anIn2_magf, *g_anIn3_magf, *g_anIn4_magf;
/* GGIO1 SPCSO DataObject pointers (for control-handler dispatch) */
static DataObject *g_spcso1_do, *g_spcso2_do, *g_spcso3_do, *g_spcso4_do;
/* GGIO1 SPCSO stVals (updated by control handler; drives GOOSE) */
static DataAttribute *g_spcso1_stVal, *g_spcso2_stVal, *g_spcso3_stVal, *g_spcso4_stVal;
/* PTOC1 StrVal setMag.f */
static DataAttribute *g_ptoc1_setMag_f;

/* ======================================================================
 * Notify state API
 * ====================================================================== */

/*
 * notify_state_api() — fire-and-forget HTTP POST to
 *   POST http://127.0.0.1:8080/mms/write
 *   Body: {"ref":"<path>","value":<value_json>}
 *
 * <path>  uses dot-separated STATE["mms"] keys, e.g.:
 *   "simpleIOGenericIO.GGIO1.ST.Ind1.stVal"
 *   "simpleIOGenericIO.GGIO1.CO.SPCSO1.ctlVal"
 *   "protection.PTOC1.StrVal.setMag.f"
 *
 * <value_json> is a JSON literal (true, false, or a float string).
 */
static void notify_state_api(const char *path, const char *value_json)
{
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0)
        return;

    struct timeval tv;
    tv.tv_sec = 1;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(8080);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sock);
        return;
    }

    char body[512];
    /* value_json is either "true", "false", or a numeric literal    */
    /* Booleans must be unquoted; floats unquoted — already correct. */
    snprintf(body, sizeof(body), "{\"ref\":\"%s\",\"value\":%s}", path, value_json);

    char req[1024];
    int n = snprintf(req, sizeof(req),
        "POST /mms/write HTTP/1.0\r\n"
        "Host: 127.0.0.1:8080\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: %zu\r\n"
        "Connection: close\r\n"
        "\r\n%s",
        strlen(body), body);

    send(sock, req, n, MSG_NOSIGNAL);
    /* Drain + discard the response to keep the connection clean */
    char buf[64];
    while (recv(sock, buf, sizeof(buf), 0) > 0)
        ;
    close(sock);
}

/* ======================================================================
 * Write handler — ST and MX attributes
 * ====================================================================== */

static MmsDataAccessError
writeHandler(DataAttribute *da, MmsValue *value,
             ClientConnection connection, void *parameter)
{
    (void)connection;
    (void)parameter;

    /* --- Ind1-4 stVal -------------------------------------------- */
    if (da == g_ind1_stVal || da == g_ind2_stVal ||
        da == g_ind3_stVal || da == g_ind4_stVal)
    {
        if (MmsValue_getType(value) != MMS_BOOLEAN)
            return DATA_ACCESS_ERROR_TYPE_INCONSISTENT;

        const char *v = MmsValue_getBoolean(value) ? "true" : "false";
        if (da == g_ind1_stVal)
            notify_state_api("simpleIOGenericIO.GGIO1.ST.Ind1.stVal", v);
        else if (da == g_ind2_stVal)
            notify_state_api("simpleIOGenericIO.GGIO1.ST.Ind2.stVal", v);
        else if (da == g_ind3_stVal)
            notify_state_api("simpleIOGenericIO.GGIO1.ST.Ind3.stVal", v);
        else
            notify_state_api("simpleIOGenericIO.GGIO1.ST.Ind4.stVal", v);
        return DATA_ACCESS_ERROR_SUCCESS;
    }

    /* --- SPCSO1-4 stVal (relayed from state API) ------------------- */
    /* Direct writes to stVal from the relay trigger GOOSE re-pub.    */
    if (da == g_spcso1_stVal || da == g_spcso2_stVal ||
        da == g_spcso3_stVal || da == g_spcso4_stVal)
    {
        if (MmsValue_getType(value) != MMS_BOOLEAN)
            return DATA_ACCESS_ERROR_TYPE_INCONSISTENT;
        /* The state API already updated ctlVal; just accept the write  */
        /* so libiec61850 updates stVal and GOOSE re-publishes.         */
        return DATA_ACCESS_ERROR_SUCCESS;
    }

    /* --- AnIn1-4 mag.f -------------------------------------------- */
    if (da == g_anIn1_magf || da == g_anIn2_magf ||
        da == g_anIn3_magf || da == g_anIn4_magf)
    {
        if (MmsValue_getType(value) != MMS_FLOAT)
            return DATA_ACCESS_ERROR_TYPE_INCONSISTENT;

        char fv[64];
        snprintf(fv, sizeof(fv), "%g", MmsValue_toFloat(value));
        if (da == g_anIn1_magf)
            notify_state_api("simpleIOGenericIO.GGIO1.MX.AnIn1.mag.f", fv);
        else if (da == g_anIn2_magf)
            notify_state_api("simpleIOGenericIO.GGIO1.MX.AnIn2.mag.f", fv);
        else if (da == g_anIn3_magf)
            notify_state_api("simpleIOGenericIO.GGIO1.MX.AnIn3.mag.f", fv);
        else
            notify_state_api("simpleIOGenericIO.GGIO1.MX.AnIn4.mag.f", fv);
        return DATA_ACCESS_ERROR_SUCCESS;
    }

    /* --- PTOC1 StrVal setMag.f (protection threshold) -------------- */
    if (da == g_ptoc1_setMag_f)
    {
        float v = MmsValue_toFloat(value);
        char fv[64];
        snprintf(fv, sizeof(fv), "%g", v);
        /* Key must match STATE["mms"]["simpleIOprotection"] in ied_state_api.py */
        notify_state_api("simpleIOprotection.PTOC1.SP.StrVal.setMag.f", fv);
        return DATA_ACCESS_ERROR_SUCCESS;
    }

    return DATA_ACCESS_ERROR_OBJECT_ACCESS_DENIED;
}

/* ======================================================================
 * Control handler — SPCSO1-4 (direct-normal)
 * ====================================================================== */

static ControlHandlerResult
controlHandler(ControlAction action, void *parameter,
               MmsValue *value, bool test)
{
    (void)action;
    if (test)
        return CONTROL_RESULT_FAILED;

    if (MmsValue_getType(value) != MMS_BOOLEAN)
        return CONTROL_RESULT_FAILED;

    bool bVal = MmsValue_getBoolean(value);
    const char *v = bVal ? "true" : "false";
    uint64_t ts = Hal_getTimeInMs();

    MmsValue *boolVal = MmsValue_newBoolean(bVal);

    if (parameter == g_spcso1_do) {
        IedServer_updateUTCTimeAttributeValue(iedServer, g_spcso1_stVal, ts);
        IedServer_updateAttributeValue(iedServer, g_spcso1_stVal, boolVal);
        notify_state_api("simpleIOGenericIO.GGIO1.CO.SPCSO1.ctlVal", v);
    } else if (parameter == g_spcso2_do) {
        IedServer_updateUTCTimeAttributeValue(iedServer, g_spcso2_stVal, ts);
        IedServer_updateAttributeValue(iedServer, g_spcso2_stVal, boolVal);
        notify_state_api("simpleIOGenericIO.GGIO1.CO.SPCSO2.ctlVal", v);
    } else if (parameter == g_spcso3_do) {
        IedServer_updateUTCTimeAttributeValue(iedServer, g_spcso3_stVal, ts);
        IedServer_updateAttributeValue(iedServer, g_spcso3_stVal, boolVal);
        notify_state_api("simpleIOGenericIO.GGIO1.CO.SPCSO3.ctlVal", v);
    } else if (parameter == g_spcso4_do) {
        IedServer_updateUTCTimeAttributeValue(iedServer, g_spcso4_stVal, ts);
        IedServer_updateAttributeValue(iedServer, g_spcso4_stVal, boolVal);
        notify_state_api("simpleIOGenericIO.GGIO1.CO.SPCSO4.ctlVal", v);
    }

    MmsValue_delete(boolVal);
    return CONTROL_RESULT_OK;
}

/* ======================================================================
 * Signal handler
 * ====================================================================== */

static void sigint_handler(int sig)
{
    (void)sig;
    running = 0;
}

/* ======================================================================
 * main
 * ====================================================================== */

int main(int argc, char **argv)
{
    int tcpPort = 102;
    if (argc > 1)
        tcpPort = atoi(argv[1]);

    /* ------------------------------------------------------------------
     * Network interface for GOOSE publishing.
     * Reads GOOSE_INTERFACE env var; falls back to "eth0".
     * ------------------------------------------------------------------ */
    const char *gooseIface = getenv("GOOSE_INTERFACE");
    if (!gooseIface || gooseIface[0] == '\0')
        gooseIface = "eth0";

    printf("[critbench_ied_server] libiec61850 version %s\n",
           LibIEC61850_getVersionString());
    printf("[critbench_ied_server] MMS port: %d, GOOSE interface: %s\n",
           tcpPort, gooseIface);

    /* ==================================================================
     * Build dynamic data model
     * ==================================================================
     *
     * IED name "simpleIO", so MMS LD names become:
     *   simpleIO + GenericIO  = simpleIOGenericIO
     *   simpleIO + protection = simpleIOprotection
     *
     * The state API STATE dict keys mirror this:
     *   STATE["mms"]["simpleIOGenericIO"]["GGIO1"][...]
     *   STATE["mms"]["protection"]["PTOC1"][...]   ← uses short key
     */

    IedModel *model = IedModel_create("simpleIO");

    /* ---- LD: GenericIO -------------------------------------------- */
    LogicalDevice *ld_genio = LogicalDevice_create("GenericIO", model);

    /* LLN0 */
    LogicalNode *lln0_genio = LogicalNode_create("LLN0", ld_genio);
    DataObject  *lln0_mod    = CDC_ENS_create("Mod",    (ModelNode *)lln0_genio, 0);
    DataObject  *lln0_beh    = CDC_ENS_create("Beh",    (ModelNode *)lln0_genio, 0);
    DataObject  *lln0_health = CDC_ENS_create("Health", (ModelNode *)lln0_genio, 0);
    (void)lln0_mod; (void)lln0_beh; (void)lln0_health;

    /* LPHD1 (mandatory per IEC 61850-7-4) */
    LogicalNode *lphd1 = LogicalNode_create("LPHD1", ld_genio);
    CDC_ENS_create("PhyHealth", (ModelNode *)lphd1, 0);

    /* GGIO1 */
    LogicalNode *ggio1 = LogicalNode_create("GGIO1", ld_genio);

    /* -- Ind1-4 (SPS CDC, FC=ST) -- */
    DataObject *ind1 = CDC_SPS_create("Ind1", (ModelNode *)ggio1, 0);
    DataObject *ind2 = CDC_SPS_create("Ind2", (ModelNode *)ggio1, 0);
    DataObject *ind3 = CDC_SPS_create("Ind3", (ModelNode *)ggio1, 0);
    DataObject *ind4 = CDC_SPS_create("Ind4", (ModelNode *)ggio1, 0);

    g_ind1_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)ind1, "stVal");
    g_ind2_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)ind2, "stVal");
    g_ind3_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)ind3, "stVal");
    g_ind4_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)ind4, "stVal");

    /* -- SPCSO1-4 (SPC CDC, direct-normal control model, FC=CO/ST) -- */
    g_spcso1_do = CDC_SPC_create("SPCSO1", (ModelNode *)ggio1, 0,
                                 CDC_CTL_MODEL_DIRECT_NORMAL);
    g_spcso2_do = CDC_SPC_create("SPCSO2", (ModelNode *)ggio1, 0,
                                 CDC_CTL_MODEL_DIRECT_NORMAL);
    g_spcso3_do = CDC_SPC_create("SPCSO3", (ModelNode *)ggio1, 0,
                                 CDC_CTL_MODEL_DIRECT_NORMAL);
    g_spcso4_do = CDC_SPC_create("SPCSO4", (ModelNode *)ggio1, 0,
                                 CDC_CTL_MODEL_DIRECT_NORMAL);

    g_spcso1_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)g_spcso1_do, "stVal");
    g_spcso2_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)g_spcso2_do, "stVal");
    g_spcso3_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)g_spcso3_do, "stVal");
    g_spcso4_stVal = (DataAttribute *)ModelNode_getChild((ModelNode *)g_spcso4_do, "stVal");

    /* -- AnIn1-4 (MV CDC, FC=MX, float) -- */
    DataObject *anIn1 = CDC_MV_create("AnIn1", (ModelNode *)ggio1, 0, false);
    DataObject *anIn2 = CDC_MV_create("AnIn2", (ModelNode *)ggio1, 0, false);
    DataObject *anIn3 = CDC_MV_create("AnIn3", (ModelNode *)ggio1, 0, false);
    DataObject *anIn4 = CDC_MV_create("AnIn4", (ModelNode *)ggio1, 0, false);

    /* MV CDC nests: AnIn1.mag → AnIn1.mag.f */
    DataAttribute *anIn1_mag = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn1, "mag");
    DataAttribute *anIn2_mag = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn2, "mag");
    DataAttribute *anIn3_mag = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn3, "mag");
    DataAttribute *anIn4_mag = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn4, "mag");

    g_anIn1_magf = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn1_mag, "f");
    g_anIn2_magf = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn2_mag, "f");
    g_anIn3_magf = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn3_mag, "f");
    g_anIn4_magf = (DataAttribute *)ModelNode_getChild((ModelNode *)anIn4_mag, "f");

    /* -- GOOSE dataset on LLN0 -- */
    DataSet *gooseDs = DataSet_create("dataSet", lln0_genio);
    /* Dataset entries are relative to the LD: "LN$FC$DO$DA"           */
    /* Include all ST-FC booleans so any change triggers GOOSE stNum++ */
    DataSetEntry_create(gooseDs, "GGIO1$ST$SPCSO1$stVal", -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$SPCSO2$stVal", -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$SPCSO3$stVal", -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$SPCSO4$stVal", -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$Ind1$stVal",   -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$Ind2$stVal",   -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$Ind3$stVal",   -1, NULL);
    DataSetEntry_create(gooseDs, "GGIO1$ST$Ind4$stVal",   -1, NULL);

    /* GOOSE Control Block: gcb01 references the dataset "dataSet".    */
    /* confRev=1, fixedOffs=false, minTime=200ms, maxTime=3000ms       */
    GSEControlBlock_create("gcb01", lln0_genio, "gcb01", "dataSet",
                           1, false, 200, 3000);

    /* ---- LD: protection ------------------------------------------- */
    /*
     * MMS LD name = "simpleIOprotection", but the state API dict uses
     * the short key "protection" (set explicitly by notify_state_api).
     */
    LogicalDevice *ld_prot = LogicalDevice_create("protection", model);

    LogicalNode *lln0_prot = LogicalNode_create("LLN0", ld_prot);
    CDC_ENS_create("Mod",    (ModelNode *)lln0_prot, 0);
    CDC_ENS_create("Health", (ModelNode *)lln0_prot, 0);

    LogicalNode *ptoc1 = LogicalNode_create("PTOC1", ld_prot);

    /* StrVal using ASG CDC (Analog Setting — FC=SP, writable setMag.f) */
    DataObject *ptoc1_strval = CDC_ASG_create("StrVal", (ModelNode *)ptoc1,
                                              0, false);
    DataAttribute *ptoc1_setMag =
        (DataAttribute *)ModelNode_getChild((ModelNode *)ptoc1_strval, "setMag");
    g_ptoc1_setMag_f =
        (DataAttribute *)ModelNode_getChild((ModelNode *)ptoc1_setMag, "f");

    /* ==================================================================
     * Create IED server
     * ================================================================== */

    IedServerConfig config = IedServerConfig_create();
    IedServerConfig_setReportBufferSize(config, 200000);
    IedServerConfig_setEdition(config, IEC_61850_EDITION_2);
    IedServerConfig_enableFileService(config, false);
    IedServerConfig_enableDynamicDataSetService(config, true);
    IedServerConfig_enableLogService(config, false);
    IedServerConfig_setMaxMmsConnections(config, 5);

    iedServer = IedServer_createWithConfig(model, NULL, config);
    IedServerConfig_destroy(config);

    /* Set identity for MMS identify service */
    IedServer_setServerIdentity(iedServer, "CritBench", "critbench-ied", "1.0.0");

    /* ==================================================================
     * Write access policies
     * ================================================================== */

    /* Allow direct MMS writes to ST (Ind stVals, SPCSO stVal relay),  */
    /* MX (AnIn measurements), SP (PTOC1 settings)                     */
    IedServer_setWriteAccessPolicy(iedServer, IEC61850_FC_ST, ACCESS_POLICY_ALLOW);
    IedServer_setWriteAccessPolicy(iedServer, IEC61850_FC_MX, ACCESS_POLICY_ALLOW);
    IedServer_setWriteAccessPolicy(iedServer, IEC61850_FC_SP, ACCESS_POLICY_ALLOW);
    IedServer_setWriteAccessPolicy(iedServer, IEC61850_FC_DC, ACCESS_POLICY_ALLOW);

    /* Register write handler for tracked attributes */
    IedServer_handleWriteAccess(iedServer, g_ind1_stVal,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_ind2_stVal,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_ind3_stVal,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_ind4_stVal,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_spcso1_stVal, writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_spcso2_stVal, writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_spcso3_stVal, writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_spcso4_stVal, writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_anIn1_magf,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_anIn2_magf,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_anIn3_magf,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_anIn4_magf,   writeHandler, NULL);
    IedServer_handleWriteAccess(iedServer, g_ptoc1_setMag_f, writeHandler, NULL);

    /* ==================================================================
     * Control handlers (SPCSO1-4 — direct-normal)
     * ================================================================== */

    IedServer_setControlHandler(iedServer, g_spcso1_do,
                                (ControlHandler)controlHandler, g_spcso1_do);
    IedServer_setControlHandler(iedServer, g_spcso2_do,
                                (ControlHandler)controlHandler, g_spcso2_do);
    IedServer_setControlHandler(iedServer, g_spcso3_do,
                                (ControlHandler)controlHandler, g_spcso3_do);
    IedServer_setControlHandler(iedServer, g_spcso4_do,
                                (ControlHandler)controlHandler, g_spcso4_do);

    /* ==================================================================
     * GOOSE interface binding
     * ================================================================== */

    IedServer_setGooseInterfaceId(iedServer, gooseIface);

    /* ==================================================================
     * Start MMS server
     * ================================================================== */

    IedServer_start(iedServer, tcpPort);

    if (!IedServer_isRunning(iedServer)) {
        fprintf(stderr,
                "[critbench_ied_server] Failed to start (port %d locked?)\n",
                tcpPort);
        IedServer_destroy(iedServer);
        IedModel_destroy(model);
        return 1;
    }

    running = 1;
    signal(SIGINT,  sigint_handler);
    signal(SIGTERM, sigint_handler);

    printf("[critbench_ied_server] MMS server ready on port %d\n", tcpPort);
    printf("[critbench_ied_server] GOOSE publishing on %s (gcb01)\n", gooseIface);

    /* ==================================================================
     * Main loop — oscillate AnIn values like the original basic_io
     * This keeps the GOOSE stNum active and provides realistic MX data.
     * ================================================================== */

    float t = 0.f;

    while (running) {
        t += 0.1f;

        uint64_t ts = Hal_getTimeInMs();

        Timestamp iecTs;
        Timestamp_clearFlags(&iecTs);
        Timestamp_setTimeInMilliseconds(&iecTs, ts);
        Timestamp_setLeapSecondKnown(&iecTs, true);

        IedServer_lockDataModel(iedServer);

        IedServer_updateTimestampAttributeValue(iedServer,
            (DataAttribute *)ModelNode_getChild((ModelNode *)anIn1, "t"), &iecTs);
        IedServer_updateFloatAttributeValue(iedServer, g_anIn1_magf, sinf(t));

        IedServer_updateTimestampAttributeValue(iedServer,
            (DataAttribute *)ModelNode_getChild((ModelNode *)anIn2, "t"), &iecTs);
        IedServer_updateFloatAttributeValue(iedServer, g_anIn2_magf, sinf(t + 1.f));

        IedServer_updateTimestampAttributeValue(iedServer,
            (DataAttribute *)ModelNode_getChild((ModelNode *)anIn3, "t"), &iecTs);
        IedServer_updateFloatAttributeValue(iedServer, g_anIn3_magf, sinf(t + 2.f));

        IedServer_updateTimestampAttributeValue(iedServer,
            (DataAttribute *)ModelNode_getChild((ModelNode *)anIn4, "t"), &iecTs);
        IedServer_updateFloatAttributeValue(iedServer, g_anIn4_magf, sinf(t + 3.f));

        IedServer_unlockDataModel(iedServer);

        Thread_sleep(100);
    }

    /* ==================================================================
     * Shutdown
     * ================================================================== */

    IedServer_stop(iedServer);
    IedServer_destroy(iedServer);
    IedModel_destroy(model);

    printf("[critbench_ied_server] stopped.\n");
    return 0;
}
