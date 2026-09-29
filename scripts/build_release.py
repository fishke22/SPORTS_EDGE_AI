from __future__ import annotations

import json

from sports_edge_ai.common.release_bundle import build_release_bundle


def main() -> None:
    bundle = build_release_bundle()
    print(
        json.dumps(
            {
                "relative_path": bundle.relative_path,
                "sha256": bundle.sha256,
                "manifest_sha256": bundle.manifest_sha256,
                "file_count": bundle.file_count,
                "version": bundle.version,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
