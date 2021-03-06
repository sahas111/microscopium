"""Feature computations and other functions for Cellomics screens.
"""
from __future__ import absolute_import

import os
import collections as coll
from skimage import io
import numpy as np
from cytoolz import groupby
from ..preprocess import stretchlim
from six.moves import range
from six.moves import zip


def batch_stitch_stack(file_dict, output, order=[0, 1, 2], target_bit_depth=8, **kwargs):
    """Run snail stitch and concatenate the channels across a set of images.

    This function takes the (plate, well) dictionary built using the
    ``make_key2file`` function. Images are grouped according to their channel,
    stitched together and stacked into a single 3-channel image. Images
    are re-scaled and saved to a user specified output directory. Images
    are saved to directories according to their plate number.

    Parameters
    ----------
    file_dict : dict { tuple (plate, well) : list of strings }
        The dictionary mapping the (plate, well) tuple to a list of image
        files. This dictionary is built using the ``make_key2file`` function.
    output : string
        The directory to output the stitched and concatenated images to.
    order : list of int, optional
        The order the channels should be in in the final image.
    target_bit_depth : int in {8, 16}, optional
        If None, perform no rescaling. Otherwise, rescale to occupy
        the dynamic range of the target bit depth.
    **kwargs : dict
        Keyword arguments to be passed to
        `microscopium.preprocess.stretchlim`
    """
    for fns in list(file_dict.values()):
        sem = cellomics_semantic_filename(fns[0])
        plate = str(sem['plate'])
        new_fn = '-'.join([sem['prefix'], plate, sem['well']])
        new_fn = '.'.join([new_fn, sem['suffix']])

        channels = groupby(get_channel, fns)
        while len(channels) < 3:
            channels[np.max(list(channels.keys())) + 1] = None

        images = []
        for channel, fns in sorted(channels.items()):
            if fns is None:
                images.append(None)
            else:
                image = snail_stitch(fns)
                image = rescale_from_12bit(image, target_bit_depth, **kwargs)
                images.append(image)

        concat_image = stack_channels(images, order=order)

        out_dir = os.path.join(output, plate)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        io.imsave(os.path.join(out_dir, new_fn), concat_image)


def rescale_from_12bit(image, target_bit_depth=8, **kwargs):
    """Rescale a 12bit image.

    Cellomics TIFs are encoded as 12bit TIF files. This function rescales the
    images to a new bit depth of 8 or 16.

    Parameters
    ----------
    image : array, shape (M, N)
        The image to be rescaled.
    target_bit_depth : int in {8, 16}, optional
        The bit range to scale the images to.
    **kwargs : dict
        Keyword arguments to be passed to
        `microscopium.preprocess.stretchlim`

    Returns
    -------
    scale_image : array, shape (M, N)
        The rescaled image.

    Examples
    --------
    >>> image = np.array([[0, 2047, 4095]])
    >>> rescale_from_12bit(image, 8)
    array([[  0, 127, 255]], dtype=uint8)
    """
    image = stretchlim(image, **kwargs)
    if target_bit_depth == 8:
        scale_image = np.round(image * 255).astype(np.uint8)
    elif target_bit_depth == 16:
        scale_image = np.round(image * 65535).astype(np.uint16)
    else:
        scale_image = image
    return scale_image


def stack_channels(images, order=[0, 1, 2]):
    """Stack multiple image files to one single, multi-channel image.

    Parameters
    ----------
    images : list of array, shape (M, N)
        The images to be concatenated. List should contain
        three images. Entries 'None' are considered to be dummy
        channels
    order : list of int, optional
        The order the channels should be in in the final image.

    Returns
    -------
    conat_image : array, shape (M, N, 3)
        The concatenated, three channel image.

    Examples
    --------
    >>> image1 = np.ones((2, 2)) * 1
    >>> image2 = np.ones((2, 2)) * 2
    >>> joined = stack_channels((image1, image2, None))
    >>> joined.shape
    (2, 2, 3)
    """
    m = images[0].shape[0]
    n = images[0].shape[1]
    dtype = images[0].dtype
    concat_image = np.zeros((m, n, 3), dtype=dtype)
    for i in range(0, 3):
        if images[order[i]] is not None:
            concat_image[:, :, i] = images[order[i]]
    return concat_image


