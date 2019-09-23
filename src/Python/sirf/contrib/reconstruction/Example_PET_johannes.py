#%% Initial imports etc
import numpy as np
import matplotlib.pyplot as plt
import os
import shutil
import pSTIR as pet

from sirf.Utilities import examples_data_path
from ccpi.optimisation.algorithms import CGLS, PDHG, FISTA
from ccpi.optimisation.operators import GradientSIRF, BlockOperator, LinearOperator
from ccpi.optimisation.functions import KullbackLeibler, IndicatorBox, BlockFunction, MixedL21Norm    
from ccpi.framework import ImageData
from ccpi.plugins.regularisers import FGP_TV

#%% go to directory with input files

# adapt this path to your situation (or start everything in the relevant directory)
os.chdir('/home/sirfuser/Documents/Hackathon4/')
#
##%% copy files to working folder and change directory to where the output files are
shutil.rmtree('exhale-output',True)
shutil.copytree('Exhale','exhale-output')
os.chdir('exhale-output')

#%% Read in images
image = pet.ImageData('pet_dyn_4D_resp_simul_dynamic_0_state_0_attenuation_map.hv');
image.fill(1)
image_array=image.as_array()
mu_map = pet.ImageData('pet_dyn_4D_resp_simul_dynamic_0_state_0_attenuation_map.hv');
mu_map_array=mu_map.as_array();

#%% Show Emission image

print('Size of emission: {}'.format(image.shape))

plt.imshow(image.as_array()[0])
plt.title('Emission')
plt.show()

plt.imshow(mu_map.as_array()[0])
plt.title('Attenuation')
plt.show()

#%% save max for future displays
cmax = image_array.max()*.6

#%% create acquisition model

am = pet.AcquisitionModelUsingRayTracingMatrix()
# we will increate the number of rays used for every Line-of-Response (LOR) as an example
# (it is not required for the exercise of course)
am.set_num_tangential_LORs(12)
templ = pet.AcquisitionData('pet_dyn_4D_resp_simul_dynamic_0_state_0.hs')
#pet.AcquisitionData.set_storage_scheme('memory')
am.set_up(templ,image); 

#%%
def norm(self):
    return LinearOperator.PowerMethod(self, 3)[0]
    
setattr(pet.AcquisitionModelUsingRayTracingMatrix, 'norm', norm)

#%%
normK = am.norm()


#%% simulate some data using forward projection

acquired_data=templ
acquisition_array = acquired_data.as_array()

#%% Display bitmaps of a middle sinogram
plt.imshow(acquisition_array[0,100,:,:], vmin = 0, vmax = 7)
plt.title('Acquisition Data')
plt.show()

#%% Generate a noisy realisation of the data

#noisy_array=np.random.poisson(acquisition_array).astype('float64')
#print(' Maximum counts in the data: %d' % noisy_array.max())
## stuff into a new AcquisitionData object
noisy_data = acquired_data.clone()
#noisy_data.fill(noisy_array)
#%%

#noisy_dat
plt.imshow(noisy_data.as_array()[0,100,:,:])
plt.title('Noisy Acquisition Data')
plt.show()

#%%


def show_data(it, obj, x):
    plt.imshow(x.as_array()[63])
    plt.colorbar()
    plt.show()

#%% CGLS reconstruction

# create initial image
# we could just use a uniform image but here we will create a disk with a different
# initial value (this will help the display later on)

#def make_cylindrical_FOV(image):
#    """truncate to cylindrical FOV"""
#    filter = pet.TruncateToCylinderProcessor()
#    filter.apply(image)
#
init_image=image.clone()
#init_image.fill(cmax/4)
#make_cylindrical_FOV(init_image)

# display
#idata = init_image.as_array()
#plt.figure()
#plt.imshow(idata[0], vmax = cmax)

# Setup and run the simple CGLS algorithm  
x_init = init_image #am.domain_geometry().allocate()

cgls = CGLS(x_init = x_init, operator = am, data = noisy_data)
cgls.max_iteration = 10
cgls.update_objective_interval = 2
cgls.run(10, verbose = True, callback = show_data)

#%%
sol_cgls = cgls.get_output().as_array()
plt.imshow(sol_cgls[63], vmin = 0)
plt.title('CGLS reconstruction')
plt.colorbar()
plt.show()

#%% TV reconstruction using PDHG algorithm 

alpha = 0.8        

method = 'GPU'

if method == 'CPU':
    
    # Create operators
    op1 = GradientSIRF(image) 
    op2 = am

    # Create BlockOperator
    operator = BlockOperator(op1, op2, shape=(2,1) ) 
    
    f2 = KullbackLeibler(noisy_data)  
    g =  IndicatorBox(lower=0)    
            
    f1 = alpha * MixedL21Norm() 
    f = BlockFunction(f1, f2)   
    
elif method == 'GPU':
    
    operator = am  
    
    g = FGP_TV(alpha, 50, 1e-7, 0, 0, 1, 'cpu' ) 
#    g.proximal = SIRF_proximal
    f = KullbackLeibler(noisy_data)
    
sigma = 1
tau = 1/(sigma*normK**2)      
    
#%%
def show_data(it, obj, x):
    plt.imshow(x.as_array()[63])
    plt.colorbar()
    plt.show()
    
# Setup and run the PDHG algorithm
#pdhg = PDHG(f = f, g = g, operator = operator, tau = tau, sigma = sigma)
#pdhg.max_iteration = 10
#pdhg.update_objective_interval = 2
#pdhg.run(1000, callback = show_data)

# Setup and run the FISTA algorithm
#fista = FISTA(f = f, g = g, operator = operator, tau = tau, sigma = sigma)
#pdhg.max_iteration = 1000
#pdhg.update_objective_interval = 10
#pdhg.run(1000, callback = show_data)
    
from ccpi.optimisation.functions import FunctionOperatorComposition

fidelity = FunctionOperatorComposition(KullbackLeibler(noisy_data) , am)
regularizer = FGP_TV(alpha, 50, 1e-7, 0, 0, 1, 'cpu' ) 

fista = FISTA()
fista.set_up(x_init=x_init , f=fidelity, g=regularizer)
fista.max_iteration = 10
fista.update_objective_interval = 2
fista.run(500, verbose = True, callback = show_data)
