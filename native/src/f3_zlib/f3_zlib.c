/* f3_zlib: zlib 1.4's deflate (./zlib, unmodified) behind one exported call, loaded by
 * fo4_import/base/pinned_zlib.py through ctypes. Every machine compresses with this copy, so the
 * same input gives the same bytes whatever zlib the Python was built with.
 * See: docs/fork/fo4_pipeline.md#pinned-zlib */
#include <string.h>
#include "zlib/zlib.h"

#ifdef _WIN32
#define F3_EXPORT __declspec(dllexport)
#else
#define F3_EXPORT __attribute__((visibility("default")))
#endif

/* Deflate source[0..source_len) into dest (capacity *dest_len) at `level` with `window_bits`
 * (15: zlib stream, -15: raw deflate), memory level 8 and the default strategy, as Python's
 * zlib.compress does. Sets *dest_len to the bytes written; returns Z_OK or a zlib error. */
F3_EXPORT int f3_deflate(unsigned char *dest, unsigned long *dest_len, const unsigned char *source,
                         unsigned long source_len, int level, int window_bits)
{
    z_stream stream;
    int err;

    memset(&stream, 0, sizeof stream);
    err = deflateInit2(&stream, level, Z_DEFLATED, window_bits, 8, Z_DEFAULT_STRATEGY);
    if (err != Z_OK)
        return err;
    stream.next_in = (z_const Bytef *)source;
    stream.avail_in = (uInt)source_len;
    stream.next_out = dest;
    stream.avail_out = (uInt)*dest_len;
    err = deflate(&stream, Z_FINISH);
    *dest_len = stream.total_out;
    deflateEnd(&stream);
    if (err == Z_STREAM_END)
        return Z_OK;
    return err == Z_OK ? Z_BUF_ERROR : err;
}

/* The zlib version this library was built from. */
F3_EXPORT const char *f3_version(void)
{
    return zlibVersion();
}
