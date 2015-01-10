from __future__ import (absolute_import, division, print_function)

import numpy as np

from pims.base_frames import FramesSequence
from pims.frame import Frame


try:
    import javabridge
except ImportError:
    javabridge = None

try:
    import bioformats
except ImportError:
    bioformats = None

try:
    from pandas import DataFrame
except ImportError:
    DataFrame = None


def available():
    try:
        import javabridge
        import bioformats
    except ImportError:
        return False
    else:
        return True


class MetadataRetrieve():
    """This class is an interface to loci.formats.meta.MetadataRetrieve. At
    initialization, it tests all the MetadataRetrieve functions and it only
    binds the ones that do not raise a java exception.

    Parameters
    ----------
    jmd: _javabridge.JB_Object
        java MetadataStore, retrieved with reader.rdr.getMetadataStore()
    log: _javabridge.JB_Object
        java OutputStream to which java system.err and system.out are printing.

    Methods
    ----------
    <loci.formats.meta.MetadataRetrieve.function>(*args) : float or int or str
        see http://downloads.openmicroscopy.org/bio-formats/5.0.6/api/loci/
                                             formats/meta/MetadataRetrieve.html
    """
    def __init__(self, jmd, log):
        jmd = javabridge.JWrapper(jmd)

        def wrap_md(fn, name=None, paramcount=None, *args):
            if len(args) != paramcount:
                # raise sensible error for wrong number of arguments
                raise TypeError(('{0}() takes exactly {1} arguments ({2} ' +
                                 'given)').format(name, paramcount, len(args)))
            try:
                jw = fn(*args)
            except javabridge.JavaException as e:
                print(javabridge.to_string(log))
                javabridge.call(log, 'reset', '()V')
                raise e
            if jw is None or jw == '':
                return None
            # convert value to int, float, or string
            jw = str(jw)
            try:
                return int(jw)
            except ValueError:
                try:
                    return float(jw)
                except ValueError:
                    return jw

        env = javabridge.get_env()
        for name, method in jmd.methods.iteritems():
            if name[:3] == 'get':
                if name in ['getRoot', 'getClass']:
                    continue
                params = env.get_object_array_elements(method[0].getParameterTypes())
                try:
                    fn = getattr(jmd, name)
                    field = fn(*((0,) * len(params)))
                    # If there is no exception, wrap the function and bind.
                    def fnw(fn1=fn, naame=name, paramcount=len(params)):
                        return (lambda *args: wrap_md(fn1, naame,
                                                      paramcount, *args))
                    fnw = fnw()
                    fnw.__doc__ = fn.__doc__
                    setattr(self, name, fnw)
                except javabridge.JavaException:
                    # function is not supported by this specific reader
                    pass


