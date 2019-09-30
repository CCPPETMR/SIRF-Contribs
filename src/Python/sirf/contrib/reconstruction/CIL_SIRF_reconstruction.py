#%% Initial imports etc
import numpy as np
import matplotlib.pyplot as plt
import os
import shutil
import pSTIR as pet

from sirf.Utilities import examples_data_path
from ccpi.optimisation.algorithms import CGLS, PDHG, FISTA
from ccpi.optimisation.operators import GradientSIRF, BlockOperator, LinearOperator
from ccpi.optimisation.functions import KullbackLeibler, IndicatorBox, FunctionOperatorComposition, BlockFunction, MixedL21Norm    
from ccpi.framework import ImageData
from ccpi.plugins.regularisers import FGP_TV
import scipy

#%%

# Define norm for the acquisition model
def norm(self):
    return LinearOperator.PowerMethod(self, 10)[0]
    
setattr(pet.AcquisitionModelUsingRayTracingMatrix, 'norm', norm)

from sirf.Utilities import check_status, assert_validity
import sirf.pystir as pystir

def KL_call(self, x):
    return -1*self.get_value(x)

def gradient(self, image, subset = -1, out = None):
    
    assert_validity(image, pet.ImageData)
    grad = pet.ImageData()
    grad.handle = pystir.cSTIR_objectiveFunctionGradient\
        (self.handle, image.handle, subset)
    check_status(grad.handle)
    
    if out is None:
        return -1*grad  
    else:
        out.fill(-1*grad)
        
def KL_convex_conjugate(self, x):
    
    '''Convex conjugate of KullbackLeibler at x'''
    
    xlogy = - scipy.special.xlogy(self.b.as_array(), 1 - x.as_array())
    return np.sum(xlogy)        
        
def KL_proximal_conjugate(self, x, tau, out=None):
        
        r'''Proximal operator of the convex conjugate of KullbackLeibler at x:
           
           .. math::     prox_{\tau * f^{*}}(x)
        '''        
                
        if out is None:
            z = x + tau * self.bnoise
            return 0.5*((z + 1) - ((z-1)**2 + 4 * tau * self.b).sqrt())
        else:
            
            tmp = tau * self.bnoise
            tmp += x
            tmp -= 1
            
            self.b.multiply(4*tau, out=out)    
            
            out.add(tmp.power(2), out=out)
            out.sqrt(out=out)
            out *= -1
            tmp += 2
            out += tmp
            out *= 0.5        

setattr(pet.ObjectiveFunction, '__call__', KL_call)
setattr(pet.PoissonLogLikelihoodWithLinearModelForMeanAndProjData, 'gradient', gradient)
setattr(pet.PoissonLogLikelihoodWithLinearModelForMeanAndProjData, 'proximal_conjugate', KL_proximal_conjugate)
setattr(pet.PoissonLogLikelihoodWithLinearModelForMeanAndProjData, 'convex_conjugate', KL_convex_conjugate)


#% go to directory with input files

EXAMPLE = 'BRAIN'

if EXAMPLE == 'SIMULATION':
    
    # adapt this path to your situation (or start everything in the relevant directory)
    os.chdir('/home/sirfuser/Documents/Hackathon4/')    
    ##%% copy files to working folder and change directory to where the output files are
    shutil.rmtree('exhale-output',True)
    shutil.copytree('Exhale','exhale-output')
    os.chdir('exhale-output')
    
    attenuation_header = 'pet_dyn_4D_resp_simul_dynamic_0_state_0_attenuation_map.hv'
    image_header = attenuation_header
    sinogram_header = 'pet_dyn_4D_resp_simul_dynamic_0_state_0.hs'

elif EXAMPLE == 'SMALL':
    # adapt this path to your situation (or start everything in the relevant directory)
    os.chdir(examples_data_path('PET'))
#    #
#    ##%% copy files to working folder and change directory to where the output files are
    shutil.rmtree('working_folder/thorax_single_slice',True)
    shutil.copytree('thorax_single_slice','working_folder/thorax_single_slice')
    os.chdir('working_folder/thorax_single_slice')
        
elif EXAMPLE == 'BRAIN':
    # adapt this path to your situation (or start everything in the relevant directory)
    os.chdir(examples_data_path('PET'))
#    #
#    ##%% copy files to working folder and change directory to where the output files are
    shutil.rmtree('working_folder/brain',True)
    shutil.copytree('brain','working_folder/brain')
    os.chdir('working_folder/brain')
    
    image_header = 'emission.hv'
    attenuation_header = 'attenuation.hv'
    sinogram_header = 'template_sinogram.hs'

# Read in images
    
image = pet.ImageData(image_header);
image_array=image.as_array()
mu_map = pet.ImageData(attenuation_header);
mu_map_array=mu_map.as_array();

# Show Emission image
print('Size of emission: {}'.format(image.shape))

plt.imshow(image.as_array()[0])
plt.colorbar()
plt.title('Emission')
plt.show()

plt.imshow(mu_map.as_array()[0])
plt.colorbar()
plt.title('Attenuation')
plt.show()

#%%

am = pet.AcquisitionModelUsingRayTracingMatrix()
# we will increate the number of rays used for every Line-of-Response (LOR) as an example
# (it is not required for the exercise of course)
am.set_num_tangential_LORs(12)
templ = pet.AcquisitionData(sinogram_header)
pet.AcquisitionData.set_storage_scheme('memory')
am.set_up(templ,image)

#% simulate some data using forward projection
if EXAMPLE == 'SIMULATION':
    
    acquired_data = templ
    image.fill(1)
    noisy_data = acquired_data.clone()

