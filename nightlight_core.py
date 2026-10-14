"""DRM gamma LUT driver for the Miyoo Flip V2, tested kernel 5.10.160.

Apply only after the KMS/SDL app has relinquished DRM master. Values saved
only after kernel accepts and confirms the property value. No autostart.
"""
import ctypes as C
import json
import os
import re
import subprocess

DEVICE = '/dev/dri/card0'
SETTINGS = '/mnt/SDCARD/Saves/spruce/nightlight-settings.json'
DRM_CLIENT_CAP_ATOMIC = 3
DRM_MODE_OBJECT_CRTC = 0xCCCCCCCC
DEFAULT = {'enabled': False, 'intensity': 50, 'amber': 50}


class ColorLut(C.Structure):
    _fields_ = [('red', C.c_uint16), ('green', C.c_uint16),
                ('blue', C.c_uint16), ('reserved', C.c_uint16)]


class ObjectProperties(C.Structure):
    _fields_ = [('count_props', C.c_uint32),
                ('props', C.POINTER(C.c_uint32)),
                ('prop_values', C.POINTER(C.c_uint64))]


def clamp_int(number, default):
    try:
        return max(0, min(100, int(number)))
    except (ValueError, TypeError):
        return default


def load_settings():
    data = dict(DEFAULT)
    try:
        with open(SETTINGS, encoding='utf-8') as stream:
            saved = json.load(stream)
        if isinstance(saved, dict):
            if type(saved.get('enabled')) is bool:
                data['enabled'] = saved['enabled']
            data['intensity'] = clamp_int(saved.get('intensity'), 50)
            data['amber'] = clamp_int(saved.get('amber'), 50)
    except (OSError, ValueError):
        pass
    return data


def save_settings(data):
    parent = os.path.dirname(SETTINGS)
    os.makedirs(parent, exist_ok=True)
    tmp = SETTINGS + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, SETTINGS)


