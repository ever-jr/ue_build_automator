from enum import Enum
from pathlib import Path
import random
import shlex
import time
import subprocess
from typing import Any
import winsound
import pyttsx3
import tomllib
import os

#==============================================================================
# Config

PROGRAM_NAME = "Build Automator"
CONFIG_FILENAME = "config.toml"
DEFAULT_BUILD_NAME = "Windows"
BIN_DIR = "./bin"
VERBOSE_SOUND_DEBUG = False

def load_config(path: str | Path) -> dict[str, Any] | None:
    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
        return config

    except:
        return None


def get_config_or_default(default, config: dict[str, Any] | None, category: str, property: str):
    if not config:
        return default

    config_category = config.get(category, { property: default })

    if not config_category or not isinstance(config_category, dict):
        config_category = { property: default }
        config[category] = config_category

    config_property = config_category.get(property, default)

    if not config_property:
        config_property = default
        config[category][property] = config_property

    return config_property


def get_default_build_platform() -> str:
    return "Win64"


#==============================================================================
# Paths

def get_path(possible_path: str) -> Path:
    return Path(possible_path).resolve()


def get_path_or_paths(possible_path: str | list[str]) -> Path | list[Path]:
    if isinstance(possible_path, list):
        out_paths: list[Path] = []
        for path in possible_path:
            out_paths.append(get_path(path))

        return out_paths

    return get_path(possible_path)


def try_find_uproject_path(project_path: Path) -> Path | None:
    if not project_path.exists():
        print(f"Project path '{project_path}' doens't exist!")
        return None

    if not project_path.is_dir():
        print(f"Project path '{project_path}' is not a directory!")
        return None

    for root, _, files in project_path.walk():
        print(f"Searching project path... root: {root} | files: {files}")
        for file in files:
            file = Path(file)
            if file.suffix == ".uproject":
                path = (root / file).resolve()
                return path

    return None


def get_default_uat_path() -> str:
    return "C:/Program Files/Epic Games/UE_5.3/Engine/Build/BatchFiles/RunUAT.bat"


def get_default_svn_path() -> str:
    return "C:/Program Files/TortoiseSVN/bin/svn.exe"
    

#==============================================================================
# Helpers

def make_line():
    return "".join('-' for _ in range(80))

#==============================================================================
# PROCESSES

def sh(cmd: list[str]):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


#==============================================================================
# SVN TORTOISE

def svn_revision(svn_exe_path: Path, path: Path) -> int:
    """Returns the revision number."""

    out = sh([str(svn_exe_path), "info", "--show-item", "revision", str(path)])
    if out.returncode != 0:
        print(out.stdout)
        raise RuntimeError("svn info failed")

    return int(out.stdout.strip())


def svn_update(svn_exe_path: Path, path: Path) -> bool:
    """Returns True if the working copy changed (moved to a new rev)."""

    cmd = [str(svn_exe_path), "update", str(path)]

    print(f"Updating SVN at: {path}")

    before = svn_revision(svn_exe_path, path)
    out = sh(cmd)

    if out.returncode != 0:
        print(out.stdout)
        raise RuntimeError("svn update failed")

    after = svn_revision(svn_exe_path, path)
    if after > before:
        print(f"✅ SVN updated: {before} -> {after}")
        return True

    print(f"No remote changes. At revision {after}\n...\n")
    return False


#==============================================================================
# Unreal Engine Building

