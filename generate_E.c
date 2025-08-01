// generate_E.c
// Enumerate all isomorphic forms of E from token-type counts.
// Build:  gcc -O2 -std=c11 generate_E.c -o generate_E
// Run:    ./generate_E > all_E.txt

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char *name;   // token type name
    int remaining;      // how many still to place
} Sym;

static FILE *OUT;

static void dfs(Sym *syms, int m, const char **buf, int depth, int total,
                unsigned long long *emitted)
{
    if (depth == total) {
        (*emitted)++;
        // Label each expression for convenience (E1, E2, ...)
        fprintf(OUT, "E%llu: ", *emitted);
        for (int i = 0; i < total; i++) {
            if (i) fputc(' ', OUT);
            fputs(buf[i], OUT);
        }
        fputc('\n', OUT);
        return;
    }

    // Lexicographic by the order listed in the array
    for (int i = 0; i < m; i++) {
        if (syms[i].remaining > 0) {
            buf[depth] = syms[i].name;
            syms[i].remaining--;
            dfs(syms, m, buf, depth + 1, total, emitted);
            syms[i].remaining++;
        }
    }
}

int main(int argc, char **argv)
{
    // Optional: write to a file if given: ./generate_E output.txt
    OUT = (argc >= 2) ? fopen(argv[1], "w") : stdout;
    if (!OUT) { perror("fopen"); return 1; }

    // Define the language's token types and counts here.
    Sym syms[] = {
        {"object_1",   4},
        {"object_2",   1},
        {"object_3",   3},
        {"relation_4", 1},
        {"relation_5", 1},
        {"relation_6", 1}
    };
    const int m = (int)(sizeof(syms) / sizeof(syms[0]));

    int total = 0;
    for (int i = 0; i < m; i++) total += syms[i].remaining;

    const char **buf = (const char **)malloc((size_t)total * sizeof(*buf));
    if (!buf) { fputs("Out of memory\n", stderr); return 1; }

    unsigned long long emitted = 0ULL;
    dfs(syms, m, buf, 0, total, &emitted);

    // Summary to stderr so it doesn't mix with the sequences when redirected
    fprintf(stderr, "Generated %llu expressions of length %d.\n",
            emitted, total);

    free(buf);
    if (OUT != stdout) fclose(OUT);
    return 0;
}
