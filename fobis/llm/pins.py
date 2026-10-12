"""pins.py — the llama.cpp build FoBiS installs, with the sha256 of every release asset it may download.

Upstream publishes several builds a day (all marked pre-release), so FoBiS never follows "latest": each FoBiS
release pins one build. The digests below are the ones GitHub publishes for the release assets; they were
generated from ``gh api repos/ggml-org/llama.cpp/releases/tags/<build>``, never typed by hand. To move the pin,
regenerate the whole table for the new build and run the opt-in real-runtime test.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from dataclasses import dataclass

PINNED_BUILD = "b11308"  # 2026-10-01
RELEASES_URL = "https://github.com/ggml-org/llama.cpp/releases/download"


@dataclass(frozen=True)
class Asset:
    """A release asset: file name and sha256."""

    name: str
    sha256: str


# (os, arch, variant) -> (llama.cpp archive, CUDA runtime archive or None). os/arch as normalised by
# `fobis.llm.runtime.platform_key`. CUDA variants need the separate CUDA runtime archive.
ASSETS: dict[tuple[str, str, str], tuple[Asset, Asset | None]] = {
    ("linux", "x86_64", "cpu"): (
        Asset("llama-b11308-bin-ubuntu-x64.tar.gz", "028c7bfafd267fa468acae107832e8cd0eeb185cf9c0ab7294314fda229141ee"),
        None,
    ),
    ("linux", "x86_64", "cuda12"): (
        Asset(
            "llama-b11308-bin-ubuntu-cuda-12.8-x64.tar.gz",
            "3d586412ff5093b85e815948ce6fe9531b6bd143e282798293f8392735ca113d",
        ),
        Asset(
            "cudart-llama-b11308-bin-ubuntu-cuda-12.8-x64.tar.gz",
            "be89acebbb786c4f7a9c393dbb1f81c81211144af50db6dad5f7d9e631b0e7cc",
        ),
    ),
    ("linux", "x86_64", "cuda13"): (
        Asset(
            "llama-b11308-bin-ubuntu-cuda-13.4-x64.tar.gz",
            "83d446f81617535c7cb32292351a8774578764c3309078bd5644ac5baf047770",
        ),
        Asset(
            "cudart-llama-b11308-bin-ubuntu-cuda-13.4-x64.tar.gz",
            "efa41b67580ae82a2670f0bcb6cf265eec93265ba9f8129970f00e590c251974",
        ),
    ),
    ("linux", "x86_64", "vulkan"): (
        Asset(
            "llama-b11308-bin-ubuntu-vulkan-x64.tar.gz",
            "a48d18b424c9ff3202068a630424ca369405868064367136060691db3275f7b8",
        ),
        None,
    ),
    ("linux", "x86_64", "rocm"): (
        Asset(
            "llama-b11308-bin-ubuntu-rocm-10.0-x64.tar.gz",
            "44695c1d4d05507733757cbd33ac66d13853fb995f4daf63a031b6d8a88d7617",
        ),
        None,
    ),
    ("linux", "x86_64", "sycl"): (
        Asset(
            "llama-b11308-bin-ubuntu-sycl-fp32-x64.tar.gz",
            "33e96503d307045e1d1bc442b5ec3e47979ee0cc1d6fc25ebc96dc43a35b42f6",
        ),
        None,
    ),
    ("linux", "aarch64", "cpu"): (
        Asset(
            "llama-b11308-bin-ubuntu-arm64.tar.gz", "393676b0d80f4e69da2084ee1c0e170093a3e6195bedf3bdecc3e5d0060dfdc4"
        ),
        None,
    ),
    ("linux", "aarch64", "cuda13"): (
        Asset(
            "llama-b11308-bin-ubuntu-cuda-13.4-arm64.tar.gz",
            "af6edce1513515e3839c33ca5707ed45099b022fd09c6b7aa4b241c04472d99f",
        ),
        Asset(
            "cudart-llama-b11308-bin-ubuntu-cuda-13.4-arm64.tar.gz",
            "6b3a44893392b9529237a92d7de18433de5db655dac2b933ed611c8893305e3e",
        ),
    ),
    ("linux", "aarch64", "vulkan"): (
        Asset(
            "llama-b11308-bin-ubuntu-vulkan-arm64.tar.gz",
            "d7e4a2893ab2a5bceefe88ba35e58e7fdbf3673907380a5aa7b611a2f462f5a7",
        ),
        None,
    ),
    ("darwin", "arm64", "metal"): (
        Asset(
            "llama-b11308-bin-macos-arm64.tar.gz", "67388a2207b82b535828045322b1e7c932983cf5eeac6000f871b9c9b4b58759"
        ),
        None,
    ),
    ("darwin", "x86_64", "cpu"): (
        Asset("llama-b11308-bin-macos-x64.tar.gz", "301be7089e2c3066c76ae446c58beca97ebf3640bfe567cdaa7caa212a7395da"),
        None,
    ),
    ("windows", "amd64", "cpu"): (
        Asset("llama-b11308-bin-win-cpu-x64.zip", "f7964ab3b61805a8578990c677726a9db39ee8344e4b5c9de9774208162a0692"),
        None,
    ),
    ("windows", "amd64", "cuda12"): (
        Asset(
            "llama-b11308-bin-win-cuda-12.4-x64.zip", "f4536789b5befb4ebc8b425ba798e55b8116f598058573026f9753dc450280c9"
        ),
        Asset(
            "cudart-llama-bin-win-cuda-12.4-x64.zip", "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"
        ),
    ),
    ("windows", "amd64", "cuda13"): (
        Asset(
            "llama-b11308-bin-win-cuda-13.4-x64.zip", "e112db35aabf7d144d4c2e612c26376fe69d387cc93b10c1f4b4954ffe87b7e6"
        ),
        Asset(
            "cudart-llama-bin-win-cuda-13.4-x64.zip", "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668"
        ),
    ),
    ("windows", "amd64", "vulkan"): (
        Asset(
            "llama-b11308-bin-win-vulkan-x64.zip", "fe9896d9faa20c4a617adf7dbc31b3abd707d9d0fce7b600dc14d63a037b02df"
        ),
        None,
    ),
    ("windows", "arm64", "cpu"): (
        Asset("llama-b11308-bin-win-cpu-arm64.zip", "e196ed6558735213accb4eeba27271e5e3dfdd0299b0cff3d9076b4912e1d2ed"),
        None,
    ),
}


def asset_url(build: str, name: str) -> str:
    """Download URL of the release asset *name* of *build*."""
    return f"{RELEASES_URL}/{build}/{name}"
