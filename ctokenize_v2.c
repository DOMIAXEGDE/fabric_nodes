
/*
 * ctokenize_v2.c
 *
 * A practical C tokenizer for LLM dataset prep with two goals:
 *  1) Lossless, reversible token stream (JSONL) including whitespace/comments.
 *  2) Basic corpus metrics and identifier vocabulary counts.
 *
 * Modes (subcommands):
 *   stream     Tokenize files to a per-token JSONL stream (lossless).
 *              Usage: ctokenize_v2 stream [--out out.jsonl] [--stdin NAME] [files...]
 *              If no files are given, reads stdin (binary) and uses NAME or "stdin".
 *
 *   stats      Emit JSON with counts per token kind and other measurables.
 *              Usage: ctokenize_v2 stats [--out out.json] [files...]
 *
 *   vocab      Emit TSV of identifier/keyword frequencies.
 *              Usage: ctokenize_v2 vocab [--out out.tsv] [files...]
 *
 *   reassemble Rebuild original files from a stream JSONL.
 *              Usage: ctokenize_v2 reassemble --in stream.jsonl [--outdir DIR]
 *              Writes each reconstructed file to DIR/<file>.recon (default DIR=".").
 *
 * Build:
 *   cc -std=c99 -O2 -Wall -Wextra -o ctokenize_v2 ctokenize_v2.c
 *
 * Notes:
 *  - The stream format is JSONL with fields:
 *      file, off (byte offset), line, col, kind, lexeme
 *    Concatenating lexemes per file in order reproduces the exact bytes.
 *  - We do minimal C lexing: identifiers/keywords, numbers, strings, chars,
 *    preprocessor lines (with backslash continuations), comments, whitespace,
 *    newlines, and punctuators/operators (longest-match).
 *  - For JSON escaping we emit \n, \r, \t, \\, \", and \u00XX for other ASCII controls.
 *  - Reassembler parses only the fields we generate.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <errno.h>
#ifdef _WIN32
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#else
#include <sys/stat.h>
#define MKDIR(p) mkdir((p), 0777)
#endif
#include <sys/types.h>
#include <sys/stat.h>
#include <stdbool.h>


#ifdef _MSC_VER
#define strcasecmp _stricmp
#endif

#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))

/* ---------- Keyword table (C11) ---------- */
static const char *C_KEYWORDS[] = {
    "auto","break","case","char","const","continue","default","do","double",
    "else","enum","extern","float","for","goto","if","inline","int","long",
    "register","restrict","return","short","signed","sizeof","static","struct",
    "switch","typedef","union","unsigned","void","volatile","while","_Alignas",
    "_Alignof","_Atomic","_Bool","_Complex","_Generic","_Imaginary","_Noreturn",
    "_Static_assert","_Thread_local"
};
static int is_keyword(const char *s, size_t n) {
    for (size_t i=0;i<sizeof(C_KEYWORDS)/sizeof(C_KEYWORDS[0]);++i) {
        const char *k = C_KEYWORDS[i];
        if (strlen(k)==n && memcmp(k,s,n)==0) return 1;
    }
    return 0;
}

/* ---------- Hash (FNV-1a 64-bit) ---------- */
static uint64_t fnv1a64(const void *data, size_t len) {
    const unsigned char *p = (const unsigned char*)data;
    uint64_t h = 1469598103934665603ULL;
    for (size_t i=0;i<len;++i) {
        h ^= p[i];
        h *= 1099511628211ULL;
    }
    return h;
}

/* ---------- Identifier vocabulary map ---------- */
typedef struct VEntry {
    uint64_t h;
    char *s;
    size_t len;
    uint64_t count;
    struct VEntry *next;
} VEntry;

typedef struct {
    VEntry **bkt;
    size_t nbkt;
    uint64_t nitem;
} VMap;

