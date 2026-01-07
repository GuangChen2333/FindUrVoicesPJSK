import argparse
import os
from pathlib import Path


def rewrite_manifest(manifest_path: Path, target_dir: Path, character_id: str) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    lines = manifest_path.read_text(encoding="utf-8").splitlines()

    new_lines = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue

        original_path, content = parts
        filename = os.path.basename(original_path)
        new_path = target_dir / filename
        new_lines.append(f"{new_path}|{character_id}|ja|{content}")

    manifest_path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rewrite manifest.list to new format: folder/filename|id|ja|content"
    )
    parser.add_argument("manifest", type=Path, help="Path to manifest.list")
    parser.add_argument("folder", type=Path, help="Target folder for rewritten paths")
    parser.add_argument("character_id", type=str, help="ID to insert into manifest entries")
    args = parser.parse_args()

    rewrite_manifest(args.manifest, args.folder, args.character_id)


if __name__ == "__main__":
    main()
