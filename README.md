# pyvCT

**An ABAQUS plug-in for the creation of virtual CT scans from 3D finite element bone/implant models.**

**Developed together with [bonemapy](https://github.com/mhogg/bonemapy), [pyvXRAY](https://github.com/mhogg/pyvxray) and [BMDanalyse](https://github.com/mhogg/BMDanalyse) to provide tools for preparation and post-processing of bone/implant computer models.**

Copyright 2015, Michael Hogg (michael.christopher.hogg@gmail.com)

MIT license - See LICENSE.txt for details on usage and redistribution

## Requirements

### Software requirements

* ABAQUS >= 6.11 (tested on 6.11, 6.12 and 6.13)
* pydicom >= 0.9.9 (available on [github](https://github.com/darcymason/pydicom/releases))

For building cython modules from source (e.g. if not using releases with pre-built modules):
* A C compiler. Using ABAQUS Python on Windows requires Microsoft C++. Can use other compilers (i.e. mingw32) if you have a separate Python installation.
* Cython >= 0.17. This is optional, as .cpp files generated by Cython are provided

**NOTES:**

1.  ABAQUS is a commerical software package and requires a license from [Simulia](http://www.3ds.com/products-services/simulia/overview/)
2.  The author of pyvCT is not associated with ABAQUS/Simulia 
3.  Python and numpy are heavily used by pyvCT. These are built in to ABAQUS. All of the last few releases (v6.11 - v6.13) use Python 2.6.x and numpy 1.4.x

## Help
 
For help create an Issue or a Pull Request on Github.
