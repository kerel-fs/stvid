from collections.abc import Iterable

import os
import shutil


class ExecutableNotFoundError(OSError):
    def __init__(self, executable, debian_package_hint=None):
        if debian_package_hint:
            message = f"{executable} can't be found in your system; Install the package '{debian_package_hint}'"
        else:
            message = f"{executable} can't be found in your system. " +
                      "Follow https://github.com/cbassa/stvid#installation for installation instructions."

        super().__init__(message)


def get_bin_path(executable, debian_package_hint=None):
    """
    Get the file path for the specified executable.
    If provided with a list, try the items sequentially until one alias is available.

    If no executable is found and debian_package_hint is provided,
    the raised error contains a message which guides users to install the specified package.

    Arguments:
    executable (str or Sequence of str): Name or path of the executable(s)
    debian_package_hint (str, optional): Name of the Debian package to suggest
                                         for installation in case of an error.
    """
    # Make sure we have always a list
    if not isinstance(executable, Iterable):
        executable = [executable]

    for cmd in executable:
        bin_file = shutil.which(cmd)

        if bin_file and os.path.isfile(bin_file):
            return bin_file

    raise ExecutableNotFoundError(executable, debian_package_hint)
