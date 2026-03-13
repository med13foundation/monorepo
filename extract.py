"""
Extract selected project files into a Markdown document with a generated TOC.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_EXCLUDE_FOLDERS = {
    "venv",
    ".venv",
    ".streamlit",
    "__pycache__",
    "site-packages",
    "bin",
    ".git",
    "logs",
}
GIT_SPECIFIC_FILES = {".gitignore", ".gitattributes", ".gitmodules"}
ALLOWED_FILE_ENDINGS = (
    ".py",
    ".toml",
    ".md",
    ".txt",
    ".sh",
    ".dockerfile",
    ".yml",
    ".yaml",
    ".sql",
    ".css",
    ".png",
    ".log",
    ".csv",
    ".r",
    ".qmd",
    ".rprofile",
    ".gitignore",
    ".placeholder",
)
DOCKER_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "entrypoint.sh",
    ".env.docker",
}
CODE_LANG_BY_ENDING = {
    ".py": "python",
    ".toml": "toml",
    ".md": "markdown",
    ".txt": "text",
    ".sh": "bash",
    ".dockerfile": "dockerfile",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
    ".css": "css",
    ".log": "text",
    ".csv": "csv",
    ".r": "r",
    ".qmd": "markdown",
    ".rprofile": "r",
    ".gitignore": "text",
    ".placeholder": "text",
    ".png": "",
    ".env.docker": "properties",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract code and structure into markdown.",
    )
    parser.add_argument(
        "--target-folder",
        "-f",
        type=Path,
        nargs="+",
        default=[Path.cwd()],
        help=(
            "Target folder(s) to extract from. Default is the current directory. "
            "You may specify multiple folders."
        ),
    )
    parser.add_argument(
        "--output-file",
        "-o",
        type=Path,
        default=Path("files_content.md"),
        help="Output markdown file name. Default is 'files_content.md'.",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        action="append",
        default=[],
        help="Additional folder names to exclude. Can be specified multiple times.",
    )
    return parser


def _should_exclude_path(
    path_parts: tuple[str, ...],
    exclude_folders: set[str],
) -> bool:
    return any(part in exclude_folders for part in path_parts)


def _target_folder_name(target_folder: Path) -> str:
    return (
        target_folder.name or target_folder.resolve().name or target_folder.as_posix()
    )


def _normalize_relative_folder(relative_folder: Path) -> str:
    return "." if relative_folder == Path() else relative_folder.as_posix()


def _is_allowed_file(file_path: Path) -> bool:
    lower_name = file_path.name.lower()
    return file_path.name in DOCKER_FILES or lower_name.endswith(ALLOWED_FILE_ENDINGS)


def _should_skip_file(
    file_path: Path,
    script_path: Path,
    output_path: Path,
) -> bool:
    if file_path.resolve() in {script_path, output_path}:
        return True
    return file_path.name in GIT_SPECIFIC_FILES or file_path.name == "output.md"


def _build_tree_structure(
    base_folder: Path,
    exclude_folders: set[str],
    script_path: Path,
    output_path: Path,
) -> dict[str, list[str]]:
    tree: defaultdict[str, list[str]] = defaultdict(list)
    for root, dirs, files in os.walk(base_folder):
        root_path = Path(root)
        if _should_exclude_path(root_path.parts, exclude_folders):
            dirs[:] = []
            continue
        dirs[:] = [directory for directory in dirs if directory not in exclude_folders]

        relative_root = _normalize_relative_folder(root_path.relative_to(base_folder))
        for file_name in sorted(files):
            file_path = root_path / file_name
            if _should_skip_file(file_path, script_path, output_path):
                continue
            if _is_allowed_file(file_path):
                tree[relative_root].append(file_name)
    return dict(tree)


def _anchor_for_path(path: Path) -> str:
    return path.as_posix().replace("/", "-").replace(".", "").lower()


def _generate_toc(tree: dict[str, list[str]]) -> str:
    lines = ["# Project File Contents\n"]
    for folder in sorted(tree):
        folder_path = Path(folder)
        indent_level = 0 if folder == "." else len(folder_path.parts) - 1
        folder_name = "." if folder == "." else folder_path.name
        lines.append(f"{'  ' * indent_level}- **{folder_name}**")
        for filename in tree[folder]:
            relative_path = folder_path / filename if folder != "." else Path(filename)
            lines.append(
                f"{'  ' * (indent_level + 1)}- [`{filename}`](#{_anchor_for_path(relative_path)})",
            )
    lines.append("\n---\n")
    return "\n".join(lines)


def _detect_code_lang(file_path: Path) -> str:
    name = file_path.name
    if name in {
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "entrypoint.sh",
        ".env.docker",
    }:
        return {
            "Dockerfile": "dockerfile",
            "docker-compose.yml": "yaml",
            "docker-compose.yaml": "yaml",
            "entrypoint.sh": "bash",
            ".env.docker": "properties",
        }[name]

    lower_name = name.lower()
    for ending, language in CODE_LANG_BY_ENDING.items():
        if lower_name.endswith(ending):
            return language
    return ""


def _read_file_content(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def _render_file(
    file_path: Path,
    relative_file_path: Path,
) -> list[str]:
    code_lang = _detect_code_lang(file_path)
    lines = [
        f'### File: `{relative_file_path.as_posix()}`\n<a name="{_anchor_for_path(relative_file_path)}"></a>',
        f"```{code_lang}",
    ]
    try:
        if not code_lang:
            lines.append("[Binary or image file omitted]")
        else:
            lines.append(_read_file_content(file_path))
    except (OSError, UnicodeDecodeError) as exc:
        lines.append(f"Error reading file: {exc}")
    lines.extend(["```", ""])
    return lines


def _render_target_folder(
    target_folder: Path,
    exclude_folders: set[str],
    script_path: Path,
    output_path: Path,
) -> list[str]:
    folder_name = _target_folder_name(target_folder)
    markdown_lines = [f"# Target Folder: {folder_name}\n"]

    for root, dirs, files in os.walk(target_folder):
        root_path = Path(root)
        if _should_exclude_path(root_path.parts, exclude_folders):
            dirs[:] = []
            continue

        found_venv = any(directory in {".venv", "venv"} for directory in dirs)
        dirs[:] = [directory for directory in dirs if directory not in exclude_folders]

        relative_root = root_path.relative_to(target_folder)
        folder_path = (
            folder_name
            if relative_root == Path()
            else (Path(folder_name) / relative_root).as_posix()
        )
        markdown_lines.append(f"## Folder: {folder_path}\n")

        if found_venv:
            markdown_lines.append(
                "> Note: Contains a virtual environment folder. Contents are excluded.\n",
            )

        for file_name in sorted(files):
            file_path = root_path / file_name
            if _should_skip_file(file_path, script_path, output_path):
                continue
            if not _is_allowed_file(file_path):
                continue
            relative_file_path = Path(folder_name) / file_path.relative_to(
                target_folder,
            )
            markdown_lines.extend(_render_file(file_path, relative_file_path))

    return markdown_lines


def _build_combined_tree(
    target_folders: list[Path],
    exclude_folders: set[str],
    script_path: Path,
    output_path: Path,
) -> dict[str, list[str]]:
    combined_tree: defaultdict[str, list[str]] = defaultdict(list)
    for target_folder in target_folders:
        folder_name = _target_folder_name(target_folder)
        for folder, files in _build_tree_structure(
            target_folder,
            exclude_folders,
            script_path,
            output_path,
        ).items():
            folder_path = (
                folder_name
                if folder == "."
                else (Path(folder_name) / folder).as_posix()
            )
            combined_tree[folder_path].extend(files)
    return dict(combined_tree)


def _resolve_target_folders(target_folders: list[Path]) -> list[Path]:
    return [folder.expanduser().resolve() for folder in target_folders]


def _write_output(output_path: Path, markdown_lines: list[str]) -> None:
    output_path.write_text("\n".join(markdown_lines), encoding="utf-8")


def _emit_summary(output_path: Path, target_folders: list[Path]) -> None:
    sys.stdout.write(f"Markdown file generated: {output_path}\n")
    if len(target_folders) > 1:
        folder_names = ", ".join(folder.name for folder in target_folders)
        sys.stdout.write(
            f"Included {len(target_folders)} folders: {folder_names}\n",
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    target_folders = _resolve_target_folders(args.target_folder)
    output_path = args.output_file.expanduser().resolve()
    exclude_folders = DEFAULT_EXCLUDE_FOLDERS.union(set(args.exclude))
    script_path = Path(__file__).resolve()

    combined_tree = _build_combined_tree(
        target_folders,
        exclude_folders,
        script_path,
        output_path,
    )
    markdown_lines = [_generate_toc(combined_tree)]
    for target_folder in target_folders:
        markdown_lines.extend(
            _render_target_folder(
                target_folder,
                exclude_folders,
                script_path,
                output_path,
            ),
        )

    _write_output(output_path, markdown_lines)
    _emit_summary(output_path, target_folders)


if __name__ == "__main__":
    main()
