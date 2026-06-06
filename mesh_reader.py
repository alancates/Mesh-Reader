from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from struct import unpack_from
from typing import Iterable
import zlib


@dataclass
class MeshHeader:
    magic: bytes = b""
    version: int | None = None
    flags: int | None = None
    raw_size: int = 0


@dataclass
class MeshData:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    uvs: list[tuple[float, float]] = field(default_factory=list)


class BinaryReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def read(self, size: int) -> bytes:
        chunk = self.data[self.offset:self.offset + size]
        if len(chunk) != size:
            raise EOFError("Unexpected end of file")
        self.offset += size
        return chunk

    def read_u8(self) -> int:
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_u16(self) -> int:
        value = unpack_from("<H", self.data, self.offset)[0]
        self.offset += 2
        return value

    def read_u32(self) -> int:
        value = unpack_from("<I", self.data, self.offset)[0]
        self.offset += 4
        return value

    def read_f32(self) -> float:
        value = unpack_from("<f", self.data, self.offset)[0]
        self.offset += 4
        return value


def read_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def maybe_decompress(data: bytes) -> bytes:
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            return zlib.decompress(data, wbits=wbits)
        except zlib.error:
            pass
    return data


def parse_header(data: bytes) -> MeshHeader:
    header = MeshHeader(raw_size=len(data))
    if len(data) >= 4:
        header.magic = data[:4]
    return header


def parse_mesh(data: bytes) -> MeshData:
    data = maybe_decompress(data)
    header = parse_header(data)
    _ = header

    mesh = MeshData()
    return mesh


def write_obj(mesh: MeshData, output_path: str | Path) -> None:
    lines: list[str] = []

    for x, y, z in mesh.vertices:
        lines.append(f"v {x} {y} {z}")

    for u, v in mesh.uvs:
        lines.append(f"vt {u} {v}")

    for a, b, c in mesh.faces:
        if mesh.uvs:
            lines.append(f"f {a}/{a} {b}/{b} {c}/{c}")
        else:
            lines.append(f"f {a} {b} {c}")

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_file(input_path: str | Path, output_path: str | Path) -> None:
    raw = read_bytes(input_path)
    mesh = parse_mesh(raw)
    write_obj(mesh, output_path)


if __name__ == "__main__":
    print("Mesh-Reader foundation ready.")