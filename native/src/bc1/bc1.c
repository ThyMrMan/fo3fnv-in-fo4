/*
 * f3_bc1: BC1 blocks of an RGB image, the algorithm of fo4_import/base/dds_encode.py (bc1_blocks) in C.
 *
 * Each 4x4 block's endpoints lie on its colours' principal axis (power iteration on the covariance), inset by a
 * sixteenth of the span, then are refitted by least squares on the indices they chose; the fit with less squared
 * error is kept. Single or double precision as the numpy code computes each value.
 * See docs/fork/fo4_facegen_plan.md#own-dds-encoder.
 */
#include <math.h>
#include <stdint.h>
#include <string.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

#define AXIS_STEPS 8

static const double WEIGHTS[4] = {1.0, 0.0, 2.0 / 3.0, 1.0 / 3.0};
static const uint8_t STEP_CODES[4] = {1, 3, 2, 0};

typedef struct {
    int c0, c1;
    uint8_t codes[16];
    float error;
} Fit;

static int to_565(const double rgb[3])
{
    static const double SCALE[3] = {31, 63, 31};
    int q[3];
    for (int c = 0; c < 3; c++) {
        double v = nearbyint(rgb[c] * SCALE[c] / 255);
        q[c] = (int)(v < 0 ? 0 : v > SCALE[c] ? SCALE[c] : v);
    }
    return (q[0] << 11) | (q[1] << 5) | q[2];
}

static void from_565(int c, float out[3])
{
    int r = (c >> 11) & 0x1F, g = (c >> 5) & 0x3F, b = c & 0x1F;
    out[0] = (float)((r << 3) | (r >> 2));
    out[1] = (float)((g << 2) | (g >> 4));
    out[2] = (float)((b << 3) | (b >> 2));
}

static void quantised(const float px[16][3], const double e0[3], const double e1[3], Fit *fit)
{
    int c0 = to_565(e0), c1 = to_565(e1);
    int hi = c0 > c1 ? c0 : c1, lo = c0 > c1 ? c1 : c0;
    if (hi == lo) {
        if (hi == 0)
            hi = 1;
        else
            lo = hi - 1;
    }
    float p0[3], p1[3], line[3];
    from_565(hi, p0);
    from_565(lo, p1);
    float len = 0;
    for (int c = 0; c < 3; c++) {
        line[c] = p0[c] - p1[c];
        len += line[c] * line[c];
    }
    if (len < 1e-6f)
        len = 1e-6f;
    float error = 0;
    for (int i = 0; i < 16; i++) {
        float t = 0;
        for (int c = 0; c < 3; c++)
            t += (px[i][c] - p1[c]) * line[c];
        float s = nearbyintf(t / len * 3);
        int step = (int)(s < 0 ? 0 : s > 3 ? 3 : s);
        float e = 0;
        for (int c = 0; c < 3; c++) {
            float d = px[i][c] - (p1[c] + ((float)step / 3.0f) * line[c]);
            e += d * d;
        }
        error += e;
        fit->codes[i] = STEP_CODES[step];
    }
    fit->c0 = hi;
    fit->c1 = lo;
    fit->error = error;
}

static void axis_of(const float centred[16][3], double axis[3])
{
    float cov[3][3] = {{0}}, a[3];
    for (int r = 0; r < 3; r++)
        for (int c = 0; c < 3; c++)
            for (int i = 0; i < 16; i++)
                cov[r][c] += centred[i][r] * centred[i][c];
    for (int c = 0; c < 3; c++) {
        float mx = centred[0][c], mn = centred[0][c];
        for (int i = 1; i < 16; i++) {
            mx = centred[i][c] > mx ? centred[i][c] : mx;
            mn = centred[i][c] < mn ? centred[i][c] : mn;
        }
        a[c] = mx - mn + 1e-3f;
    }
    for (int step = 0; step < AXIS_STEPS; step++) {
        float n[3], norm = 0;
        for (int r = 0; r < 3; r++) {
            n[r] = cov[r][0] * a[0] + cov[r][1] * a[1] + cov[r][2] * a[2];
            norm += n[r] * n[r];
        }
        norm = sqrtf(norm);
        if (norm < 1e-9f)
            norm = 1e-9f;
        for (int r = 0; r < 3; r++)
            a[r] = n[r] / norm;
    }
    int flat = !(fabsf(a[0]) + fabsf(a[1]) + fabsf(a[2]) > 0.5f);
    for (int c = 0; c < 3; c++)
        axis[c] = flat ? 1 / sqrt(3.0) : (double)a[c];
}

