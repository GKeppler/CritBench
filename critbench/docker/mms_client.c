/*
 * mms_client.c — Non-interactive MMS client for CritBench.
 *
 * Uses the libiec61850 client API to perform discover / read / write
 * operations from the command line.
 *
 * Usage:
 *   mms_client -h <host> -p <port> discover
 *   mms_client -h <host> -p <port> read  <iec61850-reference>
 *   mms_client -h <host> -p <port> write <iec61850-reference> <value>
 *
 * Build:
 *   gcc -o mms_client mms_client.c -liec61850 -lpthread
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "iec61850_client.h"

static void print_usage(const char *prog) {
    fprintf(stderr,
        "Usage:\n"
        "  %s -h <host> -p <port> discover\n"
        "  %s -h <host> -p <port> read  <reference>\n"
        "  %s -h <host> -p <port> write <reference> <value>\n",
        prog, prog, prog);
}

/* Recursively print all data attributes under a data object */
static void print_data_attributes(IedConnection con, const char *ld,
                                  const char *ln, const char *doName,
                                  FunctionalConstraint fc)
{
    IedClientError err;
    char ref[512];

    snprintf(ref, sizeof(ref), "%s/%s.%s", ld, ln, doName);

    LinkedList attrs = IedConnection_getDataDirectoryByFC(con, &err, ref, fc);
    if (attrs == NULL || err != IED_ERROR_OK)
        return;

    LinkedList entry = LinkedList_getNext(attrs);
    while (entry) {
        const char *attr = (const char *)LinkedList_getData(entry);
        printf("        DA: %s/%s.%s.%s [%s]\n", ld, ln, doName, attr,
               FunctionalConstraint_toString(fc));
        entry = LinkedList_getNext(entry);
    }
    LinkedList_destroy(attrs);
}

/* Print MmsValue to stdout in a human-readable way */
static void print_mms_value(MmsValue *value, int indent) {
    if (value == NULL) {
        printf("(null)");
        return;
    }

    MmsType type = MmsValue_getType(value);

    switch (type) {
    case MMS_BOOLEAN:
        printf("%s", MmsValue_getBoolean(value) ? "true" : "false");
        break;
    case MMS_INTEGER:
        printf("%lld", (long long)MmsValue_toInt64(value));
        break;
    case MMS_UNSIGNED:
        printf("%llu", (unsigned long long)MmsValue_toUint32(value));
        break;
    case MMS_FLOAT:
        printf("%g", MmsValue_toFloat(value));
        break;
    case MMS_VISIBLE_STRING:
    case MMS_STRING:
        printf("\"%s\"", MmsValue_toString(value));
        break;
    case MMS_BIT_STRING:
        printf("0x%08x", MmsValue_getBitStringAsInteger(value));
        break;
    case MMS_UTC_TIME: {
        uint64_t ms = MmsValue_getUtcTimeInMs(value);
        printf("UTC(%llu ms)", (unsigned long long)ms);
        break;
    }
    case MMS_STRUCTURE: {
        int count = MmsValue_getArraySize(value);
        printf("{\n");
        for (int i = 0; i < count; i++) {
            for (int j = 0; j < indent + 2; j++) printf(" ");
            printf("[%d]: ", i);
            print_mms_value(MmsValue_getElement(value, i), indent + 2);
            printf("\n");
        }
        for (int j = 0; j < indent; j++) printf(" ");
        printf("}");
        break;
    }
    case MMS_ARRAY: {
        int count = MmsValue_getArraySize(value);
        printf("[\n");
        for (int i = 0; i < count; i++) {
            for (int j = 0; j < indent + 2; j++) printf(" ");
            printf("[%d]: ", i);
            print_mms_value(MmsValue_getElement(value, i), indent + 2);
            printf("\n");
        }
        for (int j = 0; j < indent; j++) printf(" ");
        printf("]");
        break;
    }
    default:
        printf("(type=%d)", type);
        break;
    }
}

