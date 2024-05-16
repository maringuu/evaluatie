#!/bin/sh

# SPDX-FileCopyrightText: 2024 Marten Ringwelski
# SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>
#
# SPDX-License-Identifier: AGPL-3.0-only

set -e

archives=(\
    "lto.7z" \
    "noinline.7z" \
    "normal.7z" \
    "obfus.7z" \
    "obfus_2loop.7z" \
    "pie.7z" \
    "sizeopt.7z" \
)
# XXX sizeopt is wired

for archive in ${archives[@]}; do
    7z x -aos $archive
done
