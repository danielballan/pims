from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six
from six.moves import map
import os
import glob
import fnmatch
from warnings import warn
import re
import zipfile
from six.moves import StringIO

import numpy as np

from pims.base_frames import FramesSequence, FramesSequenceND
from pims.frame import Frame
from pims.utils.sort import natural_keys

try:
    from skimage.io import imread as skimage_imread
except ImportError:
    skimage_imread = None
try:
    from matplotlib.pyplot import imread as mpl_imread
except ImportError:
    mpl_imread = None
try:
    from scipy.ndimage import imread as scipy_imread
except ImportError:
    scipy_imread = None
try:
    from tifffile import imread as tifffile_imread
except ImportError:
    tifffile_imread = None
try:
    from PIL import Image
except ImportError:
    pil_imread = None
else:
    def pil_imread(filename):
        return np.asarray(Image.open(filename))


def skimage_available():
    return skimage_imread is not None


def mpl_available():
    return mpl_imread is not None


def scipy_available():
    return scipy_imread is not None


def tifffile_available():
    return tifffile_imread is not None


def PIL_available():
    return pil_imread is not None


class BaseImageSequence(FramesSequence):
    """Read a directory of sequentially numbered image files into an
    iterable that returns images as numpy arrays.

    Parameters
    ----------
    path_spec : string or iterable of strings
        a directory or, safer, a pattern like path/to/images/*.png
        which will ignore extraneous files or a list of files to open
        in the order they should be loaded. When a path to a zipfile is
        specified, all files in the zipfile will be loaded.
    process_func : function, optional
        callable with signalture `proc_img = process_func(img)`,
        which will be applied to the data from each frame
    dtype : numpy datatype, optional
        Image arrays will be converted to this datatype.
    as_grey : boolean, optional
        Convert color images to greyscale. False by default.
        May not be used in conjection with process_func.

    Examples
    --------
    >>> video = ImageSequence('path/to/images/*.png')  # or *.tif, or *.jpg
    >>> imshow(video[0]) # Show the first frame.
    >>> imshow(video[-1]) # Show the last frame.
    >>> imshow(video[1][0:10, 0:10]) # Show one corner of the second frame.

    >>> for frame in video[:]:
    ...    # Do something with every frame.

    >>> for frame in video[10:20]:
    ...    # Do something with frames 10-20.

    >>> for frame in video[[5, 7, 13]]:
    ...    # Do something with frames 5, 7, and 13.

    >>> frame_count = len(video) # Number of frames in video
    >>> frame_shape = video.frame_shape # Pixel dimensions of video
    """
    def __init__(self, path_spec, process_func=None, dtype=None,
                 as_grey=False, **kwargs):
        self.kwargs = kwargs
        self._is_zipfile = False
        self._zipfile = None
        self._get_files(path_spec)

        tmp = self.imread(self._filepaths[0], **self.kwargs)
        self._first_frame_shape = tmp.shape

        self._validate_process_func(process_func)
        self._as_grey(as_grey, process_func)

        if dtype is None:
            self._dtype = tmp.dtype
        else:
            self._dtype = dtype

    def close(self):
        if self._is_zipfile:
            self._zipfile.close()
        super(BaseImageSequence, self).close()

    def __del__(self):
        self.close()

    def imread(self, filename, **kwargs):
        if self._is_zipfile:
            file_handle = StringIO(self._zipfile.read(filename))
            return self._imread(file_handle, **kwargs)
        else:
            return self._imread(filename, **kwargs)

    def _get_files(self, path_spec):
        # deal with if input is _not_ a string
        if not isinstance(path_spec, six.string_types):
            # assume it is iterable and off we go!
            self._filepaths = sorted(list(path_spec), key=natural_keys)
            self._count = len(path_spec)
            return

        if zipfile.is_zipfile(path_spec):
            self._is_zipfile = True
            self.pathname = os.path.abspath(path_spec)
            self._zipfile = zipfile.ZipFile(path_spec, 'r')
            filepaths = [fn for fn in self._zipfile.namelist()
                         if fnmatch.fnmatch(fn, '*.*')]
            self._filepaths = sorted(filepaths, key=natural_keys)
            self._count = len(self._filepaths)
            return

        self.pathname = os.path.abspath(path_spec)  # used by __repr__
        if os.path.isdir(path_spec):
            warn("Loading ALL files in this directory. To ignore extraneous "
                 "files, use a pattern like 'path/to/images/*.png'",
                 UserWarning)
            directory = path_spec
            filenames = os.listdir(directory)
            make_full_path = lambda filename: (
                os.path.abspath(os.path.join(directory, filename)))
            filepaths = list(map(make_full_path, filenames))
        else:
            filepaths = glob.glob(path_spec)
        self._filepaths = sorted(filepaths, key=natural_keys)
        self._count = len(self._filepaths)

        # If there were no matches, this was probably a user typo.
        if self._count == 0:
            raise IOError("No files were found matching that path.")

    def get_frame(self, j):
        if j > self._count:
            raise ValueError("File does not contain this many frames")
        res = self.imread(self._filepaths[j], **self.kwargs)
        if res.dtype != self._dtype:
            res = res.astype(self._dtype)
        res = Frame(self.process_func(res), frame_no=j)
        return res

    def __len__(self):
        return self._count

    @property
    def frame_shape(self):
        return self._first_frame_shape

    @property
    def pixel_type(self):
        return self._dtype

    def __repr__(self):
        # May be overwritten by subclasses
        try:
            source = self.pathname
        except AttributeError:
            source = '(list of images)'
        return """<Frames>
Source: {pathname}
Length: {count} frames
Frame Shape: {w} x {h}
Pixel Datatype: {dtype}""".format(w=self.frame_shape[0],
                                  h=self.frame_shape[1],
                                  count=len(self),
                                  pathname=source,
                                  dtype=self.pixel_type)


