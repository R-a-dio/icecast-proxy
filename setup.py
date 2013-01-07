from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext

setup(
    cmdclass = {'build_ext': build_ext},
    ext_modules = [Extension("carray_buffer", ["buffers/carray_buffer.pyx"],
                        extra_compile_args=['-fopenmp'],
                        extra_link_args=['-fopenmp'])]
)

import os

filename = 'carray_buffer.so'
filepath = os.path.join(os.getcwd(), filename)
if os.path.exists(filepath):
    # We got installed --inplace
    destination = os.path.join(os.getcwd(), 'buffers')
    if os.path.exists(destination):
        os.rename(filepath, os.path.join(destination, filename))