static void refit(const float px[16][3], const uint8_t codes[16], const double e0[3], const double e1[3],
                  double out0[3], double out1[3])
{
    double aa = 0, bb = 0, ab = 0, ax[3] = {0}, bx[3] = {0};
    for (int i = 0; i < 16; i++) {
        double a = WEIGHTS[codes[i]], b = 1 - a;
        aa += a * a;
        bb += b * b;
        ab += a * b;
        for (int c = 0; c < 3; c++) {
            ax[c] += a * px[i][c];
            bx[c] += b * px[i][c];
        }
    }
    double det = aa * bb - ab * ab;
    int ok = fabs(det) > 1e-6;
    for (int c = 0; c < 3; c++) {
        double v0 = (bb * ax[c] - ab * bx[c]) / det, v1 = (aa * bx[c] - ab * ax[c]) / det;
        out0[c] = ok ? (v0 < 0 ? 0 : v0 > 255 ? 255 : v0) : e0[c];
        out1[c] = ok ? (v1 < 0 ? 0 : v1 > 255 ? 255 : v1) : e1[c];
    }
}

static void block(const float px[16][3], uint8_t out[8])
{
    float mean[3] = {0}, centred[16][3];
    for (int i = 0; i < 16; i++)
        for (int c = 0; c < 3; c++)
            mean[c] += px[i][c];
    for (int c = 0; c < 3; c++)
        mean[c] /= 16;
    for (int i = 0; i < 16; i++)
        for (int c = 0; c < 3; c++)
            centred[i][c] = px[i][c] - mean[c];
    double axis[3], lo = INFINITY, hi = -INFINITY;
    axis_of(centred, axis);
    for (int i = 0; i < 16; i++) {
        double t = centred[i][0] * axis[0] + centred[i][1] * axis[1] + centred[i][2] * axis[2];
        lo = t < lo ? t : lo;
        hi = t > hi ? t : hi;
    }
    double inset = (hi - lo) / 16, e0[3], e1[3], r0[3], r1[3];
    for (int c = 0; c < 3; c++) {
        double v0 = mean[c] + (hi - inset) * axis[c], v1 = mean[c] + (lo + inset) * axis[c];
        e0[c] = v0 < 0 ? 0 : v0 > 255 ? 255 : v0;
        e1[c] = v1 < 0 ? 0 : v1 > 255 ? 255 : v1;
    }
    Fit first, second;
    quantised(px, e0, e1, &first);
    refit(px, first.codes, e0, e1, r0, r1);
    quantised(px, r0, r1, &second);
    const Fit *best = second.error < first.error ? &second : &first;
    uint32_t bits = 0;
    for (int i = 0; i < 16; i++)
        bits |= (uint32_t)best->codes[i] << (2 * i);
    out[0] = best->c0 & 0xFF;
    out[1] = best->c0 >> 8;
    out[2] = best->c1 & 0xFF;
    out[3] = best->c1 >> 8;
    memcpy(out + 4, &bits, 4);
}

/* This encoder's version: dds_encode.BC1_VERSION, bumped with every change to what it writes. */
EXPORT int f3_bc1_version(void)
{
    return 1;
}

/* BC1 blocks of `rgb` (height x width x 3 bytes, both multiples of 4) into `out` (8 bytes a block, row-major). */
EXPORT void f3_bc1_blocks(const uint8_t *rgb, int height, int width, uint8_t *out)
{
    for (int by = 0; by < height / 4; by++)
        for (int bx = 0; bx < width / 4; bx++) {
            float px[16][3];
            for (int y = 0; y < 4; y++)
                for (int x = 0; x < 4; x++)
                    for (int c = 0; c < 3; c++)
                        px[y * 4 + x][c] = rgb[((size_t)(by * 4 + y) * width + bx * 4 + x) * 3 + c];
            block(px, out + ((size_t)by * (width / 4) + bx) * 8);
        }
}
