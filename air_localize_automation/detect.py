import os
import numpy as np
import matlab.engine
from air_localize_automation.numpy_as_matlab import as_matlab
from air_localize_automation.filter_spots import apply_foreground_mask
from ClusterWrap.decorator import cluster
import dask.array as da
import dask.delayed as delayed


def detect_spots(
    image,
    params_path,
    air_localize_path,
    output_path=None,
):
    """
    """

    # prepare matlab engine and data
    eng = matlab.engine.start_matlab()
    eng.addpath(air_localize_path)
    matlab_image = as_matlab(image)

    # default output path is scratch directory
    # this is specific to janelia
    if output_path is None:
        output_path = '/scratch/' + os.environ.get("USER")

    # run spot detection
    spots = eng.AIRLOCALIZE_N5(
        params_path, matlab_image, output_path, nargout=1,
    )

    # reformat spots then quit engine
    spots = np.array(spots._data).reshape(spots.size, order='F')
    eng.quit()

    # return
    return spots


@cluster
def distributed_detect_spots(
    zarr_array,
    blocksize,
    params_path,
    air_localize_path,
    overlap=12,
    mask=None,
    cluster=None,
    cluster_kwargs={},
):
    """
    """

    # define mask to data grid size ratio
    if mask is not None:
        ratio = np.array(mask.shape) / zarr_array.shape

    # define closure for detect_spots function
    def detect_spots_closure(image, mask=None, block_info=None):

        # get block and block minus overlap origins
        block_origin = blocksize * np.array(block_info[0]['chunk-location'])
        overlap_origin = np.maximum(0, block_origin - overlap)

        # check mask
        if mask is not None:

            # get region at mask scale level
            mo = np.round(block_origin * ratio).astype(np.uint16)
            ms = np.round(blocksize * ratio).astype(np.uint16)
            mask_slice = tuple(slice(x, x+y) for x, y in zip(mo, ms))
            mask_block = mask[mask_slice]

            # if there is no foreground, return null result
            if np.sum(mask_block) < 1:
                result = np.empty((1,1,1), dtype=np.ndarray)
                result[0, 0, 0] = np.zeros((0, 4))  # TODO: CONFIRM THAT 4 HERE IS CORRECT
                return result

        # get spots
        spots = detect_spots(
            image, params_path, air_localize_path,
        )

        # filter out spots in the overlap region
        for i in range(3):
            spots = spots[spots[:, i] > overlap - 1]
            spots = spots[spots[:, i] < overlap + blocksize[i]]

        # adjust spots for origin
        spots[:, :3] = spots[:, :3] + overlap_origin

        # package as object and return
        result = np.empty((1,1,1), dtype=np.ndarray)
        result[0, 0, 0] = spots
        return result


    # wrap data and mask as dask objects
    dask_array = da.from_array(zarr_array, chunks=blocksize)
    mask_d = delayed(mask) if mask is not None else None

    # run spot detection on overlapping blocks
    # TODO: THINK OVER THE BOUNDARY CONDITION
    spots_as_grid = da.map_overlap(
        detect_spots_closure, dask_array,
        mask=mask_d,
        depth=overlap,
        dtype=np.ndarray,
        boundary=0,
        trim=False,
        chunks=(1,1,1),
    ).compute()

    # reformat all detections into single array
    spots_list = []
    for ijk in range(np.prod(spots_as_grid.shape)):
        i, j, k = np.unravel_index(ijk, spots_as_grid.shape)
        spots_list.append(spots_as_grid[i, j, k])
    spots = np.vstack(spots_list)

    # filter with foreground mask
    if mask is not None:
        spots = apply_foreground_mask(spots, mask, ratio)

    # return result
    return spots