static void vmap_init(VMap *m, size_t nbkt) {
    m->nbkt = nbkt;
    m->nitem = 0;
    m->bkt = (VEntry**)calloc(nbkt, sizeof(VEntry*));
    if (!m->bkt) { fprintf(stderr, "OOM\n"); exit(1); }
}
static void vmap_add(VMap *m, const char *s, size_t len) {
    uint64_t h = fnv1a64(s, len);
    size_t idx = (size_t)(h % m->nbkt);
    for (VEntry *e = m->bkt[idx]; e; e = e->next) {
        if (e->h==h && e->len==len && memcmp(e->s, s, len)==0) {
            e->count++;
            return;
        }
    }
    VEntry *e = (VEntry*)malloc(sizeof(VEntry));
    if (!e) { fprintf(stderr, "OOM\n"); exit(1); }
    e->s = (char*)malloc(len+1);
    if (!e->s) { fprintf(stderr, "OOM\n"); exit(1); }
    memcpy(e->s, s, len); e->s[len]='\0';
    e->len = len; e->h = h; e->count = 1;
    e->next = m->bkt[idx]; m->bkt[idx] = e; m->nitem++;
}
static void vmap_free(VMap *m) {
    for (size_t i=0;i<m->nbkt;++i) {
        VEntry *e = m->bkt[i];
        while (e) { VEntry *n=e->next; free(e->s); free(e); e=n; }
    }
    free(m->bkt);
}

/* ---------- Buffer ---------- */
typedef struct {
    unsigned char *p;
    size_t n;
} Buf;

static int read_file(const char *path, Buf *b) {
    FILE *f = NULL;
    if (strcmp(path,"-")==0) f = stdin;
    else f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "Failed to open %s: %s\n", path, strerror(errno)); return -1; }
    if (f==stdin) {
        /* Read stdin to dynamic buffer */
        size_t cap = 1<<20;
        b->p = (unsigned char*)malloc(cap);
        if (!b->p) { fprintf(stderr,"OOM\n"); return -1; }
        b->n = 0;
        for (;;) {
            if (b->n + (1<<16) > cap) {
                cap *= 2;
                unsigned char *np = (unsigned char*)realloc(b->p, cap);
                if (!np) { fprintf(stderr,"OOM\n"); free(b->p); return -1; }
                b->p = np;
            }
            size_t r = fread(b->p + b->n, 1, (1<<16), f);
            b->n += r;
            if (r==0) break;
        }
    } else {
        fseek(f, 0, SEEK_END);
        long sz = ftell(f);
        if (sz < 0) { fprintf(stderr,"ftell failed\n"); fclose(f); return -1; }
        fseek(f, 0, SEEK_SET);
        b->p = (unsigned char*)malloc((size_t)sz);
        if (!b->p) { fprintf(stderr,"OOM\n"); fclose(f); return -1; }
        b->n = fread(b->p, 1, (size_t)sz, f);
        fclose(f);
    }
    return 0;
}

/* ---------- JSON escaping ---------- */
static void json_escape_write(const unsigned char *s, size_t len, FILE *out) {
    for (size_t i=0;i<len;++i) {
        unsigned char c = s[i];
        if (c == '\"' || c == '\\') {
            fputc('\\', out);
            fputc(c, out);
        } else if (c == '\n') {
            fputs("\\n", out);
        } else if (c == '\r') {
            fputs("\\r", out);
        } else if (c == '\t') {
            fputs("\\t", out);
        } else if (c < 0x20 || c == 0x7f) {
            /* Other ASCII control chars -> \u00XX */
            static const char *hex="0123456789ABCDEF";
            fputs("\\u00", out);
            fputc(hex[(c>>4)&0xF], out);
            fputc(hex[c&0xF], out);
        } else {
            fputc(c, out);
        }
    }
}

/* ---------- Minimal JSON string unescape (for reassemble) ---------- */
static int hexval(char c) {
    if (c>='0'&&c<='9') return c-'0';
    if (c>='a'&&c<='f') return 10 + (c-'a');
    if (c>='A'&&c<='F') return 10 + (c-'A');
    return -1;
}
static unsigned char *json_unescape_alloc(const char *s, size_t *out_len) {
    size_t n = strlen(s);
    unsigned char *buf = (unsigned char*)malloc(n+1);
    if (!buf) return NULL;
    size_t j=0;
    for (size_t i=0;i<n;) {
        char c = s[i++];
        if (c!='\\') { buf[j++] = (unsigned char)c; continue; }
        if (i>=n) { buf[j++]='\\'; break; }
        char e = s[i++];
        switch (e) {
            case 'n': buf[j++] = '\n'; break;
            case 'r': buf[j++] = '\r'; break;
            case 't': buf[j++] = '\t'; break;
            case '\\': buf[j++]='\\'; break;
            case '\"': buf[j++]='\"'; break;
            case 'b': buf[j++]='\b'; break;
            case 'f': buf[j++]='\f'; break;
            case 'u': {
                if (i+4<=n) {
                    int h1=hexval(s[i]), h2=hexval(s[i+1]), h3=hexval(s[i+2]), h4=hexval(s[i+3]);
                    if (h1>=0&&h2>=0&&h3>=0&&h4>=0) {
                        unsigned code = (unsigned)(h1<<12 | h2<<8 | h3<<4 | h4);
                        /* Only handle BMP ASCII subset here */
                        if (code <= 0xFF) buf[j++] = (unsigned char)code;
                        else {
                            /* naive UTF-8 encode */
                            if (code <= 0x7FF) {
                                buf[j++] = 0xC0 | (code>>6);
                                buf[j++] = 0x80 | (code & 0x3F);
                            } else {
                                buf[j++] = 0xE0 | (code>>12);
                                buf[j++] = 0x80 | ((code>>6)&0x3F);
                                buf[j++] = 0x80 | (code & 0x3F);
                            }
                        }
                        i+=4;
                    } else {
                        /* malformed, keep as-is */
                        buf[j++]='\\'; buf[j++]='u';
                    }
                } else { buf[j++]='\\'; buf[j++]='u'; }
            } break;
            default: buf[j++]=(unsigned char)e; break;
        }
    }
    buf[j]=0;
    if (out_len) *out_len = j;
    return buf;
}

