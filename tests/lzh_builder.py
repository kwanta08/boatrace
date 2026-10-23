"""テスト用の無圧縮（-lh0-）LZH を作る。レベル 2 ヘッダ＋CRC16（CRC-16/ARC）。

レベル 2 ヘッダの並び：
  0  ヘッダ全体のサイズ (2)   ここから拡張ヘッダの終端までの総バイト数
  2  圧縮方式 "-lh0-" (5)
  7  圧縮後サイズ (4)  11 元サイズ (4)  15 更新日時 Unix 秒 (4)
  19 予約 0x20 (1)  20 レベル 2 (1)  21 ファイルの CRC16 (2)  23 OS ID (1)
  24 最初の拡張ヘッダのサイズ (2)
拡張ヘッダ：種別 (1) ＋データ ＋ 次の拡張ヘッダのサイズ (2)。最後の「次」は 0。
  0x00 共通ヘッダ（データはヘッダ全体の CRC16、計算時は 0 を入れる）、0x01 ファイル名。
末尾に 0x00 を 1 バイト置く。
"""

from __future__ import annotations

import struct


def crc16(data: bytes, crc: int = 0) -> int:
    """CRC-16/ARC（LZH が使う、多項式 0xA001 の反転版、初期値 0）。"""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _entry(name: str, data: bytes, mtime: int) -> bytes:
    name_b = name.encode("ascii")
    ext_common_len = 1 + 2 + 2  # 種別 + CRC + 次のサイズ
    ext_name_len = 1 + len(name_b) + 2  # 種別 + 名前 + 次のサイズ
    header_size = 26 + ext_common_len + ext_name_len

    def build(header_crc: int) -> bytes:
        return (
            struct.pack("<H", header_size)
            + b"-lh0-"
            + struct.pack("<III", len(data), len(data), mtime)
            + b"\x20\x02"
            + struct.pack("<H", crc16(data))
            + b"U"
            + struct.pack("<H", ext_common_len)
            + b"\x00"
            + struct.pack("<H", header_crc)
            + struct.pack("<H", ext_name_len)
            + b"\x01"
            + name_b
            + struct.pack("<H", 0)
        )

    header = build(0)
    assert len(header) == header_size
    return build(crc16(header)) + data


def build_lzh(files: dict[str, bytes], mtime: int = 1_700_000_000) -> bytes:
    """名前（ASCII）→ 内容 の辞書から、無圧縮 LZH のバイト列を作る。"""
    return b"".join(_entry(n, d, mtime) for n, d in files.items()) + b"\x00"
