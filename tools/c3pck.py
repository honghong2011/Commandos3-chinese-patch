"""Commandos 3 DATA.PCK handler.

TOC entry layout (reverse-engineered, verified against DATA.PCK / Data2.PCK):
  entry header at N-12:  flag u32 (=1 for files) | parent u32 | nameoff u32 (=N)
  name field at N:       32 bytes, NUL-padded ASCII
  size u32 at N+40
  data_offset u32 at N+44   (0x200-aligned in DATA.PCK)

All game text lives in DATA\\STR\\*.STR inside the root DATA.PCK.
"""
import struct
import os

STR_NAMES = ["BER", "BRIEFINGS", "CP", "CREDITS", "DSP", "END", "GLOBAL",
             "MANUALC3", "PT", "RED", "ST1", "ST2", "TA1", "TC", "TC_01",
             "TE", "TM", "TM_DEMO", "TUT1", "TUT2", "TV"]


def deobf_abs(raw, base):
    """包内绝对偏移去/加混淆（对合）。

    定律（已三重验证）：每 16 字节块首字节 XOR
        key(P) = ((P >> 4) & 0xF) << 4 | (P // 14) & 0xF
    P 为该块在包内的绝对偏移。FONT.CFG 等非 STR 文件走这个定律。
    """
    out = bytearray(raw)
    for k in range((len(out) + 15) // 16):
        p = 16 * k
        if p < len(out):
            P = base + p
            out[p] ^= (((P >> 4) & 0xF) << 4) | ((P // 14) & 0xF)
    return bytes(out)



class PCK:
    def __init__(self, path, scan_window=0x100000):
        self.path = path
        self.fsize = os.path.getsize(path)
        self.f = open(path, 'rb')
        self.entries = {}   # base name -> (size, data_off)
        self._scan(scan_window)

    def _scan(self, window):
        self.f.seek(0)
        head = self.f.read(window)
        for base in STR_NAMES:
            needle = base.encode('ascii') + b'.STR'
            best = None
            pos = 0
            while True:
                i = head.find(needle, pos)
                if i < 0:
                    break
                pos = i + 1
                if i + 48 > len(head):
                    continue
                size, off = struct.unpack_from('<II', head, i + 40)
                if not (0 < size <= 16 << 20):
                    continue
                if off % 0x200 or off + size > self.fsize:
                    continue
                flag_ok = i >= 12 and head[i - 12:i - 8] == b'\x01\x00\x00\x00'
                # prefer flag-valid hits, then the earliest one
                score = (1 if flag_ok else 0, -i)
                if best is None or score > best[0]:
                    best = (score, size, off)
            if best:
                self.entries[base] = best[1:]

    def blob(self, name):
        size, off = self.entries[name]
        self.f.seek(off)
        data = self.f.read(size)
        if len(data) != size:
            raise IOError('short read for ' + name)
        return data

    def splice_to(self, dst, replacements):
        """Write a copy of the pack with some STR blobs replaced.

        replacements: {base_name: new_blob}; each must match the original
        byte length exactly (equal-length policy - TOC is left untouched).
        """
        todo = {}
        for name, nb in replacements.items():
            size, off = self.entries[name]
            if len(nb) != size:
                raise ValueError('%s: new blob %d bytes != original %d'
                                 % (name, len(nb), size))
            todo[off] = (size, nb)
        with open(self.path, 'rb') as src, open(dst, 'wb') as out:
            pos = 0
            for off in sorted(todo):
                size, nb = todo[off]
                self._copy(src, out, off - pos)
                pos = off
                out.write(nb)
                src.seek(off + size)
                pos = off + size
            self._copy(src, out, self.fsize - pos)

    @staticmethod
    def _copy(src, out, nbytes):
        while nbytes > 0:
            chunk = src.read(min(1 << 22, nbytes))
            if not chunk:
                raise IOError('unexpected EOF in source pack')
            out.write(chunk)
            nbytes -= len(chunk)


if __name__ == '__main__':
    import sys
    default = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'backup', 'DATA.PCK.original')
    pck = PCK(sys.argv[1] if len(sys.argv) > 1 else default)
    print('%-12s %10s %12s' % ('NAME', 'SIZE', 'DATA_OFF'))
    total = 0
    for name in STR_NAMES:
        if name in pck.entries:
            size, off = pck.entries[name]
            total += size
            print('%-12s %10d %12s' % (name, size, hex(off)))
        else:
            print('%-12s %10s' % (name, 'NOT FOUND'))
    print('total STR bytes:', total)