elif EXAMPLE == 'SMALL' or EXAMPLE == 'BRAIN':
    
    acquired_data=am.forward(image)
    
    acquisition_array = acquired_data.as_array()

    np.random.seed(10)
    noisy_data = acquired_data.clone()
    scale = 100
    noisy_array = scale * np.random.poisson(acquisition_array/scale).astype('float64')
    print(' Maximum counts in the data: %d' % noisy_array.max())
    noisy_data.fill(noisy_array)

# Show util per iteration
def show_data(it, obj, x):
    plt.imshow(x.as_array()[10])
    plt.colorbar()
    plt.show()

#%% TV reconstruction using algorithm below

alpha = 0.1

ALGORITHM = 'PDHG_SIRF' # or PDHG_CIL, PDHG_SIRF, FISTA_CIL, FISTA_SIRF, OSMAPOSL

if  ALGORITHM == 'PDHG_SIRF':
    
    operator = am      
    g = FGP_TV(alpha, 50, 1e-7, 0, 1, 0, 'cpu' ) 
    
    fidelity = pet.PoissonLogLikelihoodWithLinearModelForMeanAndProjData()
    fidelity.set_acquisition_model(am)
    fidelity.set_acquisition_data(noisy_data)
    fidelity.set_num_subsets(2)
    fidelity.set_up(image)
    fidelity.L = 100
    fidelity.b = noisy_data
    fidelity.bnoise = noisy_data * 0.0
    
    normK = operator.norm()
         
    sigma = 0.001
    #sigma = 0.001 for thorax one slice and for brain
    
    tau = 1/(sigma*normK**2)     
    
    def SIRF_update_objective(self):

        p1 = self.f(self.x) + self.g(self.x)
        d1 = -(self.f.convex_conjugate(self.y) + self.g.convex_conjugate(-1*self.operator.adjoint(self.y)))

        self.loss.append([p1, d1, p1-d1])    
    
    setattr(PDHG, 'update_objective', SIRF_update_objective)
        
    # Setup and run the PDHG algorithm
    pdhg = PDHG(f = fidelity, g = g, operator = operator, tau = tau, sigma = sigma)
    pdhg.max_iteration = 500
    pdhg.update_objective_interval = 10
    pdhg.run(1000, callback = show_data)
    sol_pdhg = pdhg.get_output()

elif  ALGORITHM == 'PDHG_CIL':
    
    method = 'implicit'
    
    if method == 'explicit':
        
        # Create operators
        op1 = GradientSIRF(image) 
        op2 = am
    
        # Create BlockOperator
        operator = BlockOperator(op1, op2, shape=(2,1) ) 
        
        f2 = KullbackLeibler(noisy_data)  
        g =  IndicatorBox(lower=0)    
                
        f1 = alpha * MixedL21Norm() 
        f = BlockFunction(f1, f2)  
        normK = operator.norm()
        
    elif method == 'implicit':
        
        operator = am      
        g = FGP_TV(alpha, 50, 1e-7, 0, 1, 0, 'cpu' ) 
        f = KullbackLeibler(noisy_data)
        normK = operator.norm()
         
    sigma = 0.001
    tau = 1/(sigma*normK**2)      
        
    # Setup and run the PDHG algorithm
    pdhg = PDHG(f = f, g = g, operator = operator, tau = tau, sigma = sigma)
    pdhg.max_iteration = 500
    pdhg.update_objective_interval = 50
    pdhg.run(1000, callback = show_data)
    sol_pdhg = pdhg.get_output()
        
elif ALGORITHM == 'FISTA_CIL':
    
    tmp_fun = KullbackLeibler(noisy_data)
    tmp_fun.L = 1
    f = FunctionOperatorComposition(tmp_fun, am)
    f.L = 100
    g = FGP_TV(alpha, 50, 1e-7, 0, 1, 0, 'cpu' )
    
    x_init = image.allocate(1)
    fista = FISTA(x_init=x_init, f = f, g = g)
    fista.max_iteration = 500
    fista.update_objective_interval = 50
    fista.run(500, verbose=True, callback = show_data) 
    
    sol_fista_cil = fista.get_output()
    
elif ALGORITHM == 'FISTA_SIRF':
    
    fidelity = pet.PoissonLogLikelihoodWithLinearModelForMeanAndProjData()
    fidelity.set_acquisition_model(am)
    fidelity.set_acquisition_data(noisy_data)
#    fidelity.set_num_subsets(2)
    fidelity.set_up(image)
    fidelity.L = 100
        
    g = FGP_TV(alpha, 50, 1e-7, 0, 1, 0, 'cpu' )

    x_init = image.allocate(1) 
    fista = FISTA(x_init = x_init, f = fidelity, g = g)
    fista.max_iteration = 2000
    fista.update_objective_interval = 50
    fista.run(2000, verbose=True, callback = show_data) 
    
    sol_fista_sirf = fista.get_output()
    
elif ALGORITHM == 'OSMAPOSL':
    
    fidelity = pet.PoissonLogLikelihoodWithLinearModelForMeanAndProjData()
    fidelity.set_acquisition_model(am)
    fidelity.set_acquisition_data(noisy_data)
    fidelity.set_num_subsets(4)
    fidelity.set_up(image)
    
    recon = pet.OSMAPOSLReconstructor()
    recon.set_objective_function(fidelity)
    recon.set_num_subsets(2)
    num_iters = 10;
    recon.set_num_subiterations(num_iters)
    
    reconstructed_image = image.allocate(1)
    recon.set_up(reconstructed_image)
    recon.reconstruct(reconstructed_image)

    plt.imshow(reconstructed_image.as_array()[0])
    plt.colorbar()
    plt.show()    
    
    sol_osmap = reconstructed_image
        