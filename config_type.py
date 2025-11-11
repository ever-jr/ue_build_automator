from pathlib import Path
from typing import Any, get_type_hints, override

import tomllib
from warnings import warn


#==============================================================================
# DEFAULTS

CONFIG_FILENAME = "config.toml"
DEFAULT_BUILD_NAME: str = "Windows"
DEFAULT_BUILD_TYPE: str = "Shipping"
BIN_DIR: str = "./bin"
DEFAULT_BUILD_OUTPUT_DIRECTORY: str = "./builds"

def _get_default_build_platform() -> str:
    return "Win64"

def _get_default_uat_path() -> str:
    return "C:/Program Files/Epic Games/UE_5.3/Engine/Build/BatchFiles/RunUAT.bat"

def get_default_svn_path() -> str:
    return "C:/Program Files/TortoiseSVN/bin/svn.exe"
    

#==============================================================================
# CONFIG HANDLING

_RawConfig = dict[str, Any]

def _load_config(path: Path) -> _RawConfig | None:
    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
        return config

    except:
        return None


def _get_config(config: _RawConfig | None, category: str, property: str) -> None | Any:
    if not config:
        return None

    config_category = config.get(category, None)

    if not config_category or not isinstance(config_category, dict):
        return None

    return config_category.get(property, None)


def _get_path_or_paths(possible_path: str | list[str]) -> Path | list[Path]:
    if isinstance(possible_path, list):
        out_paths: list[Path] = []
        for path in possible_path:
            out_paths.append(Path(path).resolve())

        return out_paths

    return Path(possible_path).resolve()


def try_find_uproject_path(project_path: Path) -> Path | None:
    if not project_path.exists():
        print(f"Project path '{project_path}' doens't exist!")
        return None

    if not project_path.is_dir():
        print(f"Project path '{project_path}' is not a directory!")
        return None

    for root, _, files in project_path.walk():
        for file in files:
            file = Path(file)
            if file.suffix == ".uproject":
                path = (root / file).resolve()
                return path

    print(f"Could not find .uproject on {project_path}")
    return None

#==============================================================================
# BASE

class _BA_Config:
    def __init__(self, category: str):
        self.category: str = category

    @override
    def __str__(self) -> str:
        return "unimplemented str"

    def is_valid(self) -> bool:
        warn("unimplemented method")
        return False

    def get_section_string(self) -> str:
        return f"[{self.category}]\n{str(self)}"

    def read_config(self, _config: _RawConfig) -> bool:
        warn("unimplemented read_config")
        return False


#==============================================================================
# PROJECT

class _BA_ProjectConfig(_BA_Config):
    def __init__(self):
        super().__init__("project")
        self._path: Path = Path()
        self._uproject: Path = Path()

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def path(self) -> Path:
        return self._path

    @path.setter
    def path(self, value: Path):
        if not value.exists():
            print("Invalid project path:", value)

        elif not value.is_dir():
            print(f"Project path '{value}' is not a directory!")

        uproject_path: Path | None = try_find_uproject_path(value)
        if uproject_path:
            self._uproject = uproject_path

        self._path = value

    @property
    def uproject(self) -> Path:
        return self._uproject

    @override
    def __str__(self) -> str:
        return f"""filename: {self.filename}
path: {self.path}
uproject: {self.uproject}"""

    @override
    def is_valid(self) -> bool:
        return (self.path.exists()
            and self.path.is_dir()
            and self.uproject.exists()
            and self.uproject.is_file()
            )
    
    @override
    def read_config(self, config: _RawConfig):
        project_path: str | None = _get_config(config, self.category, "path")

        if not project_path:
            print("No project path:", project_path)
            return False

        self.path = Path(project_path).resolve()
        if not self.is_valid():
            print("Invalid project data!")
            return False

        return True


#==============================================================================
# SVN

