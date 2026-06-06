from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


@dataclass
class MeshHeader:
    raw_size: int = 0
    version: int | None = None
    flags: int | None = None


@dataclass
class MeshData:
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[Tuple[int, int, int]] = field(default_factory=list)
    uvs: List[Tuple[float, float]] = field(default_factory=list)


def read_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def parse_header(data: bytes) -> MeshHeader:
    return MeshHeader(raw_size=len(data))


def parse_mesh(data: bytes) -> MeshData:
    return MeshData()


def write_obj(mesh: MeshData, output_path: str | Path) -> None:
    lines: list[str] = []
    for x, y, z in mesh.vertices:
        lines.append(f"v {x} {y} {z}")
    for u, v in mesh.uvs:
        lines.append(f"vt {u} {v}")
    for a, b, c in mesh.faces:
        lines.append(f"f {a} {b} {c}")
    Path(output_path).write_text("\\n".join(lines) + "\\n", encoding="utf-8")


if __name__ == "__main__":
    print("Mesh-Reader parser scaffold ready.")