def snail_stitch(fns):
    """Run right, clockwise spiral/snail stitching of 25 Cellomics TIFs.

    Runs clockwise stitching of the images. The spiral begins in the
    center of the image, moves to the right and circles around in a clockwise
    manner.

    Parameters
    ----------
    fns : list of array, shape (M, N)
        The list of 25 image files to be stitched together.

    Returns
    -------
    stitched_image : array, shape (5*M, 5*N)
        The stitched image.
    """
    fns.sort()
    order = [[20, 21, 22, 23, 24],
             [19, 6, 7, 8, 9],
             [18, 5, 0, 1, 10],
             [17, 4, 3, 2, 11],
             [16, 15, 14, 13, 12]]

    image0 = io.imread(fns[0])
    m = image0.shape[0]
    n = image0.shape[1]
    stitched_image = np.zeros((5*m, 5*n))
    for i in range(0, 5):
        for j in range(0, 5):
            index = order[i][j]
            image = io.imread(fns[index])
            stitched_image[m*i:m*(i+1), n*j:n*(j+1)] = image
    return stitched_image


def make_key2file(fns):
    """Return a dictionary mapping well co-ordinates to filenames.

    Returns a dictionary where key are (plate, well) co-ordinates and
    values are lists of images corresponding to that plate and well.

    Parameters
    ----------
    fns : list of string
        A list of Cellomics TIF files.

    Returns
    -------
    wellchannel2file : dict {tuple : list of string}
        The dictionary mapping the (plate, well) co-ordinate to
        a list of files corresponding to that well.
    """
    wellchannel2file = groupby(filename2coord, fns)
    return wellchannel2file


def get_channel(fn):
    """Get channel from Cellomics filename.

    Parameters
    ----------
    fn : string
        A filename from the Cellomics high-content screening system.

    Returns
    -------
    channel : int
        The channel of the filename.

    Examples
    --------
    >>> fn = 'MFGTMP_140206180002_A01f00d0.TIF'
    >>> get_channel(fn)
    0
    """
    sem = cellomics_semantic_filename(fn)
    channel = sem['channel']
    return channel


def get_column(fn):
    """Get column from Cellomics filename.

    Parameters
    ----------
    fn : string
        A filename from the Cellomics high-content screening system.

    Returns
    -------
    column : string
        The channel of the filename.

    Examples
    --------
    >>> fn = 'MFGTMP_140206180002_A01f00d0.TIF'
    >>> get_column(fn)
    '01'
    """
    sem = cellomics_semantic_filename(fn)
    column = sem['well'][1:]
    return column


def cellomics_semantic_filename(fn):
    """Split a Cellomics filename into its annotated components.

    Parameters
    ----------
    fn : string
        A filename from the Cellomics high-content screening system.

    Returns
    -------
    semantic : collections.OrderedDict {string: string}
        A dictionary mapping the different components of the filename.

    Examples
    --------
    >>> fn = ('MFGTMP_140206180002_A01f00d0.TIF')
    >>> d = cellomics_semantic_filename(fn)
    >>> d
    OrderedDict([('directory', ''), ('prefix', 'MFGTMP'), ('plate', 140206180002), ('well', 'A01'), ('field', 0), ('channel', 0), ('suffix', 'TIF')])
    """
    keys = ['directory', 'prefix', 'plate', 'well', 'field', 'channel', 'suffix']
    directory, fn = os.path.split(fn)
    filename, suffix = fn.split('.')[0], '.'.join(fn.split('.')[1:])

    # ignore '_stitched' tag
    split_fn = filename.split('_')
    if len(split_fn) == 4:
        split_fn = split_fn[:-1]

    prefix, plate, code = split_fn
    well = code[:3]
    field = int(code[4:6])
    channel = int(code[-1])
    values = [directory, prefix, int(plate), well, field, channel, suffix]
    semantic = coll.OrderedDict(list(zip(keys, values)))
    return semantic


def filename2coord(fn):
    """Obtain (plate, well) coordinates from a filename.

    Parameters
    ----------
    fn : string
        The input filename

    Returns
    -------
    coord : (int, string, int) tuple
        The (plate, well, cell) coordinates of the image.

    Examples
    --------
    >>> fn = 'MFGTMP_140206180002_A01f00d0.TIF'
    >>> filename2coord(fn)
    (140206180002, 'A01')
    """
    sem = cellomics_semantic_filename(fn)
    return (sem['plate'], sem['well'])


def dir2plate(path):
    """Return a Plate ID from a directory name.

    Parameters
    ----------
    path : string
        A directory containing export images from an HCS plate.

    Returns
    -------
    plateid : int
        The plate ID parsed from the directory name.

    Examples
    --------
    >>> dir2plate('MFGTMP_140206180002')
    140206180002
    """
    basedir = os.path.split(path)[1]
    plateid = int(basedir.split('_')[1])
    return plateid


if __name__ == '__main__':
    import doctest
    doctest.testmod()
