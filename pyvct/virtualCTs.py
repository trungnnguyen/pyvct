# -*- coding: utf-8 -*-

# Copyright (C) 2015 Michael Hogg

# This file is part of pyvct - See LICENSE.txt for information on usage and redistribution

import os
from abaqus import session
from abaqusConstants import ELEMENT_NODAL
from cythonMods import createElementMap
import elementTypes as et
import copy
from odbAccess import OdbMeshElementType
import numpy as np

# ~~~~~~~~~~

def convert3Dto1Dindex(i,j,k,NX,NY,NZ):
    """Converts 3D array index to 1D array index"""
    index = i+j*NX+k*NX*NY
    return index
    
# ~~~~~~~~~~
  
def convert1Dto3Dindex(index,NX,NY,NZ):
    """Converts 1D array index to 1D array index"""
    k = index / (NX*NY)
    j = (index - k*NX*NY) / NX
    i = index - k*NX*NY - j*NX
    return [i,j,k]
    
# ~~~~~~~~~~   

def transformPoint(TM,point):
    """Transforms point using supplied transform"""
    point = np.append(point,1.0)
    return np.dot(TM,point)[:3]
    
# ~~~~~~~~~~      

def createTransformationMatrix(Ma,Mb,Vab,rel='a'):
    """
    Creates a transformation matrix that can be used to transform a point from csys a to csys b.
    Ma  = 3x3 matrix containing unit vectors of orthogonal coordinate directions for csys a
    Mb  = 3x3 matrix containing unit vectors of orthogonal coordinate directions for csys b
    Vab = 3x1 vector from origin of csys a to csys b
    rel = 'a' or 'b' = Character to indicate if Vab is relative to csys a or csys b
    """
    if rel!='a' and rel!='b': return None
    a1,a2,a3 = Ma
    b1,b2,b3 = Mb
    # Rotation matrix
    R = np.identity(4,np.float)
    R[0,0:3] = [np.dot(b1,a1), np.dot(b1,a2), np.dot(b1,a3)]
    R[1,0:3] = [np.dot(b2,a1), np.dot(b2,a2), np.dot(b2,a3)]
    R[2,0:3] = [np.dot(b3,a1), np.dot(b3,a2), np.dot(b3,a3)]    
    # Transformation matrix
    if rel=='b':
        Vab = np.append(Vab,1.0)
        Vab = np.dot(R.T,Vab)[0:3]
    T = np.identity(4,np.float)     
    T[0:3,3] = -Vab       
    # Transformation matrix
    return np.dot(R,T)
    
# ~~~~~~~~~~ 

def getTMfromCsys(odb,csysName):
    if csysName=='GLOBAL': return None
    # Parse coordinate system name
    csysName = csysName.split(r'(')[0].strip()
    # Get ABAQUS datumCsys
    lcsys = None
    # Check odb csyses
    if csysName in odb.rootAssembly.datumCsyses.keys(): 
        lcsys = odb.rootAssembly.datumCsyses[csysName]
    # Check scratch odb csyses
    if odb.path in session.scratchOdbs.keys():
        if csysName in session.scratchOdbs[odb.path].rootAssembly.datumCsyses.keys():
            lcsys = session.scratchOdbs[odb.path].rootAssembly.datumCsyses[csysName]
    if lcsys==None: return None
    # Global coordinate system
    Og = np.zeros(3)
    Mg = np.identity(3)
    # Local coordinate system
    Ol    = lcsys.origin
    Ml    = np.zeros((3,3))
    Ml[0] = lcsys.xAxis/np.linalg.norm(lcsys.xAxis) # NOTE: This should already be a unit vector
    Ml[1] = lcsys.yAxis/np.linalg.norm(lcsys.yAxis) #       Shouldn't need to normalise
    Ml[2] = lcsys.zAxis/np.linalg.norm(lcsys.zAxis)
    # Create transformation matrix
    Vgl = Ol-Og
    TM  = createTransformationMatrix(Mg,Ml,Vgl,rel='a')
    return TM
        
# ~~~~~~~~~~            

def parseRegionSetName(regionSetName):
    """ Get region and setName from regionSetName """ 
    if '.' in regionSetName: region,setName = regionSetName.split('.')
    else:                    region,setName = 'Assembly',regionSetName   
    return region,setName

# ~~~~~~~~~~   
    