/* ---------- Token kinds ---------- */
typedef enum {
    TK_WS, TK_NEWLINE, TK_LINE_COMMENT, TK_BLOCK_COMMENT, TK_PREPROC,
    TK_IDENT, TK_KEYWORD, TK_NUMBER, TK_STRING, TK_CHAR, TK_PUNCT
} TokKind;
static const char *kind_name(TokKind k) {
    switch (k) {
        case TK_WS: return "WS";
        case TK_NEWLINE: return "NEWLINE";
        case TK_LINE_COMMENT: return "LINE_COMMENT";
        case TK_BLOCK_COMMENT: return "BLOCK_COMMENT";
        case TK_PREPROC: return "PREPROC";
        case TK_IDENT: return "IDENT";
        case TK_KEYWORD: return "KEYWORD";
        case TK_NUMBER: return "NUMBER";
        case TK_STRING: return "STRING";
        case TK_CHAR: return "CHAR";
        case TK_PUNCT: return "PUNCT";
    }
    return "UNK";
}

/* ---------- Metrics ---------- */
typedef struct {
    uint64_t counts[16]; /* by TokKind index */
    uint64_t tokens_total;
    uint64_t bytes_total;
    uint64_t bytes_comments;
    uint64_t bytes_whitespace;
    uint64_t lines;
} Metrics;

/* ---------- Emit JSONL token ---------- */
static void emit_json_token(FILE *out, const char *fname, size_t off, size_t line, size_t col,
                            TokKind kind, const unsigned char *lex, size_t len) {
    fputs("{\"file\":\"", out); fputs(fname, out); fputs("\",", out);
    fprintf(out, "\"off\":%zu,\"line\":%zu,\"col\":%zu,", off, line, col);
    fputs("\"kind\":\"", out); fputs(kind_name(kind), out); fputs("\",\"lexeme\":\"", out);
    json_escape_write(lex, len, out);
    fputs("\"}\n", out);
}

/* ---------- Punctuator matching ---------- */
static int is_punct_char(int c) {
    const char *p = "{}[]()#;,:?~!%^&*-+=|<>./";
    return (c && strchr(p, c)!=NULL);
}
static size_t match_punct(const unsigned char *s, size_t n) {
    if (n==0) return 0;
    /* Try 3-char punctuators */
    if (n>=3) {
        if (!memcmp(s,"<<=",3) || !memcmp(s,">>=",3) || !memcmp(s,"...",3) || !memcmp(s,"##",2) /* check later */) {
            if (!memcmp(s,"##",2)) return 2;
            return 3;
        }
    }
    /* Try 2-char */
    if (n>=2) {
        const char *twos[] = {"->","++","--","<<",">>","<=",">=","==","!=","&&","||",
                              "+=","-=","*=","/=","%=","&=","|=","^=","::",".*","->*","##"};
        for (size_t i=0;i<sizeof(twos)/sizeof(twos[0]);++i) {
            if (!memcmp(s, twos[i], strlen(twos[i]))) return strlen(twos[i]);
        }
    }
    /* Single char */
    if (is_punct_char(s[0])) return 1;
    return 0;
}

/* ---------- Tokenize one file ---------- */
typedef struct {
    const unsigned char *p;
    size_t n, i;
    size_t line, col;
    const char *fname;
    FILE *out_stream;
    Metrics *mx;
    VMap *vmap; /* for identifiers and keywords */
} Lexer;

