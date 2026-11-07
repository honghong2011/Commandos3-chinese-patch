# -*- coding: utf-8 -*-
"""Commandos3.exe 反汇编助手：VA<->文件偏移、线性反汇编、交叉引用。"""
import os
import struct
import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = os.environ.get('C3EXE') or (r'G:\steam\steamapps\common'
    r'\Commandos 3 Destination Berlin\Commandos3.exe')
_exe = open(EXE, 'rb').read()

_pe = struct.unpack_from('<I', _exe, 0x3C)[0]
_nsec = struct.unpack_from('<H', _exe, _pe + 6)[0]
_opt = struct.unpack_from('<H', _exe, _pe + 20)[0]
_s0 = _pe + 24 + _opt
SECS = []
for k in range(_nsec):
    nm = _exe[_s0 + 40 * k: _s0 + 40 * k + 8].rstrip(b'\0').decode('latin-1')
    vsz, va, rsz, raw = struct.unpack_from('<IIII', _exe, _s0 + 40 * k + 8)
    SECS.append((nm, va, vsz, rsz, raw))

_md = Cs(CS_ARCH_X86, CS_MODE_32)


def va2off(va):
    r = va - 0x400000
    for nm, v, vsz, rsz, raw in SECS:
        if v <= r < v + max(vsz, rsz):
            return raw + (r - v)
    return None


def off2va(off):
    for nm, v, vsz, rsz, raw in SECS:
        if raw <= off < raw + rsz:
            return 0x400000 + v + (off - raw)
    return None


def dis(va, n=40, mark=None):
    off = va2off(va)
    code = _exe[off:off + n * 8]
    out = []
    for ins in _md.disasm(code, va):
        tag = '  <<<' if mark and ins.address in mark else ''
        out.append('%08x  %-8s %s%s' % (ins.address, ins.mnemonic,
                                        ins.op_str, tag))
        if len(out) >= n:
            break
    return '\n'.join(out)


def xrefs_to(va):
    """call/jmp rel32 与 push imm32 引用。"""
    hits = []
    for nm, v, vsz, rsz, raw in SECS:
        if nm != '.text':
            continue
        blob = _exe[raw:raw + rsz]
        for i in range(len(blob) - 5):
            op = blob[i]
            if op in (0xE8, 0xE9):
                rel = struct.unpack_from('<i', blob, i + 1)[0]
                src = off2va(raw + i)
                if src + 5 + rel == va:
                    hits.append((src, 'call' if op == 0xE8 else 'jmp'))
            elif op == 0x68:
                imm = struct.unpack_from('<I', blob, i + 1)[0]
                if imm == va:
                    hits.append((off2va(raw + i), 'push'))
    return hits


def read_bytes(va, n):
    off = va2off(va)
    return _exe[off:off + n]


if __name__ == '__main__':
    va = int(sys.argv[1], 16)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    print(dis(va, n))