def getElements(odb,regionSetName):
    
    """Get element type and number of nodes per element"""
        
    # Get region set and elements
    region,setName = parseRegionSetName(regionSetName)
    if region=='Assembly':
        setRegion =  odb.rootAssembly.elementSets[regionSetName]
        if type(setRegion.elements[0])==OdbMeshElementType:       
            elements = setRegion.elements        
        else:
            elements=[]
            for meshElemArray in setRegion.elements:
                for e in meshElemArray:
                    elements.append(e)
    else:
        if setName=='ALL':
            setRegion = odb.rootAssembly.instances[region]
            elements  = setRegion.elements
        else:
            setRegion = odb.rootAssembly.instances[region].elementSets[setName]
            elements  = setRegion.elements
    
    # Get part information: (1) instance names, (2) element types and (3) number of each element type 
    partInfo={}
    for e in elements: 
        if not partInfo.has_key(e.instanceName): partInfo[e.instanceName]={}
        if not partInfo[e.instanceName].has_key(e.type): partInfo[e.instanceName][e.type]=0
        partInfo[e.instanceName][e.type]+=1  
        
    # Put all element types from all part instances in a list
    eTypes = []
    for k1 in partInfo.keys():
        for k2 in partInfo[k1].keys(): eTypes.append(k2)
    eTypes = dict.fromkeys(eTypes,1).keys()
        
    # Check that elements are supported
    usTypes=[]
    for eType in eTypes:
        if not any([True for seType in et.seTypes.keys() if seType==eType]):
            usTypes.append(str(eType))
    if len(usTypes)>0:
        if len(usTypes)==1: strvars = ('',usTypes[0],regionSetName,'is')
        else:               strvars = ('s',', '.join(usTypes),regionSetName,'are') 
        print '\nElement type%s %s in region %s %s not supported' % strvars
        return None
    
    return partInfo, setRegion, elements
       
# ~~~~~~~~~~      

def getPartData(odb,regionSetName,TM):

    """Get region data based on original (undeformed) coordinates"""

    # Get elements and part info
    result = getElements(odb,regionSetName)
    if result==None: return None
    else:
        regionInfo, regionSet, elements = result
        numElems = len(elements)
        ec = dict([(ename,eclass()) for ename,eclass in et.seTypes.items()])

    # Create empty dictionary,array to store element data 
    elemData = copy.deepcopy(regionInfo)
    for instName in elemData.keys():
        for k,v in elemData[instName].items():
            elemData[instName][k] = np.zeros(v,dtype=[('label','|i4'),('econn','|i4',(ec[k].numNodes,))])
    eCount      = dict([(k1,dict([k2,0] for k2 in regionInfo[k1].keys())) for k1 in regionInfo.keys()])     
    setNodeLabs = dict([(k,{}) for k in regionInfo.keys()])    
    # Create a list of element connectivities (list of nodes connected to each element)    
    for e in xrange(numElems):
        
        elem  = elements[e]
        eConn = elem.connectivity
        eInst = elem.instanceName
        eType = elem.type
        
        eIndex = eCount[eInst][eType]
        elemData[eInst][eType][eIndex] = (elem.label,eConn)
        eCount[eInst][eType] +=1  
        
        for n in eConn:        
            setNodeLabs[eInst][n] = 1
    
    numSetNodes = np.sum([len(setNodeLabs[k]) for k in setNodeLabs.keys()])
    setNodes    = np.zeros(numSetNodes,dtype=[('instName','|a80'),('label','|i4'),('coord','|f4',(3,))])    
    nodeCount   = 0
    for instName in setNodeLabs.keys():
        inst  = odb.rootAssembly.instances[instName]
        nodes = inst.nodes
        numNodes = len(nodes)
        for n in xrange(numNodes):
            node  = nodes[n]
            label = node.label
            if label in setNodeLabs[instName]:
                setNodes[nodeCount] = (instName,label,node.coordinates)
                nodeCount+=1
    
    # Transform the coordinates from the global csys to the local csys
    if TM is not None:
        print 'TM is not None'
        for i in xrange(numSetNodes):
            setNodes['coord'][i] = transformPoint(TM,setNodes['coord'][i])
        
    # Get bounding box
    low  = np.min(setNodes['coord'],axis=0)
    upp  = np.max(setNodes['coord'],axis=0) 
    bbox = (low,upp)

    # Convert setNodes to a dictionary for fast indexing by node label
    setNodeList = dict([(k,{}) for k in regionInfo.keys()])    
    for instName in setNodeList.keys():
        indx = np.where(setNodes['instName']==instName)
        setNodeList[instName] = dict(zip(setNodes[indx]['label'],setNodes[indx]['coord']))      
    
    return regionSet,elemData,setNodeList,bbox
   
# ~~~~~~~~~~ 

def checkDependencies():
    """Check pyvxray dependencies are available"""        
    try:
        from dicom.dataset import Dataset, FileDataset
    except: 
        print 'Error: Cannot load pydicom package'
        return False
    return True
    
