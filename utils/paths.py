from pathlib import Path

def get_project(project_folder_name=""):
    current = Path(__file__).resolve().parent

    while current.name != project_folder_name:
        if current.parent == current:  # reached root
            raise FileNotFoundError(f"Project folder '{project_folder_name}' not found.")
        current = current.parent

    return current