def discover_crtc():
    """Match one active 640x480 CRTC, not its object/property IDs."""
    cmd = subprocess.run(['modetest', '-D', DEVICE, '-p'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, timeout=12)
    if cmd.returncode:
        raise RuntimeError('modetest failed: ' + cmd.stderr.strip())
    try:
        section = cmd.stdout.split('CRTCs:', 1)[1].split('Planes:', 1)[0]
    except IndexError:
        raise RuntimeError('modetest output has no CRTC section')
    heads = list(re.finditer(
        r'^(\d+)\s+(\d+)\s+\((-?\d+),(-?\d+)\)\s+\((\d+)x(\d+)\)',
        section, re.M))
    matches = []
    for index, header in enumerate(heads):
        crtc_id, framebuffer, _, _, w, h = map(int, header.groups())
        if framebuffer == 0 or (w, h) != (640, 480):
            continue
        end = heads[index + 1].start() if index + 1 < len(heads) else len(section)
        body = section[header.end():end]
        lut_match = re.search(r'^\s*(\d+) GAMMA_LUT:', body, re.M)
        size_match = re.search(
            r'^\s*\d+ GAMMA_LUT_SIZE:\s*\n(?:.*\n)*?\s*value:\s*(\d+)',
            body, re.M)
        if lut_match and size_match:
            matches.append((crtc_id, int(lut_match.group(1)),
                            int(size_match.group(1))))
    if len(matches) != 1:
        raise RuntimeError('Expected 1 active 640x480 CRTC; found %d' % len(matches))
    if matches[0][2] != 1024:
        raise RuntimeError('Unsupported LUT size: %d' % matches[0][2])
    return matches[0]


def check(rc, name):
    if rc < 0:
        errno = C.get_errno() or (-rc if rc < -1 else 0)
        raise OSError('%s failed (rc=%d%s)' % (
            name, rc, ': ' + os.strerror(errno) if errno else ''))


def drm_library():
    d = C.CDLL('libdrm.so.2', use_errno=True)
    d.drmSetClientCap.argtypes = (C.c_int, C.c_uint64, C.c_uint64)
    d.drmSetClientCap.restype = C.c_int
    d.drmModeCreatePropertyBlob.argtypes = (C.c_int, C.c_void_p,
                                            C.c_size_t, C.POINTER(C.c_uint32))
    d.drmModeCreatePropertyBlob.restype = C.c_int
    d.drmModeDestroyPropertyBlob.argtypes = (C.c_int, C.c_uint32)
    d.drmModeDestroyPropertyBlob.restype = C.c_int
    d.drmModeAtomicAlloc.argtypes = ()
    d.drmModeAtomicAlloc.restype = C.c_void_p
    d.drmModeAtomicAddProperty.argtypes = (C.c_void_p, C.c_uint32,
                                           C.c_uint32, C.c_uint64)
    d.drmModeAtomicAddProperty.restype = C.c_int
    d.drmModeAtomicCommit.argtypes = (C.c_int, C.c_void_p,
                                      C.c_uint32, C.c_void_p)
    d.drmModeAtomicCommit.restype = C.c_int
    d.drmModeAtomicFree.argtypes = (C.c_void_p,)
    d.drmModeAtomicFree.restype = None
    d.drmModeObjectGetProperties.argtypes = (C.c_int, C.c_uint32, C.c_uint32)
    d.drmModeObjectGetProperties.restype = C.POINTER(ObjectProperties)
    d.drmModeFreeObjectProperties.argtypes = (C.POINTER(ObjectProperties),)
    d.drmModeFreeObjectProperties.restype = None
    return d


def get_gamma_blob(d, fd, crtc, prop):
    obj = d.drmModeObjectGetProperties(fd, crtc, DRM_MODE_OBJECT_CRTC)
    if not obj:
        raise RuntimeError('Cannot read CRTC properties')
    try:
        for i in range(obj.contents.count_props):
            if obj.contents.props[i] == prop:
                return int(obj.contents.prop_values[i])
    finally:
        d.drmModeFreeObjectProperties(obj)
    raise RuntimeError('GAMMA_LUT property missing')


def commit(d, fd, crtc, prop, blob):
    req = d.drmModeAtomicAlloc()
    if not req:
        raise RuntimeError('Atomic allocation failed')
    try:
        check(d.drmModeAtomicAddProperty(req, crtc, prop, blob),
              'drmModeAtomicAddProperty')
        check(d.drmModeAtomicCommit(fd, req, 0, None),
              'drmModeAtomicCommit')
    finally:
        d.drmModeAtomicFree(req)


def channel_multipliers(settings):
    if not settings['enabled']:
        return (1.0, 1.0, 1.0)
    strength = clamp_int(settings['intensity'], 50) / 100.0
    amber = clamp_int(settings['amber'], 50) / 100.0
    # Reproduce the visually tested v3 LUT at 50/50: R=1.0, G=.84, B=.60.
    return (1.0, 1.0 - strength * (0.16 + 0.32 * amber),
            1.0 - strength * 0.80)


def apply(settings, crtc_info):
    """Commit an explicit LUT, including for OFF (never just GAMMA_LUT=0).

    crtc_info was detected *before* the UI began. The display may temporarily
    show no active FB after SDL shutdown; the CRTC/property IDs remain valid.
    """
    crtc, prop, count = crtc_info
    if count != 1024:
        raise RuntimeError('Refusing unexpected LUT count')
    multipliers = channel_multipliers(settings)
    d = drm_library()
    fd = os.open(DEVICE, os.O_RDWR | os.O_CLOEXEC)
    blob = C.c_uint32(0)
    try:
        check(d.drmSetClientCap(fd, DRM_CLIENT_CAP_ATOMIC, 1), 'drmSetClientCap')
        previous = get_gamma_blob(d, fd, crtc, prop)
        print('CRTC %d prop %d previous blob %d' % (crtc, prop, previous), flush=True)
        lut = (ColorLut * count)()
        for index in range(count):
            sample = round(index * 65535 / (count - 1))
            lut[index] = ColorLut(*(min(65535, max(0, round(sample * scale)))
                                    for scale in multipliers), 0)
        check(d.drmModeCreatePropertyBlob(fd, C.cast(lut, C.c_void_p),
                                          C.sizeof(lut), C.byref(blob)),
              'drmModeCreatePropertyBlob')
        print('Applying %s LUT blob %d; RGB %s' % (
            'warm' if settings['enabled'] else 'neutral',
            blob.value, str(tuple(round(c, 3) for c in multipliers))), flush=True)
        commit(d, fd, crtc, prop, blob.value)
        actual = get_gamma_blob(d, fd, crtc, prop)
        if actual != blob.value:
            raise RuntimeError('Gamma readback mismatch: expected %d, got %d' %
                               (blob.value, actual))
        save_settings(settings)
        print('SUCCESS: display LUT set and settings saved', flush=True)
    finally:
        if blob.value:
            d.drmModeDestroyPropertyBlob(fd, blob.value)
        os.close(fd)
