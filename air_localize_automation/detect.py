import os, psutil
import numpy as np
import matlab
import matlab.engine
from air_localize_automation.numpy_to_matlab import as_matlab
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

    # get number of cores available
    ncpus = os.environ.get("LSB_DJOB_NUMPROC")
    if ncpus is None: ncpus = psutil.cpu_count(logical=False)
    ncpus = 2 * int(ncpus)

    # TODO: the matlab engine for python has a memory leak. MathWorks knows about this
    #       but has not fixed it. It's tolerable for now, but for serious use an
    #       alternative python/matlab integration might be necessary.
    #       memory leak: https://bastibe.de/2015-10-29-matlab-engine-leaks.html
    #       alternative integration: https://github.com/bastibe/transplant
    # prepare matlab engine and data
    eng = matlab.engine.start_matlab("-nodisplay -nodesktop -nojvm -nosplash")
    eng.maxNumCompThreads(ncpus)
    eng.addpath(air_localize_path)
    eng.addpath(air_localize_path + '/AIRLOCALIZE_1_5_subfunctions')
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

    # get intensity values at detected coordinates
    if spots.shape == (0, 5):
        spots = np.zeros((0, 6))
    else:
        coords = np.round(spots[:, :3]).astype(int)
        for i in range(3):
            coords[:, i] = np.maximum(0, coords[:, i])
            coords[:, i] = np.minimum(image.shape[i]-1, coords[:, i])
        intensities = image[coords[:, 0], coords[:, 1], coords[:, 2]]
        spots = np.concatenate((spots, intensities[..., None]), axis=1)

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
    transpose=None,
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
        overlap_origin = block_origin - overlap

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
                result[0, 0, 0] = np.zeros((0, 6))
                return result

        # check transpose (because air localize requires xyz order)
        if transpose is not None:
            image = image.transpose( transpose )

        # get spots
        spots = detect_spots(
            image, params_path, air_localize_path,
        )

        # if transposed restore input axis order
        if transpose is not None:
            spots[:, :3] = spots[:, :3][:, transpose]

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
    spots_as_grid = da.map_overlap(
        detect_spots_closure, dask_array,
        mask=mask_d,
        depth=overlap,
        dtype=np.ndarray,
        boundary='reflect',
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

