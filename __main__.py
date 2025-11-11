from enum import Enum
from pathlib import Path
import random
import shlex
import time
import subprocess
import winsound
import pyttsx3
import os

from config_type import BuildAutomatorConfig, build_automator_load_config


#==============================================================================
# DEFAULTS

PROGRAM_NAME = "Build Automator"
VERBOSE_SOUND_DEBUG = False

#==============================================================================
# HELPERS

def _make_line():
    return "".join('-' for _ in range(80))

#==============================================================================
# PROCESSES

def _sh(cmd: list[str]):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


#==============================================================================
# SVN COMMANDS

def _sh_svn(config: BuildAutomatorConfig, options: list[str]):
    svn_exe: Path = config.svn.exe
    project_path: Path = config.project.path

    cmd: list[str] = [str(svn_exe)]
    cmd.extend(options)
    cmd.append(str(project_path))

    return _sh(cmd)


def svn_cleanup(config: BuildAutomatorConfig) -> bool:
    try:
        out = _sh_svn(
            config,
            options=[
                "cleanup",
                "--remove-unversioned",
                "--remove-ignored",
                "--vacuum-pristines",
                "--include-externals",
            ]
        )
    except Exception as e:
        print("error cleaning while:", e)
        return False

    return out.returncode == 0


def svn_revision(config: BuildAutomatorConfig) -> int:
    """Returns the revision number."""

    out = _sh_svn(config, ["info", "--show-item", "revision"])
    if out.returncode != 0:
        print(out.stdout)
        raise RuntimeError("svn info failed")

    return int(out.stdout.strip())


def svn_log(config: BuildAutomatorConfig, revision_num: int) -> str:
    out = _sh_svn(config, ["log", "--revision", str(revision_num)])
    return out.stdout


def svn_update(config: BuildAutomatorConfig) -> bool:
    """Returns True if the working copy changed (moved to a new rev)."""

    print("Updating SVN at", config.project.path)
    before = svn_revision(config)

    out = _sh_svn(config, ["update"])

    if out.returncode != 0:
        print(out.stdout)
        raise RuntimeError("svn update failed")

    after = svn_revision(config)
    if after > before:
        print(f"✅ SVN updated: {before} -> {after}")
        return True

    print(f"No remote changes. At revision {after}\n...\n")
    return False


#==============================================================================
# UNREAL AUTOMATION TOOL COMMANDS

def unreal_kill_process_if_running():
    for exe in ("UnrealEditor.exe", "UnrealEditor-Cmd.exe"):
        _ = _sh(["taskkill", "/IM", exe, "/F", "/T"])


def unreal_run_automation_tool(
    uat_path: Path,
    project_path: Path,
    platform: str = "Win64",
    build_type: str = "Shipping",
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
        f"-clientconfig={build_type}",
        f"-targetplatform={platform}",
        "-build", "-cook", "-stage", "-pak", "-package",
        "-utf8output"
    ]

    if archive_dir:
        cmd += ["-archive", f"-archivedirectory={archive_dir}"]

    if extra_args:
        cmd += (extra_args if isinstance(extra_args, list) else shlex.split(extra_args))

    print(
        _make_line(),
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

def unreal_build_project(config: BuildAutomatorConfig) -> UnrealBuildResponse:
    try:
        result_code = unreal_run_automation_tool(
            config.uat.exe,
            config.project.uproject,
            config.uat.platform,
            config.uat.build_type,
            config.uat.output
            )

        if result_code != 0:
            print(
                _make_line(),
                "\n❌ Build failed!")
            print("Exit code:", result_code)
            return UnrealBuildResponse.FAILED

    except subprocess.CalledProcessError as e:
        print(
            _make_line(),
            "\n❌ Process failed!")
        print("Exit code:", e.returncode)
        print("output:\n", e.output if hasattr(e, "output") else "(no output)")
        return UnrealBuildResponse.UNEXPECTED_ERROR

    except Exception as e:
        print(
            _make_line(),
            "\n⚠️ Unexpected error during build:", e)
        return UnrealBuildResponse.UNEXPECTED_ERROR

    return UnrealBuildResponse.SUCCESS


#==============================================================================
# SOUNDS

def _sound_find_sounds_on_path(path: Path) -> list[Path]:
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


def _sound_play_file(path: Path):
    if path.exists():
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)


