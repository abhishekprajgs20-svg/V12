import os
import shutil

from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe


class UharfbuzzRecipe(CppCompiledComponentsPythonRecipe):
    """python-for-android recipe for uharfbuzz (HarfBuzz text shaping, used for Hindi / Devanagari).

    The PyPI sdist already contains the Cython-generated C++ and the HarfBuzz sources, so the
    upstream setup.py (which needs Cython 3.1 + setuptools_scm) is replaced by setup_android.py.
    """
    version = '0.57.0'
    url = 'https://files.pythonhosted.org/packages/source/u/uharfbuzz/uharfbuzz-{version}.tar.gz'
    depends = ['setuptools']
    site_packages_name = 'uharfbuzz'
    call_hostpython_via_targetpython = False
    need_stl_shared = True

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        build_dir = self.get_build_dir(arch.arch)
        shutil.copyfile(os.path.join(self.get_recipe_dir(), 'setup_android.py'),
                        os.path.join(build_dir, 'setup.py'))


recipe = UharfbuzzRecipe()