/* ---- discover --------------------------------------------------------- */
static int do_discover(IedConnection con) {
    IedClientError err;

    LinkedList devices = IedConnection_getLogicalDeviceList(con, &err);
    if (devices == NULL || err != IED_ERROR_OK) {
        fprintf(stderr, "Error getting logical device list: %d\n", err);
        return 1;
    }

    printf("=== MMS Data Model ===\n");

    LinkedList devEntry = LinkedList_getNext(devices);
    while (devEntry) {
        const char *ldName = (const char *)LinkedList_getData(devEntry);
        printf("LD: %s\n", ldName);

        LinkedList lnList = IedConnection_getLogicalDeviceDirectory(
            con, &err, ldName);
        if (lnList && err == IED_ERROR_OK) {
            LinkedList lnEntry = LinkedList_getNext(lnList);
            while (lnEntry) {
                const char *lnName = (const char *)LinkedList_getData(lnEntry);
                printf("  LN: %s\n", lnName);

                /* Get data objects for this LN */
                char lnRef[256];
                snprintf(lnRef, sizeof(lnRef), "%s/%s", ldName, lnName);

                LinkedList doList = IedConnection_getLogicalNodeDirectory(
                    con, &err, lnRef, ACSI_CLASS_DATA_OBJECT);
                if (doList && err == IED_ERROR_OK) {
                    LinkedList doEntry = LinkedList_getNext(doList);
                    while (doEntry) {
                        const char *doName =
                            (const char *)LinkedList_getData(doEntry);
                        printf("    DO: %s\n", doName);

                        /* Print data attributes for common FCs */
                        static const FunctionalConstraint fcs[] = {
                            IEC61850_FC_ST, IEC61850_FC_MX, IEC61850_FC_CO,
                            IEC61850_FC_CF, IEC61850_FC_DC, IEC61850_FC_SP,
                        };
                        for (size_t i = 0; i < sizeof(fcs)/sizeof(fcs[0]); i++) {
                            print_data_attributes(con, ldName, lnName,
                                                  doName, fcs[i]);
                        }

                        doEntry = LinkedList_getNext(doEntry);
                    }
                    LinkedList_destroy(doList);
                }

                /* Also list data sets */
                LinkedList dsList = IedConnection_getLogicalNodeDirectory(
                    con, &err, lnRef, ACSI_CLASS_DATA_SET);
                if (dsList && err == IED_ERROR_OK) {
                    LinkedList dsEntry = LinkedList_getNext(dsList);
                    while (dsEntry) {
                        const char *dsName =
                            (const char *)LinkedList_getData(dsEntry);
                        printf("    DS: %s\n", dsName);
                        dsEntry = LinkedList_getNext(dsEntry);
                    }
                    LinkedList_destroy(dsList);
                }

                lnEntry = LinkedList_getNext(lnEntry);
            }
            LinkedList_destroy(lnList);
        }

        devEntry = LinkedList_getNext(devEntry);
    }

    LinkedList_destroy(devices);
    return 0;
}

/* ---- read ------------------------------------------------------------- */
static int do_read(IedConnection con, const char *reference) {
    IedClientError err;

    /*
     * Parse the functional constraint from the reference.
     * Expected format: LD/LN$FC$DO$DA  (e.g. simpleIOGenericIO/LLN0$ST$Mod$stVal)
     * We split at first $ to get LD/LN, then the FC token.
     */

    /* First, try reading as a generic object reference by extracting FC */
    char refCopy[512];
    strncpy(refCopy, reference, sizeof(refCopy) - 1);
    refCopy[sizeof(refCopy) - 1] = '\0';

    FunctionalConstraint fc = IEC61850_FC_ST; /* default */

    /* Find the FC part: after the first $ */
    char *dollar1 = strchr(refCopy, '$');
    if (dollar1) {
        char *fcStart = dollar1 + 1;
        char *dollar2 = strchr(fcStart, '$');
        if (dollar2) {
            char fcStr[8];
            int fcLen = (int)(dollar2 - fcStart);
            if (fcLen > 0 && fcLen < (int)sizeof(fcStr)) {
                strncpy(fcStr, fcStart, fcLen);
                fcStr[fcLen] = '\0';
                fc = FunctionalConstraint_fromString(fcStr);
                if (fc == IEC61850_FC_NONE)
                    fc = IEC61850_FC_ST;
            }
        }
    }

    /* Convert $ separators to . for the objectReference format,
     * but the IedConnection_readObject takes the dollar-separated form. */
    MmsValue *value = IedConnection_readObject(con, &err, reference, fc);

    if (err != IED_ERROR_OK || value == NULL) {
        fprintf(stderr, "Read error for '%s' (FC=%s): error=%d\n",
                reference, FunctionalConstraint_toString(fc), err);
        return 1;
    }

    printf("%s = ", reference);
    print_mms_value(value, 0);
    printf("\n");

    MmsValue_delete(value);
    return 0;
}