def sound_say(text: str):
    engine = pyttsx3.init()
    _ = engine.say(text)
    _ = engine.runAndWait()


def sound_play_random(sounds: list[Path] | Path):
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
        found_sounds: list[Path] = _sound_find_sounds_on_path(possible_sound_paths)
        if len(found_sounds) < 1:
            print("No sound found on", possible_sound_paths)
            return

        selected_sound = random.choice(found_sounds)
        _sound_play_file(selected_sound)
        return

    _sound_play_file(possible_sound_paths)


#==============================================================================
# LOG HANDLING

def log_find_commands(config: BuildAutomatorConfig, log: str) -> list[str]:
    """Returns the list of commands found on log"""

    found_commands: list[str] = []
    all_commands: list[str] = config.special_log_keywords.all_commands

    for command in all_commands:
        if log.find(command) != -1:
            found_commands.append(command)

    return found_commands


#==============================================================================
# Directory Structuring

def _compact_file(file_path: Path, should_override: bool, new_name: str | None = None, output_path: Path | None = None) -> Path | None:
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

    print(_make_line())

    if zip_path.exists():
        if not should_override:
            return zip_path
        else:
            zip_path.unlink()
            print(f"Overriding existing zip: {zip_path}")

    print(f"Compacting {file_path} -> {zip_path}...")
    cmd = ["7z", "a", str(zip_path), str(file_path)]
    _ = _sh(cmd)

    return zip_path


def build_find(config: BuildAutomatorConfig) -> Path:
    unreal_default_build_name: str = config.uat.default_build_name
    unreal_build_path: Path = config.uat.output
    return unreal_build_path / unreal_default_build_name


def build_dump_log_file(dir: Path, logs: list[str]):
    if not dir.exists():
        print("Can't dump log file, path doesn't exists:", dir)

    if not dir.is_dir():
        print("Can't dump log file, is NOT directory:", dir)

    final_text: str = ""
    for log in logs:
        final_text += f"{log}\n\n"

    log_text_file: Path = dir / "svn_logs.txt"

    _ = log_text_file.write_text(final_text)


def build_compact(config: BuildAutomatorConfig, build: Path, new_build_name: str):
    final_build_path: Path = config.build_export.output
    temp_name: str = f"{new_build_name} TRANSFERING..."

    compacted_file: Path | None = _compact_file(build, config.build_export.override_zip, temp_name, final_build_path)

    if compacted_file and compacted_file.exists():
        new_name_path = compacted_file.parent / f"{new_build_name}{compacted_file.suffix}"
        renamed_file = compacted_file.rename(new_name_path)

        print(f"Compacted file renamed from {str(compacted_file)} to {str(renamed_file)}")


#==============================================================================
# Main

def build_dump_logs_and_compact(config: BuildAutomatorConfig, logs: list[str], revision_num: int) -> bool:
    print("Change detected... Starting build!")
    sound_play_random(config.sounds.build_starting)
    sound_say("Começando a buildar!")

    unreal_kill_process_if_running()
    build_result = unreal_build_project(config)

    if build_result == UnrealBuildResponse.UNEXPECTED_ERROR:
        sound_play_random(config.sounds.build_unknown_error)
        sound_say("Erro inesperado durante build!")
        return False

    elif build_result == UnrealBuildResponse.FAILED:
        sound_play_random(config.sounds.build_fail)
        sound_say("Build falha, melhore!")
        return False

    last_build: Path = build_find(config)

    if len(logs) > 0:
        build_dump_log_file(last_build, logs)

    new_build_name = f"[{revision_num}] {config.project.filename} ({config.uat.build_type})"
    build_compact(config, last_build, new_build_name)
    return True


