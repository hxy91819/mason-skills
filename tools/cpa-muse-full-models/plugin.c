/* SPDX-License-Identifier: MIT
 * CLIProxyAPI v8 native ABI: sdk/pluginabi and examples/plugin/model/c.
 * Only register metadata; execution and OAuth remain with the builtin Meta provider.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define EXPORT __attribute__((visibility("default")))
#define PLUGIN_VERSION "0.1.1"

typedef struct { void *ptr; size_t len; } buffer;
typedef struct {
    uint32_t abi_version;
    void *host_ctx;
    int (*call)(void *, const char *, const uint8_t *, size_t, buffer *);
    void (*free_buffer)(void *, size_t);
} host_api;
typedef struct {
    uint32_t abi_version;
    int (*call)(const char *, const uint8_t *, size_t, buffer *);
    void (*free_buffer)(void *, size_t);
    void (*shutdown)(void);
} plugin_api;

static const char registration[] =
    "{\"ok\":true,\"result\":{\"schema_version\":1,"
    "\"metadata\":{\"Name\":\"cpa-muse-full-models\",\"Version\":\"" PLUGIN_VERSION "\","
    "\"Author\":\"hxy91819\",\"ConfigFields\":[]},"
    "\"capabilities\":{\"model_registrar\":true}}}";

/* Full uses the Muse family context/output limits and named reasoning controls.
 * Keep this additive: model_provider would replace builtin per-auth discovery.
 */
#define MODEL(ID, LABEL) \
    "{\"ID\":\"" ID "\",\"Name\":\"" ID "\",\"Object\":\"model\"," \
    "\"OwnedBy\":\"meta\",\"Type\":\"meta\",\"DisplayName\":\"" LABEL "\"," \
    "\"ContextLength\":1048576,\"MaxCompletionTokens\":65536," \
    "\"SupportedInputModalities\":[\"text\",\"image\"]," \
    "\"SupportedOutputModalities\":[\"text\"]," \
    "\"Thinking\":{\"Levels\":[\"minimal\",\"low\",\"medium\",\"high\",\"xhigh\",\"max\"]}," \
    "\"UserDefined\":true}"

static const char models[] =
    "{\"ok\":true,\"result\":{\"Provider\":\"meta\",\"Models\":["
    MODEL("muse-wonder-full-1.0", "Muse Wonder Full 1.0") ","
    MODEL("muse-wonder-full-1.0-contributor", "Muse Wonder Full 1.0 Contributor")
    "]}}";

static int reply(buffer *out, const char *json) {
    if (!out) return 1;
    size_t len = strlen(json);
    void *ptr = malloc(len);
    if (!ptr) return 1;
    memcpy(ptr, json, len);
    out->ptr = ptr;
    out->len = len;
    return 0;
}

static int call(const char *method, const uint8_t *request, size_t len, buffer *out) {
    (void)request;
    (void)len;
    if (!out) return 1;
    out->ptr = NULL;
    out->len = 0;
    if (method && (!strcmp(method, "plugin.register") || !strcmp(method, "plugin.reconfigure")))
        return reply(out, registration);
    if (method && !strcmp(method, "model.register")) return reply(out, models);
    return reply(out, "{\"ok\":false,\"error\":{\"code\":\"unknown_method\",\"message\":\"Unsupported method\"}}");
}

static void free_buffer(void *ptr, size_t len) {
    (void)len;
    free(ptr);
}

static void shutdown_plugin(void) {}

EXPORT int cliproxy_plugin_init(const host_api *host, plugin_api *plugin) {
    (void)host;
    if (!plugin) return 1;
    plugin->abi_version = 1;
    plugin->call = call;
    plugin->free_buffer = free_buffer;
    plugin->shutdown = shutdown_plugin;
    return 0;
}
