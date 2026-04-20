import argparse
from pathlib import Path


def rewrite_manifest(
    manifest_path: Path,
    target_dir: Path,
    character_id: str,
    in_place: bool = False,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)

    lines = manifest_path.read_text(encoding="utf-8").splitlines()

    new_lines = []
    for line in lines:
        if not line.strip():
            continue

        parts = line.split("|")
        if len(parts) == 2:
            original_path, content = parts
        elif len(parts) >= 4:
            original_path = parts[0]
            content = "|".join(parts[3:])
        else:
            continue

        # Windows 路径用 ntpath 解析，避免在 POSIX 上 basename 失效
        filename = original_path.replace("\\", "/").rsplit("/", 1)[-1]

        new_path = (target_dir / filename).resolve()

        new_lines.append(f"{new_path}|{character_id}|ja|{content}")

    # in-place: 覆写源文件；否则写到 target_dir 下同名文件
    output_manifest = manifest_path if in_place else target_dir / manifest_path.name

    output_manifest.write_text(
        "\n".join(new_lines) + ("\n" if new_lines else ""),
        encoding="utf-8",
    )
    return output_manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rewrite manifest.list to new format: abs_path|id|ja|content"
    )
    parser.add_argument("manifest", type=Path, help="Path to manifest.list")
    parser.add_argument("folder", type=Path, help="Target folder for rewritten paths")
    parser.add_argument("character_id", type=str, help="ID to insert into manifest entries")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the source manifest instead of writing to folder/",
    )
    args = parser.parse_args()

    out = rewrite_manifest(
        args.manifest.resolve(),
        args.folder.resolve(),
        args.character_id,
        in_place=args.in_place,
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