class BioformatsReader2D(FramesSequence):
    """Reads 2D images from the frames of a file supported by bioformats into an
    iterable object that returns images as numpy arrays.

    Parameters
    ----------
    filename: str
    series: int, optional
        Active image series index, defaults to 0. Changeable via the `series`
        property.
    process_func: function, optional
        callable with signature `proc_img = process_func(img)`,
        which will be applied to the data from each frame
    dtype: numpy.dtype, optional
        unused
    as_grey: bool, optional
        unused

    Attributes
    ----------
    __len__ : int
        Number of planes in active series (= size Z*C*T)
    metadata : MetadataRetrieve object
        This object contains loci.formats.meta.MetadataRetrieve functions for
        metadata reading.
    sizes : dict of int
        Number of series and for active series: X, Y, Z, C, T sizes
    frame_shape : tuple of int
        Sizes in pixels in X, Y. Equal to (sizes['X'], sizes['Y'])
    pixelsizes : dict of float
        Physical pixelsizes in X, Y, Z (in microns)
    series : int
        active series that is read by get_frame. Writeable.
    channel : int or list of int
        channel(s) that are read by get_frame. Writeable.
    pixel_type : numpy.dtype
        numpy datatype of pixels
    reader_class_name : string
        classname of bioformats imagereader (loci.formats.in.*)
    java_log : string
        contains everything printed to java system.out and system.err
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
    get_metadata_xml() : string
        returns the metadata in xml format
    get_metadata_omexml() : bioformats.OMEXML object
        parses the xml metadata to an omexml object
    close(is_last) :
        closes the reader. When is_last is true, java VM is stopped. Be sure
        to do that only at the last image, because the VM cannot be restarted
        unless you restart python console. The same as pims.kill_vm()

    Examples
    ----------
    >>> frames.metadata.getPlaneDeltaT(0, 50)
    ...    # evaluates loci.formats.meta.MetadataRetrieve.getPlaneDeltaT(0, 50)

    Notes
    ----------
    Be sure to kill the java VM with pims.kill_vm() the end of the day. It
    cannot be restarted from the same python console, however. You can also
    kill the vm by calling frame.close(is_last=True).

    Dependencies:
    https://github.com/CellProfiler/python-bioformats
    https://github.com/CellProfiler/python-javabridge
    or (windows compiled) http://www.lfd.uci.edu/~gohlke/pythonlibs/#javabridge

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
            return set(bioformats.READABLE_FORMATS)
        except AttributeError:
            return {}

    class_priority = 2

    def __init__(self, filename, series=0, process_func=None, dtype=None,
                 as_grey=False):
        if dtype is not None:
            raise NotImplementedError('This reader does not support ' +
                                      'typecasting')
        self.filename = str(filename)
        self._series = series
        self._validate_process_func(process_func)
        self._initializereader()
        self._change_series()

    def _initializereader(self):
        """Starts java VM, java logger, creates reader and metadata fields
        """
        if not javabridge._javabridge.get_vm().is_active():
            javabridge.start_vm(class_path=bioformats.JARS,
                                max_heap_size='512m')
        self._java_log = javabridge.run_script("""
                org.apache.log4j.BasicConfigurator.configure();
                log4j_logger = org.apache.log4j.Logger.getRootLogger();
                log4j_logger.setLevel(org.apache.log4j.Level.WARN);
                java_out = new java.io.ByteArrayOutputStream();
                out_printstream = new java.io.PrintStream(java_out);
                java.lang.System.setOut(out_printstream);
                java.lang.System.setErr(out_printstream);
                java_out;""")
        javabridge.attach()
        self._reader = bioformats.get_image_reader(self.filename,
                                                   self.filename)
        self.metadata = MetadataRetrieve(self._reader.rdr.getMetadataStore(),
                                         self._java_log)
        javabridge.call(self._java_log, 'reset', '()V')  # reset the java log
        self._size_series = self._reader.rdr.getSeriesCount()
        self._metadatacolumns = ['plane', 'series', 'indexC', 'indexZ',
                                 'indexT', 'X', 'Y', 'Z', 'T']

    def _change_series(self):
        """Changes series and rereads dtype, sizes and pixelsizes.
        When pixelsize Y is not found, pixels are assumed to be square.
        """
        series = self._series
        self._reader.rdr.setSeries(series)
        self.isRGB = self._reader.rdr.isRGB()

        # make use of built-in methods of bioformats to determine numpy dtype
        im, md = self._get_frame_2D(series, 0)
        self._pixel_type = im.dtype

        self._sizeC = self._reader.rdr.getSizeC()
        self._sizeT = self._reader.rdr.getSizeT()
        self._sizeZ = self._reader.rdr.getSizeZ()
        self._sizeY = self._reader.rdr.getSizeY()
        self._sizeX = self._reader.rdr.getSizeX()
        self._planes = self._reader.rdr.getImageCount()
        self._pixelX = self.metadata.getPixelsPhysicalSizeX(series)
        self._pixelY = self.metadata.getPixelsPhysicalSizeY(series)
        self._pixelZ = self.metadata.getPixelsPhysicalSizeZ(series)
        if self._pixelY is None:
            self._pixelY = self._pixelX

    def __len__(self):
        return self._planes

    def close(self, is_last=False):
        bioformats.release_image_reader(self.filename)
        javabridge.detach()
        if is_last:
            javabridge.kill_vm()

    @property
    def pixelsizes(self):
        return {'X': self._pixelX, 'Y': self._pixelY, 'Z': self._pixelZ}

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
        if value >= self._size_series:
            raise IndexError('Series index out of bounds.')
        else:
            if value != self._series:
                self._series = value
                self._change_series()

    @property
    def frame_shape(self):
        return self._sizeX, self._sizeY

    def get_frame(self, j):
        """Wrapper for _get_frame, additionally applies the process_func and
        converts the numpy array and metadata to a Frame object.
        """
        im, metadata = self._get_frame(self.series, j)
        im = self.process_func(im)
        return Frame(im, frame_no=j, metadata=metadata)

    def _get_frame(self, series, j):
        """Returns image as 2D numpy array and metadata as dictionary.
        """
        im, metadata = self._get_frame_2D(series, j)
        metadataproc = dict(zip(self._metadatacolumns, metadata))
        return im, metadataproc

    def _get_frame_2D(self, series, j):
        """Actual reader, returns image as 2D numpy array and metadata as tuple.
        """
        im = self._reader.read(series=series, index=j, rescale=False)

        try:
            metadata = (j,
                        series,
                        self.metadata.getPlaneTheC(series, j),
                        self.metadata.getPlaneTheZ(series, j),
                        self.metadata.getPlaneTheT(series, j),
                        self.metadata.getPlanePositionX(series, j),
                        self.metadata.getPlanePositionY(series, j),
                        self.metadata.getPlanePositionZ(series, j),
                        self.metadata.getPlaneDeltaT(series, j))
        except AttributeError:
            metadata = (j, series, 0, 0, 0, 0, 0, 0, 0)

        return im, metadata

    def get_metadata_xml(self):
        # bioformats.get_omexml_metadata opens and closes a new reader
        return bioformats.get_omexml_metadata(self.filename)

    def get_metadata_omexml(self):
        return bioformats.OMEXML(self.get_metadata_xml())

    def get_metadata_raw(self, form='dict'):
        # code based on javabridge.jutil.to_string,
        # .jdictionary_to_string_dictionary and .jenumeration_to_string_list
        # addition is that it deals with UnicodeErrors
        def to_string(jobject):
            if not isinstance(jobject, javabridge.jutil._javabridge.JB_Object):
                try:
                    return str(jobject)
                except UnicodeError:
                    return jobject
            return javabridge.jutil.call(jobject, 'toString',
                                         '()Ljava/lang/String;')
        hashtable = self._reader.rdr.getMetadata()
        jhashtable = javabridge.jutil.get_dictionary_wrapper(hashtable)
        jenumeration = javabridge.jutil.get_enumeration_wrapper(jhashtable.keys())
        keys = []
        while jenumeration.hasMoreElements():
            keys.append(jenumeration.nextElement())
        if form == 'dict':
            result = {}
            for key in keys:
                result[key] = to_string(jhashtable.get(key))
        elif form == 'list':
            result = []
            for key in keys:
                result.append(key + ': ' + to_string(jhashtable.get(key)))
        elif form == 'string':
            result = ''
            for key in keys:
                result += key + ': ' + to_string(jhashtable.get(key)) + '\n'
        return result

    def get_index(self, z, c, t):
        return self._reader.rdr.getIndex(z, c, t)

    @property
    def java_log(self):
        return javabridge.to_string(self._java_log)

    @property
    def reader_class_name(self):
        return self._reader.rdr.get_class_name()

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


class BioformatsReader3D(BioformatsReader2D):
    """Reads 3D images from the frames of a file supported by bioformats into an
    iterable object that returns images as numpy arrays, indexed by T index.

    Parameters
    ----------
    filename: str
    series: int, optional
        Active image series index, defaults to 0. Changeable via the `series`
        property.
    C : int or list of int
        Channel(s) that are read by get_frame. Changeable via the `channel`
        property.
    process_func: function, optional
        callable with signature `proc_img = process_func(img)`,
        which will be applied to the data from each frame
    dtype: numpy.dtype, optional
        unused
    as_grey: bool, optional
        unused

    Attributes
    ----------
    __len__ : int
        Number of timepoints in active series (equal to sizes['T'])
    metadata : MetadataRetrieve object
        This object contains loci.formats.meta.MetadataRetrieve functions for
        metadata reading.
    sizes : dict of int
        Number of series and for active series: X, Y, Z, C, T sizes
    frame_shape : tuple of int
        Sizes in pixels in X, Y. Equal to (sizes['X'], sizes['Y'])
    pixelsizes : dict of float
        Physical pixelsizes in X, Y, Z (in microns)
    channel : int or iterable of int
        channel(s) that are read by get_frame. Writeable.
    series : int
        active series that is read by get_frame. Writeable.
    channel : int or list of int
        channel(s) that are read by get_frame. Writeable.
    pixel_type : numpy.dtype
        numpy datatype of pixels
    reader_class_name : string
        classname of bioformats imagereader (loci.formats.in.*)
    java_log : string
        contains everything printed to java system.out and system.err
    isRGB : boolean
        True if the image is an RGB image

    Methods
    ----------
    get_frame(plane) : pims.frame object
        returns 3D image in active series. See notes for metadata content.
    get_index(z, c, t) : int
        returns the imageindex in the current series with given coordinates
    get_metadata_raw(form) : dict or list or string
        returns the raw metadata from the file. Form defaults to 'dict', other
        options are 'list' and 'string'.
    get_metadata_xml() : string
        returns the metadata in xml format
    get_metadata_omexml() : bioformats.OMEXML object
        parses the xml metadata to an omexml object
    close(is_last) :
        closes the reader. When is_last is true, java VM is stopped. Be sure
        to do that only at the last image, because the VM cannot be restarted
        unless you restart python console. The same as pims.kill_vm()

    Examples
    ----------
    >>> frames.metadata.getPlaneDeltaT(0, 50)
    ...    # evaluates loci.formats.meta.MetadataRetrieve.getPlaneDeltaT(0, 50)

    Notes
    ----------
    Be sure to kill the java VM with pims.kill_vm() the end of the day. It
    cannot be restarted from the same python console, however. You can also
    kill the vm by calling frame.close(is_last=True).

    Dependencies:
    https://github.com/CellProfiler/python-bioformats
    https://github.com/CellProfiler/python-javabridge
    or (windows compiled) http://www.lfd.uci.edu/~gohlke/pythonlibs/#javabridge

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

    def __init__(self, filename, C=(0,), series=0,
                 process_func=None, dtype=None, as_grey=False):
        try:
            self._channel = tuple(C)
        except TypeError:
            self._channel = tuple((C,))

        super(BioformatsReader3D, self).__init__(filename, series,
                                                 process_func)

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
            channel = tuple((value,))
        if np.any(np.greater_equal(channel, self._sizeC)) or \
           np.any(np.less(channel, 0)):
            raise IndexError('Channel index should be positive and less ' +
                             'than the number of channels ' +
                             '({})'.format(self._sizeC + 1))
        self._channel = channel

    def _get_frame(self, series, t):
        """Builds array of images and DataFrame of metadata.
        """
        shape = (len(self._channel), self._sizeZ, self._sizeY, self._sizeX)
        if self.isRGB:
            shape = shape + (self._sizeC,)
        imlist = np.zeros(shape, dtype=self.pixel_type)
        metadata = []

        for (Nc, c) in enumerate(self._channel):
            for z in range(self._sizeZ):
                index = self.get_index(z, c, t)
                imlist[Nc, z], md = self._get_frame_2D(series, index)
                metadata.append(md)

        """The following block produces a dataframe, which is incompatible with
        the pims.Frame object. Instead, here metadata is converted to a dict.
        if DataFrame is not None:
            metadata = DataFrame(metadata, columns=self._metadatacolumns)
            metadata.set_index(['indexC', 'indexZ'], drop=False, inplace=True)
        """
        metadata = np.asarray(metadata).squeeze()
        metadata = dict(zip(self._metadatacolumns, metadata.T))
        return imlist.squeeze(), metadata