def kill_unreal_if_running():
    for exe in ("UnrealEditor.exe", "UnrealEditor-Cmd.exe"):
        _ = subprocess.run(["taskkill", "/IM", exe, "/F", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_unreal_automation_tool(
    uat_path: Path,
    project_path: Path,
    platform: str = "Win64",
    config: str = "Shipping",
    archive_dir: Path | None = None,
    extra_args: str | None = None
) -> int:
    """Call Unreal AutomationTool (BuildCookRun)"""

    # building for windows
    cmd = [
        str(uat_path),
        "BuildCookRun",
        f"-project={project_path}",
        "-noP4",
        f"-clientconfig={config}",
        f"-targetplatform={platform}",
        "-build", "-cook", "-stage", "-pak", "-package",
        "-utf8output"
    ]

    if archive_dir:
        cmd += ["-archive", f"-archivedirectory={archive_dir}"]

    if extra_args:
        cmd += (extra_args if isinstance(extra_args, list) else shlex.split(extra_args))

    print(
        make_line(),
        "\n🚀 Building:", " ".join(shlex.quote(c) for c in cmd)
    )

    use_shell = str(uat_path).lower().endswith((".bat", ".cmd"))

    with subprocess.Popen(
        cmd,
        shell=use_shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        encoding="utf-8",
        env=os.environ.copy()
    ) as proc:
        output = proc.stdout
        if output:
            for line in output:
                print(line, end="", flush=True)

        return proc.wait()


class UnrealBuildResponse(Enum):
    SUCCESS = 0
    FAILED = 1
    UNEXPECTED_ERROR = 2

def build_unreal_project(
    uat_exe_path: Path,
    uproject_path: Path,
    platform: str,
    config: str,
    output_dir: Path,
) -> UnrealBuildResponse:
    try:
        result_code = run_unreal_automation_tool(
            uat_exe_path,
            uproject_path,
            platform,
            config,
            output_dir
        )

        if result_code != 0:
            print(
                make_line(),
                "\n❌ Build failed!")
            print("Exit code:", result_code)
            return UnrealBuildResponse.FAILED

    except subprocess.CalledProcessError as e:
        print(
            make_line(),
            "\n❌ Process failed!")
        print("Exit code:", e.returncode)
        print("output:\n", e.output if hasattr(e, "output") else "(no output)")
        return UnrealBuildResponse.UNEXPECTED_ERROR

    except Exception as e:
        print(
            make_line(),
            "\n⚠️ Unexpected error during build:", e)
        return UnrealBuildResponse.UNEXPECTED_ERROR

    return UnrealBuildResponse.SUCCESS


#==============================================================================
# SOUNDS

def play_beep_sound():
    frequency_in_hz = 1000
    duration_in_ms = 400
    winsound.Beep(frequency_in_hz, duration_in_ms)


def play_sound_file(path: Path):
    if path.exists():
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)


def say(text: str):
    engine = pyttsx3.init()
    _ = engine.say(text)
    _ = engine.runAndWait()


def find_sounds_on_path(path: Path) -> list[Path]:
    if not path.exists():
        return []

    found_sounds: list[Path] = []

    if path.is_dir():
        for root, _, files in path.walk():
            for file in files:
                file = Path(file)
                if file.suffix == ".wav":
                    found_sounds.append(root / file)

    return found_sounds


def play_random_sound(sounds: list[Path] | Path):
    if VERBOSE_SOUND_DEBUG:
        print(f"Selecting sound from {sounds}...")

    if isinstance(sounds, list):
        if len(sounds) < 1:
            print("No sound found on", sounds)
            return
        possible_sound_paths: Path = random.choice(sounds)
    else:
        possible_sound_paths = sounds

    if not possible_sound_paths.exists():
        print(f"Sound path {possible_sound_paths} do not exists.")
        return

    if possible_sound_paths.is_dir():
        found_sounds: list[Path] = find_sounds_on_path(possible_sound_paths)
        if len(found_sounds) < 1:
            print("No sound found on", possible_sound_paths)
            return

        selected_sound = random.choice(found_sounds)
        play_sound_file(selected_sound)
        return

    play_sound_file(possible_sound_paths)


#==============================================================================
# Directory Structuring

def find_file(dir: Path, filename: str) -> Path | None:
    file_path = Path(os.path.join(dir, filename)).resolve()
    if not file_path.exists():
        return None
    return file_path


def get_final_build_name(filename: str, commit: int) -> str:
    return f"[{commit}] {filename}"


def compact_file(file_path: Path, should_override: bool, new_name: str | None = None, output_path: Path | None = None) -> Path | None:
    """Returns the compacted file."""

    if not file_path.exists():
        print(f"{file_path.name} does not exists!")
        return None

    if not file_path.is_dir():
        print(f"{file_path.name} is not a directory!")
        return None

    zip_name = f"{file_path.name}.zip"
    out_path = file_path.parent

    if new_name:
        zip_name = f"{new_name}.zip"

    if output_path:
        out_path = output_path

    zip_path = out_path / zip_name

    print(make_line())

    if zip_path.exists():
        if not should_override:
            return zip_path
        else:
            zip_path.unlink()
            print(f"Overriding existing zip: {zip_path}")

    print(f"Compacting {file_path} -> {zip_path}...")
    cmd = ["7z", "a", str(zip_path), str(file_path)]
    _ = sh(cmd)

    return zip_path


def find_and_process_last_build(new_build_name: str, output_path: Path, should_override: bool):
    last_build_path = Path(BIN_DIR).resolve() / DEFAULT_BUILD_NAME
    _ = compact_file(last_build_path, should_override, new_build_name, output_path)


#==============================================================================
# Main

def loop_pool_and_build():
    config = load_config(CONFIG_FILENAME)
    print("Loading configs...")

    # development
    should_print_configs: bool = get_config_or_default(True, config, "development", "print_config")

    # project configs
    project_path: Path = get_path(get_config_or_default("", config, "project", "project_path"))

    if not project_path.exists():
        print("Invalid project path:", project_path)
        return

    if not project_path.is_dir():
        print(f"Project path '{project_path}' is not a directory!")
        return

    project_filename:       str = project_path.name
    project_uproject_path:  Path | None = try_find_uproject_path(project_path)

    if not project_uproject_path or not project_uproject_path.exists():
        print("Invalid UProject path:", project_uproject_path)
        return

    # unreal configs
    uat_exe_path:       Path = get_path(get_config_or_default(get_default_uat_path(), config, "unreal", "uat_exe_path"))
    uat_platform:       str = get_config_or_default(get_default_build_platform(), config, "unreal", "platform")
    uat_build_type:     str = get_config_or_default("Shipping", config, "unreal", "build_type")
    uat_output_temp =   Path(BIN_DIR).resolve()

    if not uat_exe_path.exists():
        print("Invalid Unreal Build Tool executable path:", uat_exe_path)
        return

    output_build_directory: Path = get_path(get_config_or_default("./builds", config, "unreal", "output_file"))

    # svn configs
    svn_exe_path:                   Path = get_path(get_config_or_default(get_default_svn_path(), config, "svn", "exe_path"))
    svn_update_interval_in_seconds: int = get_config_or_default(30, config, "svn", "update_interval_in_seconds")

    if not svn_exe_path.exists():
        print("Invalid SVN executable path:", svn_exe_path)
        return

    if svn_update_interval_in_seconds <= 0:
        old_interval: int = svn_update_interval_in_seconds
        svn_update_interval_in_seconds = 1
        print(f"Fixing SVN update interval '{old_interval}s' -> '{svn_update_interval_in_seconds}s'")

    # sounds
    sounds_build_starting:      list[Path] | Path = get_path_or_paths(get_config_or_default(".", config, "sounds", "build_starting"))
    sounds_build_success:       list[Path] | Path = get_path_or_paths(get_config_or_default(".", config, "sounds", "build_success"))
    sounds_build_fail:          list[Path] | Path = get_path_or_paths(get_config_or_default(".", config, "sounds", "build_fail"))
    sounds_build_unknown_error: list[Path] | Path = get_path_or_paths(get_config_or_default(".", config, "sounds", "build_unknown_error"))

    # build
    should_override_build_zip: bool = get_config_or_default(False, config, "build", "override_zip")

    if should_print_configs and config:
        print("showing configs...\n")
        for config_category in config:
            print(f"[{config_category}]")
            for config_name in config[config_category]:
                print(f"{config_name} = {config[config_category][config_name]}")
            print()

    last_built_rev: int = -1

    while True:
        try:
            def wait():
                time.sleep(svn_update_interval_in_seconds)

            changed = svn_update(svn_exe_path, project_path)

            current_rev = svn_revision(svn_exe_path, project_path)
            should_build = changed and (current_rev != last_built_rev)

            if should_build:
                play_random_sound(sounds_build_starting)
                say("Começando a buildar!")

                print("Change detected -> starting build")

                kill_unreal_if_running()
                build_result = build_unreal_project(
                    uat_exe_path,
                    project_uproject_path,
                    uat_platform,
                    uat_build_type,
                    uat_output_temp,
                )

                if build_result == UnrealBuildResponse.UNEXPECTED_ERROR:
                    play_random_sound(sounds_build_unknown_error)
                    say("Erro inesperado durante build!")
                    wait()
                    continue

                elif build_result == UnrealBuildResponse.FAILED:
                    play_random_sound(sounds_build_fail)
                    say("Build falha, melhore!")
                    wait()
                    continue

                last_built_rev = current_rev

                new_build_name = f"[{last_built_rev}] {project_filename}"
                find_and_process_last_build(new_build_name, output_build_directory, should_override_build_zip)
                play_random_sound(sounds_build_success)

                print(make_line(), f"\n🍆 Build completed for r{last_built_rev}!")

                wait()

        except KeyboardInterrupt:
            print(f"{PROGRAM_NAME} Finished!")
            return

        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    loop_pool_and_build()
