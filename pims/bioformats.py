from __future__ import (absolute_import, division, print_function)

import numpy as np

from pims.base_frames import FramesSequence
from pims.frame import Frame
from warnings import warn
import os

try:
    import jpype
except ImportError:
    jpype = None
    
LOCI_TOOLS_PATH = os.path.join(os.path.dirname(__file__),
                               'loci_tools.jar')

def available():
    return jpype is not None 


def download_jar(url=None, overwrite=False):
    from six.moves.urllib.request import urlretrieve
    if not overwrite and os.path.isfile(LOCI_TOOLS_PATH):
        raise IOError('File {} already exists, please backup the file or set '
                      'parameter `overwrite = True`'.format(LOCI_TOOLS_PATH))
    if url is None:
        url = 'http://downloads.openmicroscopy.org/bio-formats/5.1.0/artifacts/loci_tools.jar'
    urlretrieve(url, LOCI_TOOLS_PATH)
    print('Downloaded loci_tools.jar to {}'.format(LOCI_TOOLS_PATH))
    return LOCI_TOOLS_PATH


class MetadataRetrieve(object):
    """This class is an interface to loci.formats.meta.MetadataRetrieve. At
    initialization, it tests all the MetadataRetrieve functions and it only
    binds the ones that do not raise a java exception.

    Parameters
    ----------
    jmd: jpype._jclass.loci.formats.ome.OMEXMLMetadataImpl
        java MetadataStore, instanciated with:
            jmd = loci.formats.MetadataTools.createOMEXMLMetadata()
        and coupled to reader with `rdr.setMetadataStore(metadata)`

    Methods
    ----------
    <loci.formats.meta.MetadataRetrieve.function>(*args) : float or int or str
        see loci.formats.meta.MetadataRetrieve API on openmicroscopy.org
    """
    def __init__(self, md):
        def wrap_md(fn, name=None, paramcount=None, *args):
            if len(args) != paramcount:
                # raise sensible error for wrong number of arguments
                raise TypeError(('{0}() takes exactly {1} arguments ({2} ' +
                                 'given)').format(name, paramcount, len(args)))
            jw = fn(*args)
            if jw is None or jw == '':
                return None
            # convert value to int, float, or string
            jw = unicode(jw)
            try:  # deal with values hidden inside 'value[number]'
                temp = jw[jw.index('value[') + 6:]
                temp = temp[:temp.index(']')]
            except ValueError:
                pass  # do nothing when 'value[' or ']' were not found
            else:
                jw = temp
            try:
                return int(jw)
            except ValueError:
                try:
                    return float(jw)
                except ValueError:
                    return jw

        for name in dir(md):
            if (name[:3] != 'get') or (name in ['getRoot', 'getClass']):
                continue
            fn = getattr(md, name)
            for paramcount in range(5):
                try:
                    field = fn(*((0,) * paramcount))
                    if field is None:
                        continue
                    # If there is no exception, wrap the function and bind.
                    def fnw(fn1=fn, naame=name, paramcount=paramcount):
                        return (lambda *args: wrap_md(fn1, naame,
                                                      paramcount, *args))
                    fnw = fnw()
                    fnw.__doc__ = ('loci.formats.meta.MetadataRetrieve.'
                                   + name + ' wrapped\nby JPype and an '
                                   'additional automatic typeconversion.\n\n')
                    setattr(self, name[3:], fnw)
                    continue
                except:
                    # function is not supported by this specific reader
                    pass

    def __repr__(self):
        listing = list(filter(lambda x: x[:2] != '__', dir(self)))
        return '<MetadataRetrieve> Available loci.formats.meta.' + \
               'MetadataRetrieve functions: ' + ', '.join(listing)


