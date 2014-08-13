from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six

# has to be here for API stuff
from pims.image_sequence import ImageSequence  # noqa


def not_available(requirement):
    def raiser(*args, **kwargs):
        raise ImportError(
            "This reader requires {0}.".format(requirement))
    return raiser

try:
    import pims.pyav_reader
    if pims.pyav_reader.available():
        Video = pims.pyav_reader.PyAVVideoReader
    else:
        raise ImportError()
except (ImportError, IOError):
    Video = not_available("PyAV")

try:
    import pims.tiff_stack
    from pims.tiff_stack import (TiffStack_pil, TiffStack_libtiff,
                                 TiffStack_tifffile)
    if pims.tiff_stack.tifffile_available():
        TiffStack = TiffStack_tifffile
    elif pims.tiff_stack.libtiff_available():
        TiffStack = TiffStack_libtiff
    elif pims.tiff_stack.PIL_available():
        TiffStack = TiffStack_pil
    else:
        raise ImportError()
except ImportError:
    TiffStack = not_available("tifffile or libtiff or PIL/PILLOW")

try:
    import pims.zvi_reader
    if pims.zvi_reader.ole_available():
        ZVI = pims.zvi_reader.ZVI
    else:
        raise ImportError()
except ImportError:
    ZVI = not_available("OleFileIO and PIL/Pillow")