class _BA_SVNConfig(_BA_Config):
    def __init__(self):
        super().__init__("svn")
        self.exe: Path = Path(get_default_svn_path()).resolve()
        self._update_interval_in_seconds: int = 1
        self.cleanup_timeout_in_seconds: float = 1 * 60 * 60

    @property
    def update_interval_in_seconds(self) -> int:
        return self._update_interval_in_seconds

    @update_interval_in_seconds.setter
    def update_interval_in_seconds(self, value: int):
        if value <= 0:
            self.update_interval_in_seconds = 1
            print(f"Fixing SVN update interval '{value}s' -> '{self.update_interval_in_seconds}s'")
        else:
            self._update_interval_in_seconds = value

    @override
    def __str__(self) -> str:
        return f"""exe: {self.exe}
update interval in seconds: {self.update_interval_in_seconds}"""

    @override
    def is_valid(self) -> bool:
        return (self.exe.exists()
            and self.exe.is_file()
            )

    @override
    def read_config(self, config: _RawConfig) -> bool:
        svn_exe_path: str | None = _get_config(config, self.category, "exe_path")

        if svn_exe_path:
            self.exe = Path(svn_exe_path).resolve()
            if not self.exe.exists() or not self.exe.is_file():
                return False

        update_interval_in_seconds: int | None = _get_config(config, self.category, "update_interval_in_seconds")
        if update_interval_in_seconds:
            self.update_interval_in_seconds = update_interval_in_seconds

        cleanup_timeout_in_seconds: float | None = _get_config(config, self.category, "cleanup_timeout_in_seconds")
        if cleanup_timeout_in_seconds != None and cleanup_timeout_in_seconds > 1.0:
            self.cleanup_timeout_in_seconds = cleanup_timeout_in_seconds

        return True


#==============================================================================
# UNREAL AUTOMATION TOOL

class _BA_UnrealAutomationToolConfig(_BA_Config):
    def __init__(self):
        super().__init__("unreal")
        self.default_build_name: str = DEFAULT_BUILD_NAME
        self.exe: Path = Path(_get_default_uat_path()).resolve()
        self.platform: str = _get_default_build_platform()
        self.build_type: str = DEFAULT_BUILD_TYPE
        self.output: Path = Path(BIN_DIR).resolve()
        self.build_log_file: Path = self.output / "build_log.txt"

    @override
    def __str__(self) -> str:
        return f"""exe: {self.exe}
platform: {self.platform}
build type: {self.build_type}
output: {self.output}"""

    @override
    def is_valid(self) -> bool:
        return self.exe.exists() and self.exe.is_file()

    @override
    def read_config(self, config: _RawConfig) -> bool:
        uat_exe: str | None = _get_config(config, self.category, "uat_exe_path")
        if uat_exe:
            self.exe = Path(uat_exe).resolve()

        if not self.exe.exists() or not self.exe.is_file():
            print("Invalid Unreal Build Tool executable path:", self.exe)
            return False

        uat_platform: str | None = _get_config(config, self.category, "platform")
        if uat_platform:
            self.platform = uat_platform

        uat_build_type: str | None = _get_config(config, self.category, "build_type")
        if uat_build_type:
            self.build_type = uat_build_type

        return True


#==============================================================================
# BUILD EXPORT

class _BA_BuildExportConfig(_BA_Config):
    def __init__(self):
        super().__init__("build_export")
        self.override_zip: bool = False
        self.output: Path = Path(DEFAULT_BUILD_OUTPUT_DIRECTORY).resolve()
        self.max_num_relevant_logs: int = 10

    @override
    def __str__(self) -> str:
        return f"""override zip: {self.override_zip}
output: {self.output}"""

    @override
    def is_valid(self) -> bool:
        return True
    
    @override
    def read_config(self, config: _RawConfig) -> bool:
        override_zip: bool | None = _get_config(config, self.category, "override_zip")
        if override_zip:
            self.override_zip = override_zip

        output_directory: str | None = _get_config(config, self.category, "output_directory")
        if output_directory:
            self.output = Path(output_directory).resolve()

        max_num_relevant_logs: int | None = _get_config(config, self.category, "max_num_relevant_logs")
        if max_num_relevant_logs and max_num_relevant_logs < 999:
            self.max_num_relevant_logs = max_num_relevant_logs

        return True


#==============================================================================
# SPECIAL LOG KEYWORDS

class _BA_SpecialLogKeywordsCommandsConfig(_BA_Config):
    def __init__(self):
        super().__init__("special_log_keywords")
        self.is_enabled: bool = True
        self.make_dev_build: str = "#devbuild"
        self.ignore_build: str = "#ignorebuild"

    @override
    def __str__(self) -> str:
        return f"make dev build: {self.make_dev_build}"

    @override
    def is_valid(self) -> bool:
        return (self.make_dev_build != ""
            and self.ignore_build != ""
            )

    @override
    def read_config(self, config: _RawConfig) -> bool:
        is_enabled: bool | None = _get_config(config, self.category, "enabled")
        if is_enabled != None:
            self.is_enabled = is_enabled

        make_dev_build: str | None = _get_config(config, self.category, "make_dev_build")
        if make_dev_build:
            self.make_dev_build = make_dev_build

        ignore_build: str | None = _get_config(config, self.category, "ignore_build")
        if ignore_build:
            self.ignore_build = ignore_build

        return self.is_valid()

    @property
    def all_commands(self) -> list[str]:
        return [
            self.make_dev_build,
            self.ignore_build,
        ]

        