static void metrics_add(Metrics *mx, TokKind k, size_t len) {
    if ((int)k < 16) mx->counts[(int)k]++;
    mx->tokens_total++;
    mx->bytes_total += len;
    if (k==TK_LINE_COMMENT || k==TK_BLOCK_COMMENT) mx->bytes_comments += len;
    if (k==TK_WS || k==TK_NEWLINE) mx->bytes_whitespace += len;
    if (k==TK_NEWLINE) mx->lines++;
}

static void emit(Lexer *lx, TokKind k, const unsigned char *s, size_t len, size_t start_off, size_t start_line, size_t start_col) {
    if (lx->out_stream) {
        emit_json_token(lx->out_stream, lx->fname, start_off, start_line, start_col, k, s, len);
    }
    metrics_add(lx->mx, k, len);
    if (lx->vmap && (k==TK_IDENT || k==TK_KEYWORD)) {
        vmap_add(lx->vmap, (const char*)s, len);
    }
}

static void lex_file(Buf *b, const char *fname, FILE *out_stream, Metrics *mx, VMap *vmap) {
    Lexer lx = { b->p, b->n, 0, 1, 1, fname, out_stream, mx, vmap };
    while (lx.i < lx.n) {
        size_t start = lx.i, start_line = lx.line, start_col = lx.col;
        unsigned char c = lx.p[lx.i];

        /* Newline(s): handle CRLF and LF */
        if (c == '\r') {
            size_t j = lx.i;
            if (j+1 < lx.n && lx.p[j+1]=='\n') {
                lx.i += 2; lx.line++; lx.col = 1;
                emit(&lx, TK_NEWLINE, lx.p+start, 2, start, start_line, start_col);
            } else {
                lx.i += 1; lx.line++; lx.col = 1;
                emit(&lx, TK_NEWLINE, lx.p+start, 1, start, start_line, start_col);
            }
            continue;
        }
        if (c == '\n') {
            lx.i += 1; lx.line++; lx.col = 1;
            emit(&lx, TK_NEWLINE, lx.p+start, 1, start, start_line, start_col);
            continue;
        }

        /* Whitespace run (excluding newlines) */
        if (c==' ' || c=='\t' || c=='\v' || c=='\f') {
            size_t j = lx.i+1;
            while (j<lx.n) {
                unsigned char d = lx.p[j];
                if (d==' '||d=='\t'||d=='\v'||d=='\f') j++;
                else break;
            }
            lx.i = j; lx.col += (j-start);
            emit(&lx, TK_WS, lx.p+start, j-start, start, start_line, start_col);
            continue;
        }

        /* Preprocessor line starting with '#' at column 1 */
        if (c=='#' && lx.col==1) {
            size_t j = lx.i+1;
            /* continuation handled inline; no flag needed */
            while (j < lx.n) {
                unsigned char d = lx.p[j];
                if (d=='\r') {
                    /* Check CRLF; treat as newline; stop if not continued */
                    if (j>start && lx.p[j-1]=='\\') { /* continued */
                        if (j+1 < lx.n && lx.p[j+1]=='\n') { j+=2; continue; }
                        else { j+=1; continue; }
                    }
                    break;
                } else if (d=='\n') {
                    if (j>start && lx.p[j-1]=='\\') { j++; continue; }
                    break;
                } else {
                    j++;
                }
            }
            size_t len = j - start;
            lx.i = j; lx.col += len;
            emit(&lx, TK_PREPROC, lx.p+start, len, start, start_line, start_col);
            continue;
        }

        /* Comments */
        if (c=='/' && lx.i+1<lx.n) {
            unsigned char n1 = lx.p[lx.i+1];
            if (n1=='/') {
                size_t j = lx.i+2;
                while (j<lx.n && lx.p[j] != '\n' && lx.p[j] != '\r') j++;
                lx.i = j; lx.col += (j-start);
                emit(&lx, TK_LINE_COMMENT, lx.p+start, j-start, start, start_line, start_col);
                continue;
            } else if (n1=='*') {
                size_t j = lx.i+2;
                while (j+1<lx.n && !(lx.p[j]=='*' && lx.p[j+1]=='/')) j++;
                if (j+1 < lx.n) j+=2; /* include closing */ 
                lx.i = j; lx.col += (j-start);
                emit(&lx, TK_BLOCK_COMMENT, lx.p+start, j-start, start, start_line, start_col);
                continue;
            }
        }

        /* String literal */
        if (c=='\"') {
            size_t j = lx.i+1;
            
            while (j<lx.n) {
                unsigned char d = lx.p[j++];
                if (d=='\\') {
                    if (j<lx.n) j++; /* skip escaped char */
                } else if (d=='\"') {
                    break;
                }
            }
            size_t len = j - start;
            lx.i = j; lx.col += len;
            emit(&lx, TK_STRING, lx.p+start, len, start, start_line, start_col);
            continue;
        }

        /* Char literal */
        if (c=='\'') {
            size_t j = lx.i+1;
            
            while (j<lx.n) {
                unsigned char d = lx.p[j++];
                if (d=='\\') {
                    if (j<lx.n) j++; /* skip escaped char */
                } else if (d=='\'') {
                    break;
                }
            }
            size_t len = j - start;
            lx.i = j; lx.col += len;
            emit(&lx, TK_CHAR, lx.p+start, len, start, start_line, start_col);
            continue;
        }

        /* Identifier / keyword (C identifier rules) */
        if (isalpha(c) || c=='_') {
            size_t j = lx.i+1;
            while (j<lx.n) {
                unsigned char d = lx.p[j];
                if (isalnum(d) || d=='_') j++; else break;
            }
            size_t len = j - start;
            TokKind k = is_keyword((const char*)lx.p+start, len) ? TK_KEYWORD : TK_IDENT;
            lx.i = j; lx.col += len;
            emit(&lx, k, lx.p+start, len, start, start_line, start_col);
            continue;
        }

        /* Number literal (simple, accepts hex/dec/octal/floats/suffixes) */
        if (isdigit(c) || (c=='.' && lx.i+1<lx.n && isdigit(lx.p[lx.i+1]))) {
            size_t j = lx.i;
            
            if (lx.p[j]=='0' && j+1<lx.n && (lx.p[j+1]=='x'||lx.p[j+1]=='X')) {
                j+=2;
                while (j<lx.n && (isxdigit(lx.p[j]) || lx.p[j]=='\'')) j++;
            } else {
                while (j<lx.n && (isdigit(lx.p[j]) || lx.p[j]=='\'')) j++;
                if (j<lx.n && lx.p[j]=='.') { j++; while (j<lx.n && (isdigit(lx.p[j])||lx.p[j]=='\'')) j++; }
                if (j<lx.n && (lx.p[j]=='e'||lx.p[j]=='E'||lx.p[j]=='p'||lx.p[j]=='P')) {
                    j++;
                    if (j<lx.n && (lx.p[j]=='+'||lx.p[j]=='-')) j++;
                    while (j<lx.n && isxdigit(lx.p[j])) j++;
                }
            }
            /* Suffixes */
            while (j<lx.n && (isalpha(lx.p[j]) || lx.p[j]=='_')) j++;
            size_t len = j - start;
            lx.i = j; lx.col += len;
            emit(&lx, TK_NUMBER, lx.p+start, len, start, start_line, start_col);
            continue;
        }

        /* Punctuators/operators */
        size_t plen = match_punct(lx.p + lx.i, lx.n - lx.i);
        if (plen > 0) {
            lx.i += plen; lx.col += plen;
            emit(&lx, TK_PUNCT, lx.p+start, plen, start, start_line, start_col);
            continue;
        }

        /* Fallback: unknown byte, emit as PUNCT to preserve */
        lx.i += 1; lx.col += 1;
        emit(&lx, TK_PUNCT, lx.p+start, 1, start, start_line, start_col);
    }
}