class ImageSequence_skimage(BaseImageSequence):
    __doc__ = BaseImageSequence.__doc__
    _imread = skimage_imread


class ImageSequence_mpl(BaseImageSequence):
    __doc__ = BaseImageSequence.__doc__
    _imread = mpl_imread


class ImageSequence_pil(BaseImageSequence):
    __doc__ = BaseImageSequence.__doc__
    _imread = pil_imread


class ImageSequence_scipy(BaseImageSequence):
    __doc__ = BaseImageSequence.__doc__
    _imread = scipy_imread


class ImageSequence_tifffile(BaseImageSequence):
    __doc__ = BaseImageSequence.__doc__
    _imread = tifffile_imread


def filename_to_indices(filename, identifiers='tzc'):
    """ Find ocurrences of dimension indices (e.g. t001, z06, c2)
    in a filename and returns a list of indices.

    Parameters
    ----------
    filename : string
        filename to be searched for indices
    identifiers : string or list of strings, optional
        iterable of N strings preceding dimension indices, in that order

    Returns
    ---------
    list of int
        dimension indices. Elements default to 0 when index was not found.

    """
    escaped = [re.escape(a) for a in identifiers]
    dimensions = re.findall('(' + '|'.join(escaped) + r')(\d+)',
                            filename)
    if len(dimensions) > len(identifiers):
        dimensions = dimensions[-3:]
    order = [a[0] for a in dimensions]
    result = [0] * len(identifiers)
    for (i, col) in enumerate(identifiers):
        try:
            result[i] = int(dimensions[order.index(col)][1])
        except ValueError:
            result[i] = 0
    return result


