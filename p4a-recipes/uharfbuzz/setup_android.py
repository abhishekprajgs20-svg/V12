"""Minimal setup.py used ONLY for the python-for-android build of uharfbuzz.

The upstream setup.py needs Cython >= 3.1, setuptools_scm and the Limited API, none of which
python-for-android's host Python provides.  The uharfbuzz sdist already ships the Cython-generated
C++ (src/uharfbuzz/_harfbuzz.cpp) and the HarfBuzz sources (harfbuzz/), so we simply compile those.
"""
import os
from setuptools import setup, Extension

here = os.path.abspath(os.path.dirname(__file__))

ext = Extension(
    "uharfbuzz._harfbuzz",
    sources=[
        "src/uharfbuzz/_harfbuzz.cpp",
        "harfbuzz/src/harfbuzz-world.cc",
    ],
    define_macros=[
        ("HB_NO_MT", "1"),
        ("HB_HAS_SUBSET", "1"),
        ("HB_HAS_RASTER", "1"),
        ("HB_NO_PRAGMA_GCC_DIAGNOSTIC_ERROR", "1"),
    ],
    include_dirs=["harfbuzz/src"],
    extra_compile_args=["-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-w"],
    language="c++",
)

setup(
    name="uharfbuzz",
    version="0.57.0",
    packages=["uharfbuzz"],
    package_dir={"": "src"},
    package_data={"uharfbuzz": ["py.typed", "*.pyi"]},
    ext_modules=[ext],
    zip_safe=False,
)
