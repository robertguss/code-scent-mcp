from __future__ import annotations

import tomllib
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]


class LicenseMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    text: str


class ProjectMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    requires_python: str = Field(alias="requires-python")
    license: LicenseMetadata
    scripts: dict[str, str]


class PyprojectMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    project: ProjectMetadata


def _load_pyproject() -> PyprojectMetadata:
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        return PyprojectMetadata.model_validate(tomllib.load(pyproject_file))


def test_codescent_cli_registered() -> None:
    pyproject = _load_pyproject()

    assert pyproject.project.scripts["codescent"] == "codescent.cli.main:app"


def test_python_version_and_license_metadata() -> None:
    pyproject = _load_pyproject()

    assert pyproject.project.name == "codescent"
    assert pyproject.project.requires_python == ">=3.12"
    assert pyproject.project.license.text == "MIT"
