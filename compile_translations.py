"""Turn locale/*/LC_MESSAGES/django.po into django.mo (what Django reads).

Pure Python, so it works on Windows without installing GNU gettext.
Run it after editing a translation in django.po:   py compile_translations.py
Then commit both the .po and the .mo files.
"""
import ast
import struct
from pathlib import Path

BASE = Path(__file__).resolve().parent


def read_po(path):
    entries, msgid, msgstr, section = {}, None, None, None

    def flush():
        if msgid is not None and msgstr:
            entries[msgid] = msgstr
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('msgid '):
            flush()
            msgid, msgstr, section = ast.literal_eval(line[6:]), '', 'id'
        elif line.startswith('msgstr '):
            msgstr, section = ast.literal_eval(line[7:]), 'str'
        elif line.startswith('"'):
            if section == 'id':
                msgid += ast.literal_eval(line)
            else:
                msgstr += ast.literal_eval(line)
    flush()
    return entries


def write_mo(entries, path):
    keys = sorted(entries)
    ids = b''.join(k.encode('utf-8') + b'\0' for k in keys)
    strs = b''.join(entries[k].encode('utf-8') + b'\0' for k in keys)
    n = len(keys)
    key_start = 7 * 4 + 16 * n
    val_start = key_start + len(ids)
    koffsets, voffsets, ko, vo = [], [], 0, 0
    for k in keys:
        kb, vb = k.encode('utf-8'), entries[k].encode('utf-8')
        koffsets += [len(kb), key_start + ko]
        voffsets += [len(vb), val_start + vo]
        ko += len(kb) + 1
        vo += len(vb) + 1
    header = struct.pack('Iiiiiii', 0x950412de, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    path.write_bytes(header + struct.pack(f'{2 * n}i', *koffsets) + struct.pack(f'{2 * n}i', *voffsets) + ids + strs)


if __name__ == '__main__':
    for po in BASE.glob('locale/*/LC_MESSAGES/*.po'):
        entries = read_po(po)
        write_mo(entries, po.with_suffix('.mo'))
        print(f'{po.relative_to(BASE)}: {len(entries) - ("" in entries)} translations compiled')