class BioformatsReaderRaw(FramesSequence):
    """Reads 2D images from the frames of a file supported by bioformats into
    an iterable object that returns images as numpy arrays.

    Parameters
    ----------
    filename : str
    process_func : function, optional
        callable with signature `proc_img = process_func(img)`,
        which will be applied to the data from each frame
    dtype : numpy datatype, optional
        Image arrays will be converted to this datatype.
    as_grey : boolean, optional
        Convert color images to greyscale. False by default.
        May not be used in conjunction with process_func.
    meta : bool, optional
        When true, the metadata object is generated. Takes time to build.
    java_memory : str, optional
        The max heap size of the java virtual machine, default 512m. As soon as
        the virtual machine is started, python has to be restarted to change
        the max heap size.
    series: int, optional
        Active image series index, defaults to 0. Changeable via the `series`
        property.


    Attributes
    ----------
    __len__ : int
        Number of planes in active series (= size Z*C*T)
    metadata : MetadataRetrieve object
        This object contains loci.formats.meta.MetadataRetrieve functions for
        metadata reading. Not available when meta == False.
    frame_metadata : dict
        This dictionary sets which metadata fields are read and passed into the
        Frame.metadata field obtained by get_frame. This will only work if
        meta=True. Only MetadataRetrieve methods with signature (series, plane)
        will be accepted.
    sizes : dict of int
        Number of series and for active series: X, Y, Z, C, T sizes
    frame_shape : tuple of int
        Shape of the image (y, x) or (y, x, 3) or (y, x, 4)
    series : int
        active series that is read by get_frame. Writeable.
    channel : int or list of int
        channel(s) that are read by get_frame. Writeable.
    pixel_type : numpy.dtype
        numpy datatype of pixels
    isRGB : boolean
        True if the image is an RGB image

    Methods
    ----------
    get_frame(plane) : pims.frame object
        returns 2D image in active series. See notes for metadata content.
    get_index(z, c, t) : int
        returns the imageindex in the current series with given coordinates
    get_metadata_raw(form) : dict or list or string
        returns the raw metadata from the file. Form defaults to 'dict', other
        options are 'list' and 'string'.
    close() :
        closes the reader

    Examples
    ----------
    >>> frames.metadata.PlaneDeltaT(0, 50)
    ...    # evaluates loci.formats.meta.MetadataRetrieve.getPlaneDeltaT(0, 50)

    Notes
    ----------
    It is not necessary to shutdown the JVM at end. This will be automatically
    done when JPype is unloaded at python exit.

    Dependencies:
    http://sourceforge.net/projects/jpype/files/JPype/

    Tested with files from http://loci.wisc.edu/software/sample-data
    Working for:
        Zeiss Laser Scanning Microscopy, IPLab, Gatan Digital Micrograph,
        Image-Pro sequence, Leica, Image-Pro workspace, Nikon NIS-Elements ND2,
        Image Cytometry Standard, QuickTime movie
    Not (fully) working for:
        Olympus Fluoview TIFF, Bio-Rad PIC, Openlab LIFF, PerkinElmer,
        Andor Bio-imaging Division TIFF, Leica LIF, BIo-Rad PIC

    For files larger than 4GB, 64 bits Python is required

    Metadata automatically provided by get_frame, as dictionary:
        plane: index of image in series
        series: series index
        indexC, indexZ, indexT: indexes of C, Z, T
        X, Y, Z: physical location of the image in microns
        T: timestamp of the image in seconds
    """

    @classmethod
    def class_exts(cls):
        try:
            return {'.lsm', '.ipl', '.dm3', '.seq', '.nd2', '.ics', '.ids',
                    '.mov', '.ipw', '.tif', '.tiff', '.jpg', '.bmp', '.lif'}
        except AttributeError:
            return {}

    class_priority = 2

    def __init__(self, filename, process_func=None, dtype=None,
                 as_grey=False, meta=True, java_memory='512m', series=0):
        # Make sure that file exists before starting java
        if not os.path.isfile(filename):
            raise IOError('The file "{}" does not exist.'.format(filename))

        if not os.path.isfile(LOCI_TOOLS_PATH):
            print('loci_tools.jar not found, downloading')
            download_jar()

        # Start java VM and initialize logger (globally)
        if not jpype.isJVMStarted():
            jpype.startJVM(jpype.getDefaultJVMPath(), '-ea',
                           '-Djava.class.path=' + LOCI_TOOLS_PATH,
                           '-Xmx' + java_memory)
            log4j = jpype.JPackage('org.apache.log4j')
            log4j.BasicConfigurator.configure()
            log4j_logger = log4j.Logger.getRootLogger()
            log4j_logger.setLevel(log4j.Level.ERROR)

        if not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()

        loci = jpype.JPackage('loci')

        # Initialize reader and metadata
        self.filename = str(filename)
        self.rdr = loci.formats.ChannelSeparator(loci.formats.ChannelFiller())
        if meta:
            self._metadata = loci.formats.MetadataTools.createOMEXMLMetadata()
            self.rdr.setMetadataStore(self._metadata)
        self.rdr.setId(self.filename)

        FormatTools = loci.formats.FormatTools
        self._dtype_dict = {FormatTools.INT8: 'i1',
                            FormatTools.UINT8: 'u1',
                            FormatTools.INT16: 'i2',
                            FormatTools.UINT16: 'u2',
                            FormatTools.INT32: 'i4',
                            FormatTools.UINT32: 'u4',
                            FormatTools.FLOAT: 'f4',
                            FormatTools.DOUBLE: 'f8'}

        # Set the correct series and initialize the sizes
        self._size_series = self.rdr.getSeriesCount()
        if series >= self._size_series or series < 0:
            self.rdr.close()
            raise IndexError('Series index out of bounds.')
        self._series = series
        self._forced_dtype = dtype
        self._change_series()

        # Define a process func, if applicable
        # TODO: check if as grey works with series with different dimensions
        self._validate_process_func(process_func)
        self._as_grey(as_grey, process_func)

        # Define the names of the standard per frame metadata.
        self.frame_metadata = {}
        if meta:
            self.metadata = MetadataRetrieve(self._metadata)
            if hasattr(self.metadata, 'PlaneTheT'):
                self.frame_metadata['indexT'] = 'PlaneTheT'
            if hasattr(self.metadata, 'PlaneTheZ'):
                self.frame_metadata['indexZ'] = 'PlaneTheZ'
            if hasattr(self.metadata, 'PlaneTheC'):
                self.frame_metadata['indexC'] = 'PlaneTheC'
            if hasattr(self.metadata, 'PlaneDeltaT'):
                self.frame_metadata['T'] = 'PlaneDeltaT'
            if hasattr(self.metadata, 'PlanePositionX'):
                self.frame_metadata['X'] = 'PlanePositionX'
            if hasattr(self.metadata, 'PlanePositionY'):
                self.frame_metadata['Y'] = 'PlanePositionY'
            if hasattr(self.metadata, 'PlanePositionZ'):
                self.frame_metadata['Z'] = 'PlanePositionZ'

    def _change_series(self):
        """Changes series and rereads dtype, sizes and pixelsizes.
        When pixelsize Y is not found, pixels are assumed to be square.
        """
        series = self._series
        self.rdr.setSeries(series)
        self.isRGB = self.rdr.isRGB()
        self._sizeRGB = self.rdr.getRGBChannelCount()
        self._isInterleaved = self.rdr.isInterleaved()
        self._sizeT = self.rdr.getSizeT()
        self._sizeZ = self.rdr.getSizeZ()
        self._sizeY = self.rdr.getSizeY()
        self._sizeX = self.rdr.getSizeX()
        if self.isRGB:
            self._sizeC = 1
            self._first_frame_shape = (self._sizeY, self._sizeX, self._sizeRGB)
        else:
            self._sizeC = self.rdr.getSizeC()
            self._first_frame_shape = (self._sizeY, self._sizeX)
        self._planes = self.rdr.getImageCount()

        # determine pixel type
        self._source_dtype = self._dtype_dict[self.rdr.getPixelType()]
        if self.rdr.isLittleEndian():
            self._source_dtype = '<' + self._source_dtype
        else:
            self._source_dtype = '>' + self._source_dtype

        if self._forced_dtype is None:
            self._pixel_type = self._source_dtype
        else:
            self._pixel_type = self._forced_dtype

    def __len__(self):
        return self._planes

    def close(self):
        self.rdr.close()

    def __del__(self):
        self.close()

    @property
    def sizes(self):
        return {'series': self._size_series, 'X': self._sizeX,
                'Y': self._sizeY, 'Z': self._sizeZ, 'C': self._sizeC,
                'T': self._sizeT}

    @property
    def series(self):
        return self._series

    @series.setter
    def series(self, value):
        if value >= self._size_series or value < 0:
            raise IndexError('Series index out of bounds.')
        else:
            if value != self._series:
                self._series = value
                self._change_series()

    @property
    def frame_shape(self):
        return self._first_frame_shape

    def get_frame(self, j):
        """Returns image in current series specific as a Frame object with
        specified frame_no and metadata attributes.
        """
        im, metadata = self._get_frame(self.series, j)
        return Frame(self.process_func(im), frame_no=j, metadata=metadata)

    def _get_frame(self, series, j):
        """Actual reader, returns image as 2D numpy array and metadata as
        dict. It changes the series property if necessary.
        """
        self.series = series  # use property setter & error reporting

        # see https://github.com/originell/jpype/issues/71
        Jbyte = self.rdr.openBytes(j)
        Jstr = jpype._jclass.JClass('java.lang.String')(Jbyte, 'ISO-8859-1')
        Pbyte = np.array(np.frombuffer(Jstr.toString(), dtype='uint16'),
                         dtype='uint8')
        im = np.frombuffer(buffer(Pbyte), dtype=self._source_dtype)
        if self.isRGB:
            if self._isInterleaved:
                im.shape = (self._sizeY, self._sizeX, self._sizeRGB)
            else:
                im.shape = (self._sizeRGB, self._sizeY, self._sizeX)
                im = im.transpose(1, 2, 0)  # put RGB in inner dimension
        else:
            im.shape = (self._sizeY, self._sizeX)

        im = im.astype(self._pixel_type, copy=False)

        metadata = {'frame': j, 'series': series}
        for key, method in self.frame_metadata.iteritems():
            metadata[key] = getattr(self.metadata, method)(series, j)

        return im, metadata

    def get_metadata_raw(self, form='dict'):
        hashtable = self.rdr.getGlobalMetadata()
        if form == 'dict':
            result = {key: unicode(hashtable[key]) for key in hashtable.keys()}
        elif form == 'list':
            result = [key + ': ' + unicode(hashtable[key])
                      for key in hashtable.keys()]
        elif form == 'string':
            result = ''
            for key in hashtable.keys():
                result += key + ': ' + unicode(hashtable[key]) + '\n'
        return result

    def get_index(self, z, c, t):
        return self.rdr.getIndex(z, c, t)

    @property
    def reader_class_name(self):
        return self.rdr.getFormat()

    @property
    def pixel_type(self):
        return self._pixel_type

    def __repr__(self):
        result = """<Frames>
Source: {filename}
Series: {mp}, active: {mpa}
Framecount: {count} frames
Colordepth: {c}
Zstack depth: {z}
Time frames: {t}
Frame Shape: {w} x {h}""".format(w=self._sizeX,
                                 h=self._sizeY,
                                 mp=self._size_series,
                                 mpa=self._series,
                                 count=self._planes,
                                 z=self._sizeZ,
                                 t=self._sizeT,
                                 c=self._sizeC,
                                 filename=self.filename)
        return result


