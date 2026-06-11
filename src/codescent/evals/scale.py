from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from codescent.evals.deterministic import ExpectedManifest

if TYPE_CHECKING:
    from pathlib import Path


def generate_scale_fixture(
    *,
    source_repo: Path,
    source_manifest: Path,
    output_root: Path,
    module_count: int,
) -> tuple[Path, Path]:
    repo = output_root / "python-scale"
    manifest_path = output_root / "python-scale.expected.json"
    shutil.rmtree(repo, ignore_errors=True)
    _ = shutil.copytree(source_repo, repo, ignore=shutil.ignore_patterns(".codescent"))

    generated_files = _write_generated_modules(repo, module_count)
    manifest = ExpectedManifest.model_validate_json(source_manifest.read_text())
    scaled = manifest.model_copy(
        update={
            "fixture_root": repo.as_posix(),
            "files": (*manifest.files, *generated_files),
        }
    )
    _ = manifest_path.write_text(scaled.model_dump_json(indent=2))
    return repo, manifest_path


def _write_generated_modules(repo: Path, module_count: int) -> tuple[str, ...]:
    package = repo / "src" / "scale_generated"
    _ = package.mkdir(parents=True, exist_ok=True)
    _ = (package / "__init__.py").write_text("PACKAGE_NAME = 'scale_generated'\n")
    files = ["src/scale_generated/__init__.py"]
    for index in range(module_count):
        relative = f"src/scale_generated/module_{index:03}.py"
        _ = (repo / relative).write_text(
            "\n".join(
                [
                    f'GENERATED_VALUE_{index:03} = "scale-value-{index:03}"',
                    "",
                ]
            )
        )
        files.append(relative)
    return tuple(files)
