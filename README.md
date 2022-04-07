```bash
$$$$$$$\            $$\      $$\                     $$\
$$  __$$\           $$ | $\  $$ |                    $$ |
$$ |  $$ |$$\   $$\ $$ |$$$\ $$ | $$$$$$\   $$$$$$\  $$ |  $$\  $$$$$$\  $$$$$$$\
$$$$$$$  |$$ |  $$ |$$ $$ $$\$$ |$$  __$$\ $$  __$$\ $$ | $$  |$$  __$$\ $$  __$$\
$$  ____/ $$ |  $$ |$$$$  _$$$$ |$$ /  $$ |$$ |  \__|$$$$$$  / $$ /  $$ |$$ |  $$ |
$$ |      $$ |  $$ |$$$  / \$$$ |$$ |  $$ |$$ |      $$  _$$<  $$ |  $$ |$$ |  $$ |
$$ |      \$$$$$$$ |$$  /   \$$ |\$$$$$$  |$$ |      $$ | \$$\ \$$$$$$  |$$ |  $$ |
\__|       \____$$ |\__/     \__| \______/ \__|      \__|  \__| \______/ \__|  \__|
          $$\   $$ |
          \$$$$$$  |
           \______/
```
# PyWorkon

[![PyPI version][pypi-version]][pypi-link]
[![PyPI platforms][pypi-platforms]][pypi-link]
[![GitHub Discussion][github-discussions-badge]][github-discussions-link]
[![Conda-Forge][conda-badge]][conda-link]

PyWorkon is a command line interface to enter and manage your software projects. It is powered by [Nubia](https://github.com/facebookincubator/python-nubia) and [Rich](https://github.com/Textualize/rich) for the shell interface and [Textual](https://github.com/Textualize/textual) for it's TUI.

## Installation

You can install this library from [PyPI](https://pypi.org/project/pyworkon/) with `pip`:

```bash
python3 -m pip install pyworkon
```

or install it with `pipx`:
```bash
pipx install pyworkon
```


You can also use `pipx` to run the library without installing it:

```bash
pipx run pyworkon
```

## Features

pyworkon currently provides the following features (get help with `-h` or `--help`):

- Enter existing projects and start your favourite IDE (configurable)
- Project (GIT Repository) management
  - Create new projects from templates
  - Delete or archive projects
- Multiple (GIT hosting) providers
  - [GitHub](http://github.com/) and [GitHub Enterprise](https://github.com/enterprise)
  - [GitLab](https://gitlab.com/) and your self hosted GitLab instance(s)
  - [Bitbucket](https://bitbucket.org/)
- TUI (terminal user interface) and shell interface.
- Highly customizable


## Examples


**`workon` command:**

Enter an existing [GitHub project](https://github.com/chassing/pyworkon). (Github provider must be configured before hand)

![GIF of the workon command](https://github.com/chassing/pyworkon/releases/download/v0.3.0/tui.gif)


![GIF of the TUI functionality](https://github.com/chassing/pyworkon/releases/download/v0.3.0/tui.gif)


## Development

[![pre-commit.ci status][pre-commit-badge]][pre-commit-link]
[![Code style: black][black-badge]][black-link]

See [CONTRIBUTING.md](https://github.com/chassing/pyworkon/blob/main/.github/CONTRIBUTING.md) for details on how to set up a development environment.


[black-badge]:              https://img.shields.io/badge/code%20style-black-000000.svg
[black-link]:               https://github.com/psf/black
[conda-badge]:              https://img.shields.io/conda/vn/conda-forge/pyworkon
[conda-link]:               https://github.com/conda-forge/pyworkon-feedstock
[github-discussions-badge]: https://img.shields.io/static/v1?label=Discussions&message=Ask&color=blue&logo=github
[github-discussions-link]:  https://github.com/chassing/pyworkon/discussions
[pypi-link]:                https://pypi.org/project/pyworkon/
[pypi-platforms]:           https://img.shields.io/pypi/pyversions/pyworkon
[pypi-version]:             https://badge.fury.io/py/pyworkon.svg
