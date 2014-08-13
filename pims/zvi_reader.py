from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six

import re
import numpy as np
from pims.frame import Frame

try:
    from PIL import Image  # should work with PIL or PILLOW
except ImportError:
    Image = None

try:
    from OleFileIO_PL import OleFileIO
except ImportError:
    OleFileIO = None


def ole_available():
    return (OleFileIO is not None) and (Image is not None)


from pims.base_frames import FramesSequence

_dtype_map = {4: np.uint8,
              8: np.uint8,
              16: np.uint16}


class ZVI(FramesSequence):
    """Read ZVI image sequences (single files containing many images) into an
    iterable object that returns images as numpy arrays.

    WARNING: This code is alpha code. The image size and data type are
    hard-coded, and not ready for general use.

    This reader, which relies on OleFileIO and PIL/Pillow, is tested on
    Zeiss AxioVision ZVI files. It should also read Olympus FluoView OIB files
    and others based on the legacy OLE file format.

    Parameters
    ----------
    filename : string
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
    >>> video = ZVI('filename.zvi')
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
    @classmethod
    def class_exts(cls):
        # TODO extend this set to match reality
        return {'zvi'} | super(OleImages, cls).class_exts()

    def __init__(self, filename, process_func=None, dtype=None,
                 as_grey=False):
        self._filename = filename
        self._ole = OleFileIO(self._filename)
        self._streams = self._ole.listdir()

        if dtype is not None:
            raise ValueError("This reader ignored dtype and used uint16.")
        self._dtype = np.dtype('<i16')

        self._im_sz = (656, 492)  # TODO

        self._toc = []
        for stream in self._streams:
            if stream[0] != 'Image':
                continue
            m = re.match('Item\((\d+)\)', stream[1])
            if m is None:
                continue
            self._toc.append(int(m.group(1)))
        self._len = max(self._toc)
        # self._toc is not used hereafter, but it could be.

        self._validate_process_func(process_func)
        self._as_grey(as_grey, process_func)

    def get_frame(self, j):
        stream_label = ['Image', 'Item({0})'.format(j), 'Contents']
        data = self._ole.openstream(stream_label).read()
        img = Image.fromstring('I;16L', self._im_sz, data)
        # Mysteriously, the image comes in rolled by 162 pixels! Roll it back.
        arr = np.roll(np.asarray(img, dtype=self._dtype), -162)
        return Frame(self.process_func(arr), frame_no=j)

    @property
    def pixel_type(self):
        return self._dtype

    @property
    def frame_shape(self):
        return self._im_sz

    def __len__(self):
        return self._len

    def __repr__(self):
        # May be overwritten by subclasses
        return """<Frames>
Source: {filename}
Length: {count} frames
Frame Shape: {w} x {h}
Pixel Datatype: {dtype}""".format(w=self.frame_shape[0],
                                  h=self.frame_shape[1],
                                  count=len(self),
                                  filename=self._filename,
                                  dtype=self.pixel_type)