class ImageSequenceND(FramesSequenceND, BaseImageSequence):
    """Read a directory of multi-indexed image files into an iterable that
    returns images as numpy arrays. By default, the extra dimensions are
    denoted with t, z, c.

    Parameters
    ----------
    path_spec : string or iterable of strings
        a directory or, safer, a pattern like path/to/images/*.png
        which will ignore extraneous files or a list of files to open
        in the order they should be loaded. When a path to a zipfile is
        specified, all files in the zipfile will be loaded. The filenames
        should contain the indices of T, Z and C, preceded by a dimension
        identifier such as: 'file_t001c05z32'.
    process_func : function, optional
        callable with signature `proc_img = process_func(img)`,
        which will be applied to the data from each frame.
    dtype : numpy datatype, optional
        Image arrays will be converted to this datatype.
    as_grey : boolean, optional
        Not implemented for 3D images.
    plugin : string, optional
        Passed on to skimage.io.imread if scikit-image is available.
        If scikit-image is not available, this will be ignored and a warning
        will be issued. Not available in combination with zipfiles.
    dim_identifiers : iterable of strings, optional
        N strings preceding dimension indices. Default 'tzc'. x and y are not
        allowed.

    Attributes
    ----------
    axes : list of strings
        List of all available axes
    ndim : int
        Number of image axes
    sizes : dict of int
        Dictionary with all axis sizes
    frame_shape : tuple of int
        Shape of frames that will be returned by get_frame
    iter_axes : iterable of strings
        This determines which axes will be iterated over by the FramesSequence.
        The last element in will iterate fastest. x and y are not allowed.
    bundle_axes : iterable of strings
        This determines which axes will be bundled into one Frame. The axes in
        the ndarray that is returned by get_frame have the same order as the
        order in this list. The last two elements have to be ['y', 'x'].
        Defaults to ['z', 'y', 'x'].
    default_coords: dict of int
        When a dimension is not present in both iter_axes and bundle_axes, the
        coordinate contained in this dictionary will be used.
    """
    def __init__(self, path_spec, process_func=None, dtype=None,
                 as_grey=False, plugin=None, dim_identifiers='tzc'):
        if as_grey:
            raise ValueError('As grey not supported for ND images')
        self.dim_identifiers = dim_identifiers
        super(ImageSequenceND, self).__init__(path_spec, process_func,
                                              dtype, as_grey, plugin)
        self._init_axis('y', self._first_frame_shape[0])
        self._init_axis('x', self._first_frame_shape[1])
        if 't' in self.axes:
            self.iter_axes = 't'  # iterate over t
        if 'z' in self.axes:
            self.bundle_axes = 'zyx'  # return z-stacks

    def _get_files(self, path_spec):
        super(ImageSequenceND, self)._get_files(path_spec)
        self._toc = np.array([filename_to_indices(f, self.dim_identifiers)
                              for f in self._filepaths])
        for n, name in enumerate(self.dim_identifiers):
            if np.all(self._toc[:, n] == 0):
                self._toc = np.delete(self._toc, n, axis=1)
            else:
                self._toc[:, n] = self._toc[:, n] - min(self._toc[:, n])
                self._init_axis(name, max(self._toc[:, n]) + 1)
        self._filepaths = np.array(self._filepaths)

    def get_frame(self, i):
        frame = super(ImageSequenceND, self).get_frame(i)
        return Frame(self.process_func(frame), frame_no=i)

    def get_frame_2D(self, **ind):
        row = [ind[name] for name in self.dim_identifiers]
        i = np.argwhere(np.all(self._toc == row, 1))[0, 0]
        res = self.imread(self._filepaths[i], **self.kwargs)
        if res.dtype != self._dtype:
            res = res.astype(self._dtype)
        return res

    def __repr__(self):
        try:
            source = self.pathname
        except AttributeError:
            source = '(list of images)'
        s = "<ImageSequenceND>\nSource: {0}\n".format(source)
        s += "Dimensions: {0}\n".format(self.ndim)
        for dim in self._sizes:
            s += "Dimension '{0}' size: {1}\n".format(dim, self._sizes[dim])
        s += """Pixel Datatype: {dtype}""".format(dtype=self.pixel_type)
        return s


def customize_image_sequence(imread_func, name=None):
    """Class factory for ImageSequence with customized image reader.

    Parameters
    ----------
    imread_func : callable
        image reader
    name : str or None
        name of class returned; if None, 'CustomImageSequence' is used.

    Returns
    -------
    type : a subclass of ImageSequence
        This subclass has its image-opening method, imread, overriden
        by the passed function.

    Example
    -------
    >>> # my_func accepts a filename and returns a numpy array
    >>> MyImageSequence = customize_image_sequence(my_func)
    >>> frames = MyImageSequence('path/to/my_weird_files*')
    """
    class CustomImageSequence(BaseImageSequence):
        def _imread(self, filename, **kwargs):
            return imread_func(filename, **kwargs)
    if name is not None:
        CustomImageSequence.__name__ = name
    return CustomImageSequence