class BioformatsReader(BioformatsReaderRaw):
    """Reads multidimensional images from the frames of a file supported by
    bioformats into an iterable object that returns images as numpy arrays
    indexed by t. The numpy array dimensions are CZYX, ZYX, CYX or YX,
    depending on the contents of the file and the setting of the channel
    property.

    Parameters
    ----------
    filename: str
    process_func : function, optional
        callable with signature `proc_img = process_func(img)`,
        which will be applied to the data from each frame
    dtype : numpy datatype, optional
        Image arrays will be converted to this datatype.
    as_grey : boolean, optional
        Convert color images to greyscale. False by default.
        May not be used in conjunction with process_func.
    meta: bool, optional
        When true, the metadata object is generated. Takes time to build.
    java_memory : str, optional
        The max heap size of the java virtual machine, default 512m. As soon as
        the virtual machine is started, python has to be restarted to change
        the max heap size.
    series: int, optional
        Active image series index, defaults to 0. Changeable via the `series`
        property.
    C : int or list of int
        Channel(s) that are read by get_frame. Changeable via the `channel`
        property. Defaults to all channels.

    Attributes
    ----------
    __len__ : int
        Number of timepoints in active series (equal to sizes['T'])
    metadata : MetadataRetrieve object
        This object contains loci.formats.meta.MetadataRetrieve functions for
        metadata reading. Not available when meta == False.
    frame_metadata : dict
        This dictionary sets which metadata fields are read and passed into the
        Frame.metadata field obtained by get_frame. This will only work if
        meta=True. Only MetadataRetrieve methods with signature (series, plane)
        will be accepted.
    sizes : dict of int
        Number of series and for active series: X, Y, Z, C, T sizes
    frame_shape : tuple of int
        Shape of the image (y, x) or (y, x, 3) or (y, x, 4)
    channel : int or iterable of int
        channel(s) that are read by get_frame. Writeable.
    series : int
        active series that is read by get_frame. Writeable.
    channel : int or list of int
        channel(s) that are read by get_frame. Writeable.
    pixel_type : numpy.dtype
        numpy datatype of pixels
    java_log : string
        contains everything printed to java system.out and system.err
    isRGB : boolean
        True if the image is an RGB image
    channel_RGB : list of rgb values (floats)
        The rgb values of all active channels set by the channels property. If
        not supported by the underlying reader, this returns an empty list

    Methods
    ----------
    get_frame(plane) : pims.frame object
        returns 3D image in active series. See notes for metadata content.
    get_index(z, c, t) : int
        returns the imageindex in the current series with given coordinates
    get_metadata_raw(form) : dict or list or string
        returns the raw metadata from the file. Form defaults to 'dict', other
        options are 'list' and 'string'.
    close() :
        closes the reader

    Examples
    ----------
    >>> frames.metadata.PlaneDeltaT(0, 50)
    ...    # evaluates loci.formats.meta.MetadataRetrieve.getPlaneDeltaT(0, 50)

    Notes
    ----------
    It is not necessary to shutdown the JVM at end. It will be automatically
    done when JPype is unloaded at python exit.

    Dependencies:
    http://sourceforge.net/projects/jpype/files/JPype/

    Tested with files from http://loci.wisc.edu/software/sample-data
    Working for:
        Zeiss Laser Scanning Microscopy, IPLab, Gatan Digital Micrograph,
        Image-Pro sequence, Leica, Image-Pro workspace, Nikon NIS-Elements ND2,
        Image Cytometry Standard, QuickTime movie
    Not (fully) working for:
        Olympus Fluoview TIFF, Bio-Rad PIC, Openlab LIFF, PerkinElmer,
        Andor Bio-imaging Division TIFF, Leica LIF, BIo-Rad PIC

    For files larger than 4GB, 64 bits Python is required

    Metadata automatically provided by get_frame, as dictionary:
        plane: index of image in series
        series: series index
        indexC, indexZ, indexT: indexes of C, Z, T
        X, Y, Z: physical location of the image in microns
        T: timestamp of the image in seconds
    """
    class_priority = 5

    def __init__(self, filename, process_func=None, dtype=None, as_grey=False,
                 meta=True, java_memory='512m', series=0, C=None):
        self._channel = C
        super(BioformatsReader, self).__init__(filename, process_func, dtype,
                                               as_grey, meta, java_memory,
                                               series)
        rgbvalues = []
        try:
            for c in range(self._sizeC):
                rgba = self.metadata.ChannelColor(self.series, c)
                rgbvalues.append([(rgba >> 24 & 255) / 255,
                                  (rgba >> 16 & 255) / 255,
                                  (rgba >> 8 & 255) / 255])
        except:  # a lot could happen, use catch all here
            self.channel_RGB_all = []
        else:
            self.channel_RGB_all = rgbvalues

    def __len__(self):
        return self._sizeT

    @property
    def channel(self):
        if self.isRGB:
            raise AttributeError('Channel index not applicable to RGB files.')
        return self._channel

    @channel.setter
    def channel(self, value):
        if self.isRGB:
            raise AttributeError('Channel index not applicable to RGB files.')
        try:
            channel = tuple(value)
        except TypeError:
            channel = (value,)
        if np.any(np.greater_equal(channel, self._sizeC)) or \
           np.any(np.less(channel, 0)):
            raise IndexError('Channel index should be positive and less ' +
                             'than the number of channels ' +
                             '({})'.format(self._sizeC + 1))
        self._channel = channel
 
    @property
    def channel_RGB(self):
        if len(self.channel_RGB_all) == self._sizeC:
            return [self.channel_RGB_all[c] for c in self.channel]

    def _change_series(self):
        super(BioformatsReader, self)._change_series()

        if self.isRGB:
            self._channel = (0,)
            self.channel_RGB = []
        elif self._channel is None:
            self.channel = tuple(range(self._sizeC))
        else:
            try:
                self.channel = self._channel
            except IndexError:
                warn("Channel index out of range. Resetting to all channels.",
                     UserWarning)
                self.channel = tuple(range(self._sizeC))

    def get_frame(self, t):
        """Returns image in current series at specified T index. The image is
        wrapped in a Frame object with specified frame_no and metadata."""
        shape = (len(self._channel), self._sizeZ, self._sizeY, self._sizeX)
        if self.isRGB:
            shape = shape + (self._sizeRGB,)
        imlist = np.zeros(shape, dtype=self.pixel_type)

        mdlist = []
        for (Nc, c) in enumerate(self._channel):
            for z in range(self._sizeZ):
                index = self.get_index(z, c, t)
                imlist[Nc, z], md = self._get_frame(self.series, index)
                mdlist.append(md)

        keys = mdlist[0].keys()
        metadata = {}
        for k in keys:
            metadata[k] = [row[k] for row in mdlist]
            if metadata[k][1:] == metadata[k][:-1]:
                metadata[k] = metadata[k][0]

        if self.channel_RGB is not None:
            metadata['colors'] = self.channel_RGB

        return Frame(self.process_func(imlist.squeeze()), frame_no=t,
                     metadata=metadata)
