/*
 * xwma_enc: a WAV to xWMA encoder taking xWMAEncode's arguments.
 *
 *     xwma_enc [-b <bits per second>] <in.wav> <out.xwm>
 *
 * The bitrate defaults to 48000. Exits 1 with a message on stderr on failure.
 * See docs/fork/fo4_ck_replacements.md#xwma-spike.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _MSC_VER
#include <intrin.h>

int __builtin_clz(unsigned int x)
{
    unsigned long i;
    _BitScanReverse(&i, x);
    return 31 - (int)i;
}
#endif

void xwma_encode_file(const char *in_path, const char *out_path, int bit_rate);

int main(int argc, char **argv)
{
    int bit_rate = 48000;
    int first = 1;
    if (argc > 2 && !strcmp(argv[1], "-b")) {
        bit_rate = atoi(argv[2]);
        first = 3;
    }
    if (argc != first + 2) {
        fprintf(stderr, "usage: xwma_enc [-b <bits per second>] <in.wav> <out.xwm>\n");
        return 1;
    }
    xwma_encode_file(argv[first], argv[first + 1], bit_rate);
    return 0;
}
