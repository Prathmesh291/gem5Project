/*
 * chase.c — controlled pointer-chase microbenchmark for cache-compression
 * experiments in gem5 SE mode.
 *
 * Design goal: keep the MEMORY ACCESS PATTERN identical across runs and vary
 * ONLY the compressibility of the data, so any difference between
 * never/always/adaptive compression policies is attributable to compression.
 *
 *   - Every node is exactly one 64-byte cache line (pointer + 7 x 8-byte words).
 *   - Traversal order is a single random cycle over all nodes (Sattolo's
 *     algorithm) generated from a FIXED seed BEFORE the payload is written,
 *     so the order is identical for every payload mode and working-set size.
 *   - Each visit is a dependent load (p = p->next), so execution time is
 *     dominated by load-to-use latency: L1 hit, L2 hit (+ decompression), or
 *     DRAM. This makes the decompression penalty and the capacity benefit of
 *     compression both visible in IPC / cycles.
 *
 * Usage:
 *   ./chase <working_set_kB> <zero|small|random> <visits_in_millions> [write]
 *
 *   working_set_kB : total bytes of nodes (e.g. 128, 320, 448, 640, 1024)
 *   zero           : payload all zeros           -> highly compressible (FPC zero runs)
 *   small          : payload small 8-bit ints    -> compressible (FPC sign-extended patterns)
 *   random         : payload xorshift64 values   -> incompressible
 *   visits         : number of node visits in millions (steady-state length)
 *   write          : optional; each visit also overwrites one payload word with
 *                    a random value, so initially-compressible lines EXPAND and
 *                    stress the data-expansion / re-allocation path.
 *
 * Build (static linking is strongly recommended for gem5 SE mode):
 *   gcc -O2 -static -o chase chase.c
 *
 * To measure the instruction count of the initialisation phase (to choose a
 * fast-forward count), run with visits = 0 under AtomicSimpleCPU and read
 * simInsts from stats.txt.
 *
 * The program prints a checksum. For a given <ws, mode, visits, write> the
 * checksum MUST be identical under every compression policy — compression is
 * supposed to be invisible to software. Use this as a correctness check.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#define LINE_BYTES 64

typedef struct node {
    struct node *next;      /* 8 bytes  */
    uint64_t pay[7];        /* 56 bytes */
} node_t;                   /* = 64 bytes = one cache line */

static uint64_t rng_state = 0x9E3779B97F4A7C15ull;   /* fixed seed */

static inline uint64_t xorshift64(void)
{
    uint64_t x = rng_state;
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    rng_state = x;
    return x;
}

int main(int argc, char **argv)
{
    if (argc < 4) {
        fprintf(stderr,
            "usage: %s <working_set_kB> <zero|small|random> <visits_M> [write]\n",
            argv[0]);
        return 1;
    }

    const size_t ws_kb   = strtoull(argv[1], NULL, 10);
    const char  *mode    = argv[2];
    const uint64_t visits = strtoull(argv[3], NULL, 10) * 1000000ull;
    const int    do_write = (argc > 4 && strcmp(argv[4], "write") == 0);

    if (sizeof(node_t) != LINE_BYTES) {
        fprintf(stderr, "node_t is %zu bytes, expected %d\n",
                sizeof(node_t), LINE_BYTES);
        return 2;
    }

    const size_t n = (ws_kb * 1024) / LINE_BYTES;
    if (n < 2) { fprintf(stderr, "working set too small\n"); return 2; }

    node_t *nodes = NULL;
    if (posix_memalign((void **)&nodes, LINE_BYTES, n * sizeof(node_t)) != 0) {
        fprintf(stderr, "allocation failed\n");
        return 3;
    }

    /* ---- 1. Traversal order: one random cycle, same for every mode ---- */
    size_t *perm = (size_t *)malloc(n * sizeof(size_t));
    if (!perm) return 3;
    for (size_t i = 0; i < n; i++) perm[i] = i;
    for (size_t i = n - 1; i > 0; i--) {          /* Sattolo: j in [0, i-1] */
        size_t j = (size_t)(xorshift64() % i);
        size_t t = perm[i]; perm[i] = perm[j]; perm[j] = t;
    }
    for (size_t i = 0; i < n; i++)
        nodes[perm[i]].next = &nodes[perm[(i + 1) % n]];
    free(perm);

    /* ---- 2. Payload: the only thing that differs between modes ---- */
    int m = 0;                                     /* 0 zero, 1 small, 2 random */
    if      (strcmp(mode, "zero")   == 0) m = 0;
    else if (strcmp(mode, "small")  == 0) m = 1;
    else if (strcmp(mode, "random") == 0) m = 2;
    else { fprintf(stderr, "unknown mode %s\n", mode); return 1; }

    for (size_t i = 0; i < n; i++) {
        for (int k = 0; k < 7; k++) {
            if (m == 0)      nodes[i].pay[k] = 0;
            else if (m == 1) nodes[i].pay[k] = (uint64_t)((i * 7u + (size_t)k) & 0x7Fu);
            else             nodes[i].pay[k] = xorshift64();
        }
    }

    /* ---- 3. Steady-state region: dependent pointer chase ---- */
    node_t *p = &nodes[0];
    uint64_t sum = 0;
    for (uint64_t v = 0; v < visits; v++) {
        sum += p->pay[v & 3];                      /* touch payload (same line) */
        if (do_write)
            p->pay[(v + 1) & 3] = xorshift64();    /* dirty rewrite -> expansion */
        p = p->next;                               /* dependent load */
    }

    printf("ws_kB=%zu nodes=%zu mode=%s visits=%llu write=%d checksum=%llu\n",
           ws_kb, n, mode, (unsigned long long)visits, do_write,
           (unsigned long long)sum);
    free(nodes);
    return 0;
}