/* ---------- Output helpers ---------- */
/* ---------- Portable line reader (no POSIX getline dependency) ---------- */
static long read_line(FILE *in, char **line, size_t *cap) {
    if (!*line || *cap == 0) {
        *cap = 4096;
        *line = (char*)malloc(*cap);
        if (!*line) return -1;
    }
    size_t len = 0;
    int ch;
    while ((ch = fgetc(in)) != EOF) {
        if (len + 2 >= *cap) {
            size_t ncap = (*cap) * 2;
            char *tmp = (char*)realloc(*line, ncap);
            if (!tmp) return -1;
            *line = tmp; *cap = ncap;
        }
        (*line)[len++] = (char)ch;
        if (ch == '\n') break;
    }
    if (len == 0 && ch == EOF) return -1;
    (*line)[len] = '\0';
    return (long)len;
}

static FILE *open_out(const char *path) {
    if (!path || strcmp(path,"-")==0) return stdout;
    FILE *f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "Failed to open %s for write: %s\n", path, strerror(errno)); exit(1); }
    return f;
}

/* ---------- CLI parsing ---------- */
static void die_usage(void) {
    fprintf(stderr,
        "Usage:\n"
        "  ctokenize_v2 stream [--out OUT.jsonl] [--stdin NAME] [files...]\n"
        "  ctokenize_v2 stats  [--out OUT.json]  [files...]\n"
        "  ctokenize_v2 vocab  [--out OUT.tsv]   [files...]\n"
        "  ctokenize_v2 reassemble --in STREAM.jsonl [--outdir DIR]\n"
    );
    exit(2);
}