/* ---- write ------------------------------------------------------------ */
static int do_write(IedConnection con, const char *reference,
                    const char *valueStr)
{
    IedClientError err;

    /* Extract FC from reference (same logic as read) */
    char refCopy[512];
    strncpy(refCopy, reference, sizeof(refCopy) - 1);
    refCopy[sizeof(refCopy) - 1] = '\0';

    FunctionalConstraint fc = IEC61850_FC_ST;
    char *dollar1 = strchr(refCopy, '$');
    if (dollar1) {
        char *fcStart = dollar1 + 1;
        char *dollar2 = strchr(fcStart, '$');
        if (dollar2) {
            char fcStr[8];
            int fcLen = (int)(dollar2 - fcStart);
            if (fcLen > 0 && fcLen < (int)sizeof(fcStr)) {
                strncpy(fcStr, fcStart, fcLen);
                fcStr[fcLen] = '\0';
                fc = FunctionalConstraint_fromString(fcStr);
                if (fc == IEC61850_FC_NONE)
                    fc = IEC61850_FC_ST;
            }
        }
    }

    /* First read the existing value to determine its type */
    MmsValue *existing = IedConnection_readObject(con, &err, reference, fc);
    MmsValue *newVal = NULL;

    if (existing != NULL && err == IED_ERROR_OK) {
        MmsType type = MmsValue_getType(existing);
        switch (type) {
        case MMS_BOOLEAN:
            newVal = MmsValue_newBoolean(
                strcmp(valueStr, "true") == 0 ||
                strcmp(valueStr, "1") == 0);
            break;
        case MMS_INTEGER:
            newVal = MmsValue_newIntegerFromInt64(atoll(valueStr));
            break;
        case MMS_UNSIGNED:
            newVal = MmsValue_newUnsignedFromUint32((uint32_t)atol(valueStr));
            break;
        case MMS_FLOAT:
            newVal = MmsValue_newFloat(atof(valueStr));
            break;
        case MMS_VISIBLE_STRING:
        case MMS_STRING:
            newVal = MmsValue_newVisibleString(valueStr);
            break;
        default:
            /* Try as string for unknown types */
            newVal = MmsValue_newVisibleString(valueStr);
            break;
        }
        MmsValue_delete(existing);
    } else {
        /* Can't determine type; try as string */
        newVal = MmsValue_newVisibleString(valueStr);
    }

    err = IED_ERROR_OK;
    IedConnection_writeObject(con, &err, reference, fc, newVal);
    MmsValue_delete(newVal);

    if (err != IED_ERROR_OK) {
        fprintf(stderr, "Write error for '%s': %d\n", reference, err);
        return 1;
    }

    printf("OK: written '%s' to %s\n", valueStr, reference);
    return 0;
}


/* ---- main ------------------------------------------------------------- */
int main(int argc, char **argv) {
    const char *host = "localhost";
    int port = 102;
    const char *action = NULL;
    const char *arg1 = NULL;
    const char *arg2 = NULL;

    /* Parse arguments */
    int i = 1;
    while (i < argc) {
        if (strcmp(argv[i], "-h") == 0 && i + 1 < argc) {
            host = argv[++i];
        } else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) {
            port = atoi(argv[++i]);
        } else if (action == NULL) {
            action = argv[i];
        } else if (arg1 == NULL) {
            arg1 = argv[i];
        } else if (arg2 == NULL) {
            arg2 = argv[i];
        }
        i++;
    }

    if (action == NULL) {
        print_usage(argv[0]);
        return 1;
    }

    /* Connect */
    IedClientError err;
    IedConnection con = IedConnection_create();
    IedConnection_connect(con, &err, host, port);

    if (err != IED_ERROR_OK) {
        fprintf(stderr, "MMS connect failed! (host=%s, port=%d, error=%d)\n",
                host, port, err);
        IedConnection_destroy(con);
        return 1;
    }

    int rc = 0;

    if (strcmp(action, "discover") == 0) {
        rc = do_discover(con);
    } else if (strcmp(action, "read") == 0) {
        if (arg1 == NULL) {
            fprintf(stderr, "Error: read requires a reference argument\n");
            rc = 1;
        } else {
            rc = do_read(con, arg1);
        }
    } else if (strcmp(action, "write") == 0) {
        if (arg1 == NULL || arg2 == NULL) {
            fprintf(stderr,
                    "Error: write requires <reference> and <value>\n");
            rc = 1;
        } else {
            rc = do_write(con, arg1, arg2);
        }
    } else {
        fprintf(stderr, "Unknown action: %s\n", action);
        print_usage(argv[0]);
        rc = 1;
    }

    IedConnection_close(con);
    IedConnection_destroy(con);
    return rc;
}