# ~~~~~~~~~~

def createVirtualCT(odbName,bRegionSetName,BMDfoname,showImplant,iRegionSetName,
                    iDensity,stepNumber,csysName,sliceResolution,sliceSpacing,newSubDirName):
    """Creates a virtual CT stack from an ABAQUS odb file. The odb file should contain \n""" + \
    """a step with a fieldoutput variable representing bone mineral density (BMD)"""
        
    # User message
    print '\npyvCT: Create virtual CT plugin'
    
    # Check dependencies
    if not checkDependencies():
        print 'Error: Virtual CT not created\n'
        return
    
    # Process inputs
    sliceResolutions = {'256 x 256':(256,256), '512 x 512':(512,512)} 
    stepNumber       = int(stepNumber)
    sliceSpacing     = float(sliceSpacing)
        
    # Set variables
    NX,NY     = sliceResolutions[sliceResolution]   
    iDensity /= 1000.    
    odb       = session.odbs[odbName]
    ec        = dict([(ename,eclass()) for ename,eclass in et.seTypes.items()])

    # Get transformation matrix to convert from global to local coordinate system
    TM = getTMfromCsys(odb,csysName)
    print '\nCT reference frame will be relative to %s' % csysName

    # Get part data and create a bounding box. The bounding box should include the implant if specified
    bRegion,bElemData,bNodeList,bBBox = getPartData(odb,bRegionSetName,TM)
    if showImplant:    
        iRegion,iElemData,iNodeList,iBBox = getPartData(odb,iRegionSetName,TM)
        bbLow = np.min((bBBox[0],iBBox[0]),axis=0)
        bbUpp = np.max((bBBox[1],iBBox[1]),axis=0)
    else:
        bbLow,bbUpp = bBBox
        
    # Define extents of CT stack
    bbox        = np.array([bbLow,bbUpp])
    bbCentre    = bbox.mean(axis=0)
    bbSides     = 1.05*(bbUpp - bbLow)
    bbSides[:2] = np.max(bbSides[:2])
    bbLow       = bbCentre-0.5*bbSides
    bbUpp       = bbCentre+0.5*bbSides
    lx,ly,lz    = bbUpp - bbLow
    x0,y0,z0    = bbLow
    xN,yN,zN    = bbUpp
    
    # Generate CT grid
    NZ = int(np.ceil(lz/sliceSpacing+1))
    x  = np.linspace(x0,xN,NX)
    y  = np.linspace(y0,yN,NY)
    z  = np.linspace(z0,zN,NZ)
    
    # Get BMD values for all elements 
    # Get frame            
    stepName = "Step-%i" % (stepNumber)
    frame    = odb.steps[stepName].frames[-1]
    # Get BMD data for bRegion in frame
    print 'Getting BMD values'
    # Initialise BMDvalues 
    BMDvalues = dict([(k,{}) for k in bElemData.keys()])         
    for instName,instData in bElemData.items():
        for etype,eData in instData.items():
            for i in xrange(eData.size): 
                BMDvalues[instName][eData[i]['label']] = et.seTypes[etype]()    
    # Get list of BMD element_nodal values for each node in bone region
    BMDfov = frame.fieldOutputs[BMDfoname].getSubset(region=bRegion, position=ELEMENT_NODAL).values
    BMDnv  = {}
    for i in xrange(len(BMDfov)):
        val = BMDfov[i]            
        instanceName = val.instance.name
        elemLabel    = val.elementLabel        
        nodeLabel    = val.nodeLabel
        if not BMDnv.has_key(instanceName): BMDnv[instanceName] = {}
        if not BMDnv[instanceName].has_key(nodeLabel): BMDnv[instanceName][nodeLabel] = []
        BMDnv[instanceName][nodeLabel].append(val.data)
    # Average BMD element_nodal values
    for instName in BMDnv.keys():
        for nl in BMDnv[instName].keys():
            BMDnv[instName][nl] = np.mean(BMDnv[instName][nl])
    # Add nodal BMD values to BMDvalues array 
    for instName in bElemData.keys():
        for etype in bElemData[instName].keys():
            eData = bElemData[instName][etype]
            for i in xrange(eData.size):             
                el = eData[i]['label']
                nc = eData[i]['econn']
                for indx in range(nc.size):
                    nl  = nc[indx]
                    val = BMDnv[instName][nl]
                    BMDvalues[instName][el].setNodalValueByIndex(indx,val)
                
    # Create the element map for the bone and map values over to voxel array
    print 'Mapping BMD values'
    voxels = np.zeros((NX,NY,NZ),dtype=np.float32)  
    for instName in bElemData.keys():
        for etype in bElemData[instName].keys():
            edata = bElemData[instName][etype]
            emap  = createElementMap(bNodeList[instName],edata['label'],edata['econn'],ec[etype].numNodes,x,y,z) 
            # Where an intersection was found between the grid point and implant, add implant to voxel array
            indx = np.where(emap['cte']>0)[0]
            for gpi in indx:
                cte,g,h,r = emap[gpi]
                ipc = [g,h,r]
                i,j,k = convert1Dto3Dindex(gpi,NX,NY,NZ)
                voxels[i,j,k] = BMDvalues[instName][cte].interp(ipc)
            
    # Create element map for the implant, map to 3D space array and then add to voxels array
    if showImplant:
        print 'Adding implant'
        # Get a map for each instance and element type. Then combine maps together
        for instName in iElemData.keys():
            for etype in iElemData[instName].keys():
                edata = iElemData[instName][etype]
                emap  = createElementMap(iNodeList[instName],edata['label'],edata['econn'],ec[etype].numNodes,x,y,z)
                # Where an intersection was found between the grid point and implant, add implant to voxel array
                indx = np.where(emap['cte']>0)[0]
                for gpi in indx:    
                    i,j,k = convert1Dto3Dindex(gpi,NX,NY,NZ)
                    voxels[i,j,k] = iDensity
        
    # Get min/max range of voxel values
    vmin,vmax = [voxels.min(),voxels.max()]
        
    # Scale voxel values to maximum range
    numbits = 8
    low,upp = 0, 2**numbits-1
    voxels  = low + (voxels-vmin)/(vmax-vmin)*upp
    voxels  = voxels.astype(np.uint16)
    
    # Write CT slices to new directory
    print 'Writing CT slice files'
    # Create a new sub-directory to keep CT slice files
    newSubDirPath =  os.path.join(os.getcwd(),newSubDirName)
    if os.path.isdir(newSubDirPath):
        for i in range(1000):
            newSubDirPath = os.path.join(os.getcwd(),newSubDirName+'_%d'%(i+1))
            if not os.path.isdir(newSubDirPath): break
    os.mkdir(newSubDirPath)
    
    # Assume stack direction is z-direction. Need to reorder voxel array
    # Note: The array ds.PixelArray is indexed by [row,col], which is equivalent to [yi,xi]. Also,
    # because we are adding to CTvals by z slice, then the resulting index of CTvals is [zi,yi,xi].
    # Correct this to more typical index [xi,yi,zi] by swapping xi and zi e.g. zi,yi,xi -> xi,yi,zi
    voxels = voxels.swapaxes(0,2)
    voxels = voxels[:,::-1,:]
    
    # Setup basic metadata
    psx = lx/(NX-1)
    psy = ly/(NY-1)
    metaData = {}
    metaData['PixelSpacing'] = ['%.3f' % v for v in (psx,psy)]
    
    # Write CT slices: One per z-index
    for s in range(voxels.shape[0]):
        sn = ('%5d.dcm' % (s+1)).replace(' ','0')
        fn = os.path.join(newSubDirPath,sn)
        metaData['ImagePositionPatient'] = ['%.3f' % v for v in (0.0,0.0,z[s])]
        pixel_array = voxels[s]
        writeCTslice(pixel_array,fn,metaData)
  
    # User message
    print 'Virtual CT has been created in %s' % newSubDirPath
    print '\nFinished\n'
    
# ~~~~~~~~~~ 

def writeCTslice(pixel_array,filename,metaData):
    
    from dicom.dataset import Dataset, FileDataset

    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID =    ''
    file_meta.MediaStorageSOPInstanceUID = ''
    file_meta.ImplementationClassUID =     ''
    ds = FileDataset(filename,{},file_meta = file_meta,preamble="\0"*128)
    ds.BitsAllocated       = 16                       # 16-bit grey-scale voxel values
    ds.SamplesPerPixel     =  1                       # 1 for grey scale, 4 for RGBA
    ds.PixelRepresentation =  0                       # 0 for unsigned, 1 for signed
    ds.PhotometricInterpretation = 'MONOCHROME2'      # 0 is black
    ds.ImagePositionPatient      = metaData['ImagePositionPatient']
    ds.Columns       = pixel_array.shape[0]
    ds.Rows          = pixel_array.shape[1]    
    ds.PixelSpacing  = metaData['PixelSpacing']
    if pixel_array.dtype != np.uint16:
        pixel_array = pixel_array.astype(np.uint16)
    ds.PixelData = pixel_array.tostring()
    ds.save_as(filename)
    return
    
    