typedef struct {
    uint64_t total_tokens;
    uint64_t total_bytes;
    uint64_t total_files;
    uint64_t total_lines;
    Metrics m;
} Agg;

static void agg_add(Agg *a, const Metrics *m) {
    for (int i=0;i<16;++i) a->m.counts[i] += m->counts[i];
    a->m.tokens_total += m->tokens_total;
    a->m.bytes_total  += m->bytes_total;
    a->m.bytes_comments += m->bytes_comments;
    a->m.bytes_whitespace += m->bytes_whitespace;
    a->m.lines += m->lines;
}

/* ---------- stream/stats/vocab drivers ---------- */
static void process_files_stream_stats_vocab(char **files, int nfiles, const char *stdin_name,
                                             FILE *out_stream, int do_stats, FILE *out_stats,
                                             int do_vocab, FILE *out_vocab) {
    Agg agg = {0};
    VMap vmap; VMap *vmap_p = NULL;
    if (do_vocab) { vmap_init(&vmap, 1<<15); vmap_p = &vmap; }

    for (int fi=0; fi<nfiles || (nfiles==0 && fi==0); ++fi) {
        const char *fname = NULL;
        Buf b={0};
        if (nfiles==0) {
            fname = stdin_name ? stdin_name : "stdin";
            if (read_file("-", &b) != 0) exit(1);
        } else {
            fname = files[fi];
            if (read_file(fname, &b) != 0) exit(1);
        }

        Metrics mx = {0};
        mx.bytes_total = b.n;
        if (out_stream) {
            /* Optionally emit a file-start marker (comment) for readability (not required) */
            /* fprintf(out_stream, "{\"file\":\"%s\",\"off\":0,\"line\":1,\"col\":1,\"kind\":\"META\",\"lexeme\":\"BEGIN\"}\n", fname); */
        }
        lex_file(&b, fname, out_stream, &mx, vmap_p);
        agg_add(&agg, &mx);
        agg.total_files++;
        free(b.p);
    }

    /* Stats output */
    if (do_stats) {
        fprintf(out_stats, "{");
        fprintf(out_stats, "\"files\":%llu,", (unsigned long long)agg.total_files);
        fprintf(out_stats, "\"tokens\":%llu,", (unsigned long long)agg.m.tokens_total);
        fprintf(out_stats, "\"bytes\":%llu,", (unsigned long long)agg.m.bytes_total);
        fprintf(out_stats, "\"lines\":%llu,", (unsigned long long)agg.m.lines);
        fprintf(out_stats, "\"bytes_comments\":%llu,", (unsigned long long)agg.m.bytes_comments);
        fprintf(out_stats, "\"bytes_whitespace\":%llu,", (unsigned long long)agg.m.bytes_whitespace);
        fprintf(out_stats, "\"kinds\":{");
        for (int k=0;k<=TK_PUNCT;++k) {
            fprintf(out_stats, "\"%s\":%llu", kind_name((TokKind)k), (unsigned long long)agg.m.counts[k]);
            if (k!=TK_PUNCT) fputc(',', out_stats);
        }
        fprintf(out_stats, "}");
        fprintf(out_stats, "}\n");
    }

    /* Vocab output (identifiers+keywords) */
    if (do_vocab) {
        /* Dump unsorted; downstream can sort by count */
        for (size_t i=0;i<vmap.nbkt;++i) {
            for (VEntry *e=vmap.bkt[i]; e; e=e->next) {
                fprintf(out_vocab, "%s\t%llu\n", e->s, (unsigned long long)e->count);
            }
        }
        vmap_free(&vmap);
    }
}


