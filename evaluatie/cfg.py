# SPDX-FileCopyrightText: 2024 Marten Ringwelski
# SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>
#
# SPDX-License-Identifier: AGPL-3.0-only

import os
import pathlib as pl
from configparser import ConfigParser

_config = None


class _Throw:
    pass


_config_path = pl.Path(
    os.getenv(
        "ZACKEN_CONFIG_PATH",
        pl.Path.home() / ".config" / "evaluatie" / "config.ini",
    )
)


def load():
    if not pl.Path(_config_path).exists():
        raise FileNotFoundError(
            f"Expected the configuration file at {_config_path.absolute()} but the file does not exist."
        )

    global _config  # noqa: PLW0603
    config = ConfigParser()
    config.read(_config_path)
    _config = config


load()


def get(section: str, key: str, default=_Throw) -> str:
    """Returns the value of the key in section.
    Raises a KeyError when default is not set and then entry does not exist.
    """
    try:
        s = _config[section]
    except KeyError as err:
        if default == _Throw:
            raise KeyError(f"Section '{section}' does not exist") from err
        return default

    try:
        value = s[key]
    except KeyError as err:
        if default == _Throw:
            raise KeyError(f"Key '{key}' does not exist in section {section}.") from err
        return default

    return value


def gets(section: str, key: str, default: str = _Throw) -> str:
    value = get(section, key, default)
    return value


def getb(section: str, key: str, default: bool = _Throw) -> bool:
    """Raises a ValueError when the key cannot be converted"""
    value = get(section, key, default)

    if isinstance(value, bool):
        # The default used and is a boolean
        return value

    if value in ["true", "True"]:
        return True
    if value in ["false", "False"]:
        return False

    raise ValueError(f"{value} is not a valid boolean.")


def geti(section: str, key: str, default: int = _Throw) -> int:
    value = get(section, key, default)
    return int(value, base=0)