#==============================================================================
# SOUNDS

class _BA_SoundsConfig(_BA_Config):
    def __init__(self):
        super().__init__("sounds")
        self.build_starting: list[Path] | Path = Path("./").resolve()
        self.build_success: list[Path] | Path = Path("./").resolve()
        self.build_fail: list[Path] | Path = Path("./").resolve()
        self.build_unknown_error: list[Path] | Path = Path("./").resolve()

    @override
    def __str__(self) -> str:
        sounds_paths = {
            "build starting": self.build_starting,
            "build success": self.build_success,
            "build fail": self.build_fail,
            "build unknown error": self.build_unknown_error,
        }
        text: str = ""
        for path_key in sounds_paths:
            text += f"{path_key}: "
            path: list[Path] | Path = sounds_paths[path_key]
            if isinstance(path, Path):
                text += path.name
            else:
                num_paths: int = len(path)
                for i in range(num_paths):
                    sub_path: Path = path[i]
                    text += f"{sub_path.name}"
                    if i < num_paths:
                        text += ", "
            text += "\n"

        return text

    @override
    def is_valid(self) -> bool:
        return True

    @override
    def read_config(self, config: _RawConfig) -> bool:
        sounds_build_starting:      list[str] | str | None = _get_config(config, self.category, "build_starting")
        sounds_build_success:       list[str] | str | None = _get_config(config, self.category, "build_success")
        sounds_build_fail:          list[str] | str | None = _get_config(config, self.category, "build_fail")
        sounds_build_unknown_error: list[str] | str | None = _get_config(config, self.category, "build_unknown_error")

        if sounds_build_starting:
            self.build_starting = _get_path_or_paths(sounds_build_starting)

        if sounds_build_success:
            self.build_success = _get_path_or_paths(sounds_build_success)

        if sounds_build_fail:
            self.build_fail = _get_path_or_paths(sounds_build_fail)

        if sounds_build_unknown_error:
            self.build_unknown_error = _get_path_or_paths(sounds_build_unknown_error)

        return self.is_valid()


#==============================================================================
# ALL CONFIGS

class BuildAutomatorConfig:
    def __init__(self, config: _RawConfig | None = None):
        self.should_print_configs: bool = True
        self.project: _BA_ProjectConfig = _BA_ProjectConfig()
        self.svn: _BA_SVNConfig = _BA_SVNConfig()
        self.uat: _BA_UnrealAutomationToolConfig = _BA_UnrealAutomationToolConfig()
        self.build_export: _BA_BuildExportConfig = _BA_BuildExportConfig()
        self.special_log_keywords: _BA_SpecialLogKeywordsCommandsConfig = _BA_SpecialLogKeywordsCommandsConfig()
        self.sounds: _BA_SoundsConfig = _BA_SoundsConfig()

        if config:
            should_print_configs: bool | None = _get_config(config, "development", "print_config")
            if should_print_configs != None:
                self.should_print_configs = should_print_configs 

            for property_config in self.all_configs:
                if not property_config.read_config(config):
                    warn(f"Failed to read property config: {property_config.category}")
                    break

    @property
    def all_configs(self) -> list[_BA_Config]:
        return [
            self.project,
            self.svn,
            self.uat,
            self.special_log_keywords,
            self.build_export,
            self.sounds,
        ]

    @override
    def __str__(self) -> str:
        text = f"should print configs: {self.should_print_configs}\n\n"

        for config in self.all_configs:
            text += config.get_section_string() + "\n\n"

        return text


    def is_valid(self) -> bool:
        return all(config.is_valid() for config in self.all_configs)


    def get_invalid_configs(self) -> list[_BA_Config]:
        invalid_configs: list[_BA_Config] = []

        for config in self.all_configs:
            if not config.is_valid():
                invalid_configs.append(config)

        return invalid_configs


    def get_invalid_configs_string(self) -> str:
        text: str = ""

        for config in self.get_invalid_configs():
            text += config.get_section_string() + '\n'

        return text


def build_automator_load_config() -> BuildAutomatorConfig | None:
    config_path = Path(CONFIG_FILENAME).resolve()

    if not config_path.exists() or not config_path.is_file():
        print(f"Unable to find config file {CONFIG_FILENAME}.")
        return None

    config: _RawConfig | None = _load_config(config_path)
    if config:
        return BuildAutomatorConfig(config)

    return None