/* ----- Path utilities for reassemble (handle Windows drive letters, make dirs) ----- */
static char *str_dup(const char *s) {
    size_t n = strlen(s);
    char *r = (char*)malloc(n+1);
    if (!r) { fprintf(stderr,"OOM\n"); exit(1); }
    memcpy(r,s,n+1);
    return r;
}
static char *sanitize_relpath(const char *name) {
    /* Convert backslashes to '/', drop drive "X:" prefix, strip leading slashes,
       and replace any remaining ':' to '_' to avoid invalid filenames. */
    char *tmp = str_dup(name);
    for (char *p=tmp; *p; ++p) { if (*p=='\\') *p='/'; }
    if (isalpha((unsigned char)tmp[0]) && tmp[1]==':') {
        /* drop "X:" */
        memmove(tmp, tmp+2, strlen(tmp+2)+1);
    }
    while (tmp[0]=='/' || tmp[0]=='\\') memmove(tmp, tmp+1, strlen(tmp+1)+1);
    for (char *p=tmp; *p; ++p) { if (*p==':') *p='_'; }
    /* Very simple traversal guard: replace ".." with "__" */
    for (char *p=tmp; (p=strstr(p,"..")); ) { p[0]='_'; p[1]='_'; p+=2; }
    return tmp;
}
static void mkdir_p_for_file(const char *path) {
    /* Create all parent directories of 'path' */
    char *tmp = str_dup(path);
    for (size_t i=0; tmp[i]; ++i) {
        if (tmp[i]=='/' || tmp[i]=='\\') {
            char c = tmp[i];
            tmp[i] = 0;
            if (strlen(tmp) > 0) {
                struct stat st;
                if (stat(tmp, &st) != 0) {
                    MKDIR(tmp);
                }
            }
            tmp[i] = c;
        }
    }
    free(tmp);
}
static const char *basename_pos(const char *path) {
    const char *p = strrchr(path, '/');
    const char *q = strrchr(path, '\\');
    const char *m = p > q ? p : q;
    return m ? m+1 : path;
}

/* ---------- Reassembler ---------- */
typedef struct OutFile {
    char *name;
    FILE *f;
    struct OutFile *next;
} OutFile;


static OutFile *of_find_or_open(OutFile **head, const char *name, const char *outdir) {
    /* Build a safe output path.
       If outdir is provided: outdir + '/' + sanitized relative path + '.recon'
       Else: basename(name) + '.recon' in CWD. */
    char *rel = sanitize_relpath(name);
    const char *base = basename_pos(rel);
    char *rel_or_base = NULL;
    if (outdir && outdir[0]) {
        rel_or_base = rel; /* keep subdirs under outdir */
    } else {
        rel_or_base = (char*)base; /* just filename */
    }

    size_t n_outdir = (outdir && outdir[0]) ? strlen(outdir) : 0;
    size_t n_rel = strlen(rel_or_base);
    size_t need = n_outdir + (n_outdir?1:0) + n_rel + 6 /* .recon */ + 1;
    char *full = (char*)malloc(need);
    if (!full) { fprintf(stderr,"OOM\n"); exit(1); }
    if (n_outdir) {
        memcpy(full, outdir, n_outdir);
        full[n_outdir] = '/';
        memcpy(full + n_outdir + 1, rel_or_base, n_rel);
        memcpy(full + n_outdir + 1 + n_rel, ".recon", 6+1);
    } else {
        memcpy(full, rel_or_base, n_rel);
        memcpy(full + n_rel, ".recon", 6+1);
    }

    /* Ensure directories exist */
    mkdir_p_for_file(full);

    /* Make sure list doesn't already have this path */
    for (OutFile *p=*head; p; p=p->next) if (strcmp(p->name,full)==0) { free(rel); free(full); return p; }

    OutFile *n = (OutFile*)malloc(sizeof(OutFile));
    if (!n) { fprintf(stderr,"OOM\n"); exit(1); }
    n->name = full;
    n->f = fopen(n->name, "wb");
    if (!n->f) { fprintf(stderr,"Failed to open %s: %s\n", n->name, strerror(errno)); exit(1); }
    n->next = *head; *head = n;
    free(rel);
    return n;
}

