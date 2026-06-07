from __future__ import annotations

from pathlib import Path
import argparse
import re


def read_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def parse_slec_text(data: bytes) -> tuple[str, str, str, list[str]]:
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()

    header_line = lines[0] if len(lines) > 0 else ""
    id_line = lines[1] if len(lines) > 1 else ""
    size_line = lines[2] if len(lines) > 2 else ""

    xml_blocks = re.findall(r"(<llsd>.*?</llsd>)", text, flags=re.DOTALL | re.IGNORECASE)
    return header_line, id_line, size_line, xml_blocks


def parse_slec_file(input_path: str | Path, output_dir: str | Path) -> None:
    raw = read_bytes(input_path)
    header_line, id_line, size_line, xml_blocks = parse_slec_text(raw)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "summary.txt"
    summary_lines = [
        f"Input file: {input_path}",
        f"Bytes: {len(raw)}",
        f"Header: {header_line}",
        f"Record ID: {id_line}",
        f"Size line: {size_line}",
        f"LLSD blocks: {len(xml_blocks)}",
    ]
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    combined_path = out_dir / "all_blocks.xml"
    combined_text = "\n\n".join(xml_blocks) if xml_blocks else ""
    combined_path.write_text(combined_text, encoding="utf-8")

    for idx, block in enumerate(xml_blocks, start=1):
        block_path = out_dir / f"block_{idx:03d}.xml"
        block_path.write_text(block, encoding="utf-8")

    print(f"Input file: {input_path}")
    print(f"Bytes: {len(raw)}")
    print(f"Header: {header_line}")
    print(f"Record ID: {id_line}")
    print(f"Size line: {size_line}")
    print(f"LLSD blocks found: {len(xml_blocks)}")
    print(f"Wrote output to: {out_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract LLSD/XML blocks from a Firestorm .slec file."
    )
    parser.add_argument("input_file", help="Path to input .slec file")
    parser.add_argument("output_dir", help="Directory for extracted output")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    parse_slec_file(args.input_file, args.output_dir)


if __name__ == "__main__":
    main()