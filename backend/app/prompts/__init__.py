from pathlib import Path
from typing import Dict


def load_prompts() -> Dict[str, Dict[str, Dict[str, str]]]:
    """Load all prompt templates from files with nested subfolder structure."""
    prompts = {"system": {}, "user": {}}

    prompts_dir = Path(__file__).parent

    def load_prompts_from_directory(base_dir: Path) -> Dict[str, Dict[str, str]]:
        """Recursively load prompts from a given base directory."""
        prompts_dict = {}
        for file_or_folder in base_dir.iterdir():
            if file_or_folder.is_dir():
                # Recursively load subfolders
                prompts_dict[file_or_folder.name] = load_prompts_from_directory(
                    file_or_folder
                )

            elif file_or_folder.is_file() and file_or_folder.suffix == ".txt":
                # Load text files
                prompt_name = file_or_folder.stem
                if prompt_name in prompts_dict:
                    raise ValueError(
                        f"Duplicate prompt name: {prompt_name} in {file_or_folder.parent}"  # noqa: E501
                    )
                prompts_dict[prompt_name] = file_or_folder.read_text().strip()

        return prompts_dict

    # Load system prompts.
    system_dir = prompts_dir / "system"
    if system_dir.exists():
        prompts["system"] = load_prompts_from_directory(system_dir)

    # Load user prompts.
    user_dir = prompts_dir / "user"
    if user_dir.exists():
        prompts["user"] = load_prompts_from_directory(user_dir)

    return prompts


PROMPTS = load_prompts()
