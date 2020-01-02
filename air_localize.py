import z5py
import numpy as np
import sys
import json
import matlab, matlab.engine
import n5_metadata_utils as n5mu
from _internal.mlarray_utils import _get_strides, _get_mlsize


# BEGIN:
# copied from SO:
# https://stackoverflow.com/questions/10997254/converting-numpy-arrays-to-matlab-and-vice-versa
def _wrapper__init__(self, arr):
    assert arr.dtype == type(self)._numpy_type
    self._python_type = type(arr.dtype.type().item())
    self._is_complex = np.issubdtype(arr.dtype, np.complexfloating)
    self._size = _get_mlsize(arr.shape)
    self._strides = _get_strides(self._size)[:-1]
    self._start = 0

    if self._is_complex:
        self._real = arr.real.ravel(order='F')
        self._imag = arr.imag.ravel(order='F')
    else:
        self._data = arr.ravel(order='F')

_wrappers = {}
def _define_wrapper(matlab_type, numpy_type):
    t = type(matlab_type.__name__, (matlab_type,), dict(
        __init__=_wrapper__init__,
        _numpy_type=numpy_type
    ))
    # this tricks matlab into accepting our new type
    t.__module__ = matlab_type.__module__
    _wrappers[numpy_type] = t

_define_wrapper(matlab.double, np.double)
_define_wrapper(matlab.single, np.single)
_define_wrapper(matlab.uint8, np.uint8)
_define_wrapper(matlab.int8, np.int8)
_define_wrapper(matlab.uint16, np.uint16)
_define_wrapper(matlab.int16, np.int16)
_define_wrapper(matlab.uint32, np.uint32)
_define_wrapper(matlab.int32, np.int32)
_define_wrapper(matlab.uint64, np.uint64)
_define_wrapper(matlab.int64, np.int64)
_define_wrapper(matlab.logical, np.bool_)

def as_matlab(arr):
    try:
        cls = _wrappers[arr.dtype.type]
    except KeyError:
        raise TypeError("Unsupported data type")
    return cls(arr)
# END: SO copy


def read_coords(path):
    with open(path, 'r') as f:
        offset = np.array(f.readline().split(' ')).astype(np.float64)
        extent = np.array(f.readline().split(' ')).astype(np.float64)
    return offset, extent



if __name__ == '__main__':

    image       = sys.argv[1]
    subpath     = sys.argv[2]
    coords      = sys.argv[3]
    params      = sys.argv[4]
    output      = sys.argv[5]
    suffix      = sys.argv[6]

    offset, extent = read_coords(coords)
    vox            = n5mu.read_voxel_spacing(image, subpath)
    offset_vox     = np.round(offset/vox).astype(np.uint16)
    extent_vox     = np.round(extent/vox).astype(np.uint16)
    ends           = offset_vox + extent_vox

    image = z5py.File(image, use_zarr_format=False)[subpath]
    data  = image[offset_vox[2]:ends[2], offset_vox[1]:ends[1], offset_vox[0]:ends[0]]
    data  = np.moveaxis(data, (0, 2), (2, 0))

    eng = matlab.engine.start_matlab()
    air_localize_path = '/groups/scicompsoft/home/fleishmang/source'
    air_localize_path += '/AIRLOCALIZE1_5_PAR_batch'
    eng.addpath(air_localize_path)
    air_localize_path += '/AIRLOCALIZE_1_5_subfunctions'
    eng.addpath(air_localize_path)
    matlab_data = as_matlab(data)
    points = eng.AIRLOCALIZE_N5(params, matlab_data, output, nargout=1)
    points = np.array(points._data).reshape(points.size, order='F')
    # TODO: according to Yuhan's code, x/y must be swapped in points (i.e. airlocalize: (y, x, z))
    # TODO: write default spot file for tiles that return 0 spots
    points[:, :3] = points[:, :3] * vox + offset

    np.savetxt(output + '/air_localize_points' + suffix, points)