def _run():
    config = BuildAutomatorConfig() # start empty

    last_built_revision: int = -1
    last_cleanup_time: float = -1.0

    while True:
        try:
            current_time = time.time()

            def wait(config: BuildAutomatorConfig):
                time.sleep(config.svn.update_interval_in_seconds)

            new_config: BuildAutomatorConfig | None = build_automator_load_config()
            if not new_config or not new_config.is_valid():
                if not config.is_valid():
                    wait_time_in_seconds: int = 10
                    print("Incomplete config data:\n")
                    print(config.get_invalid_configs_string(), "\n")
                    print(f"trying again in {wait_time_in_seconds}s\n...")
                    time.sleep(wait_time_in_seconds)
                    continue

                print("New configuration is invalid, ignoring...")
            else:
                config = new_config

            if config.should_print_configs:
                print("Showing configs...\n\n", config)

            unreal_kill_process_if_running()

            cleanup_time_difference: float = current_time - last_cleanup_time if last_cleanup_time != -1.0 else 0.0
            #print(f"cleanup time in seconds: {config.svn.cleanup_timeout_in_seconds} | cleanup time diff: {cleanup_time_difference}")
            if last_cleanup_time == -1 or cleanup_time_difference >= config.svn.cleanup_timeout_in_seconds:
                print(_make_line(), "\nCLEANUP TIME!\n")
                if svn_cleanup(config):
                    last_cleanup_time = current_time
                else:
                    winsound.MessageBeep()
                    sound_say("Falha ao limpar projeto!")
                    print("Cleanup failed!")
                    wait(config)
                    continue

            has_revision_changed: bool = svn_update(config)
            current_revision: int = svn_revision(config)

            if last_built_revision == -1:
                last_built_revision = current_revision

            if has_revision_changed:
                max_num_relevant_logs: int = config.build_export.max_num_relevant_logs
                num_revisions_betwen_last_and_new: int = max(0, min(max_num_relevant_logs, current_revision - last_built_revision))

                ignore_build: bool = False

                logs: list[str] = []
                if max_num_relevant_logs > 0 and num_revisions_betwen_last_and_new > 0:
                    print(_make_line())

                    print("Num revisions between last and new:", num_revisions_betwen_last_and_new)

                    revision_start: int = current_revision - max(0, num_revisions_betwen_last_and_new - 1)
                    revision_end: int = current_revision
                    print("Revision start:", revision_start)
                    print("Revision end:", revision_end)

                    found_commands: list[str] = []

                    print("\nLOGS:")
                    for revision_num in range(revision_start, revision_end + 1):
                        revision_log: str = svn_log(config, revision_num)
                        commands_on_log: list[str] = log_find_commands(config, revision_log)

                        found_commands.extend(commands_on_log)

                        print("revision", revision_num)
                        print(revision_log)
                        logs.append(revision_log)

                    for command in found_commands:
                        if command == config.special_log_keywords.make_dev_build:
                            config.uat.build_type = "Development"

                        elif command == config.special_log_keywords.ignore_build:
                            print("💀 Ignoring build...")
                            sound_say(f"Ignorando build...")
                            ignore_build = True

                    print("commands:", found_commands)


                if len(logs) > 0:
                    print("dumping current logs on build!")
                    build_dump_log_file(build_find(config), logs)

                if not ignore_build:
                    successful_build: bool = build_dump_logs_and_compact(config, logs, last_built_revision)
                    if not successful_build:
                        last_built_revision = current_revision # do not repeat building
                        wait(config)
                        continue

                # dump steam_appid.txt
                print(_make_line(), f"\n🍆 Build completed for r{current_revision}!")
                sound_play_random(config.sounds.build_success)
                sound_say(f"Build {config.uat.build_type} completada!")

                last_built_revision = current_revision

            wait(config)

        except KeyboardInterrupt:
            print(f"{PROGRAM_NAME} Finished!")
            return

        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    _run()