static void reassemble(const char *in_path, const char *outdir) {
    FILE *in = strcmp(in_path,"-")==0 ? stdin : fopen(in_path,"rb");
    if (!in) { fprintf(stderr,"Failed to open %s: %s\n", in_path, strerror(errno)); exit(1); }
    OutFile *files = NULL;
    char *line = NULL; size_t cap=0;
    while (1) {
        long r = read_line(in, &line, &cap);
        if (r < 0) break;
        /* Find "file":"..."," and "lexeme":"..." */
        const char *p = strstr(line, "\"file\":\"");
        if (!p) continue;
        p += 8;
        const char *q = strchr(p, '\"');
        if (!q) continue;
        size_t fname_len = (size_t)(q - p);
        char *fname = (char*)malloc(fname_len+1); memcpy(fname,p,fname_len); fname[fname_len]=0;

        const char *lx = strstr(q, "\"lexeme\":\"");
        if (!lx) { free(fname); continue; }
        lx += 10;
        /* Extract JSON string until closing quote not escaped */
        size_t bufcap = r; char *raw = (char*)malloc(bufcap);
        size_t j=0;
        for (const char *s=lx; *s; ++s) {
            char ch = *s;
            if (ch=='\"') {
                /* Check if escaped */
                size_t back=0; const char *t=s-1;
                while (t>=lx && *t=='\\') { back++; t--; }
                if ((back % 2)==0) { /* not escaped */
                    break;
                }
            }
            raw[j++] = ch;
        }
        raw[j]=0;
        size_t lex_len=0;
        unsigned char *lex = json_unescape_alloc(raw, &lex_len);
        free(raw);

        OutFile *of = of_find_or_open(&files, fname, outdir);
        fwrite(lex, 1, lex_len, of->f);

        free(lex);
        free(fname);
    }
    /* close */
    for (OutFile *p=files; p;) { fclose(p->f); OutFile *n=p->next; free(p->name); free(p); p=n; }
    if (in!=stdin) fclose(in);
}

/* ---------- main ---------- */
int main(int argc, char **argv) {
    if (argc < 2) die_usage();
    const char *cmd = argv[1];

    if (strcmp(cmd,"stream")==0) {
        const char *out_path = NULL;
        const char *stdin_name = NULL;
        int i=2;
        /* parse options */
        for (; i<argc; ++i) {
            if (strcmp(argv[i],"--out")==0 && i+1<argc) { out_path = argv[++i]; continue; }
            if (strcmp(argv[i],"--stdin")==0 && i+1<argc) { stdin_name = argv[++i]; continue; }
            if (argv[i][0]=='-') { fprintf(stderr,"Unknown option: %s\n", argv[i]); die_usage(); }
            break;
        }
        FILE *out = open_out(out_path);
        char **files = NULL; int nfiles = argc - i;
        if (nfiles>0) files = &argv[i];
        process_files_stream_stats_vocab(files, nfiles, stdin_name, out, 0, NULL, 0, NULL);
        if (out && out!=stdout) fclose(out);
        return 0;
    } else if (strcmp(cmd,"stats")==0) {
        const char *out_path = NULL;
        int i=2;
        for (; i<argc; ++i) {
            if (strcmp(argv[i],"--out")==0 && i+1<argc) { out_path = argv[++i]; continue; }
            if (argv[i][0]=='-') { fprintf(stderr,"Unknown option: %s\n", argv[i]); die_usage(); }
            break;
        }
        FILE *out = open_out(out_path);
        char **files = NULL; int nfiles = argc - i;
        if (nfiles>0) files = &argv[i];
        process_files_stream_stats_vocab(files, nfiles, NULL, NULL, 1, out, 0, NULL);
        if (out && out!=stdout) fclose(out);
        return 0;
    } else if (strcmp(cmd,"vocab")==0) {
        const char *out_path = NULL;
        int i=2;
        for (; i<argc; ++i) {
            if (strcmp(argv[i],"--out")==0 && i+1<argc) { out_path = argv[++i]; continue; }
            if (argv[i][0]=='-') { fprintf(stderr,"Unknown option: %s\n", argv[i]); die_usage(); }
            break;
        }
        FILE *out = open_out(out_path);
        char **files = NULL; int nfiles = argc - i;
        if (nfiles>0) files = &argv[i];
        process_files_stream_stats_vocab(files, nfiles, NULL, NULL, 0, NULL, 1, out);
        if (out && out!=stdout) fclose(out);
        return 0;
    } else if (strcmp(cmd,"reassemble")==0) {
        const char *in_path = NULL;
        const char *outdir = NULL;
        int i=2;
        for (; i<argc; ++i) {
            if (strcmp(argv[i],"--in")==0 && i+1<argc) { in_path = argv[++i]; continue; }
            if (strcmp(argv[i],"--outdir")==0 && i+1<argc) { outdir = argv[++i]; continue; }
            if (argv[i][0]=='-') { fprintf(stderr,"Unknown option: %s\n", argv[i]); die_usage(); }
        }
        if (!in_path) die_usage();
        reassemble(in_path, outdir);
        return 0;
    } else {
        die_usage();
    }
}
