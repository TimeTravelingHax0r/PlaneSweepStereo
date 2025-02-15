import time
from math import floor
import numpy as np
import cv2
from scipy.sparse import csr_matrix

def project_impl(K, Rt, points):
    """
    Project 3D points into a calibrated camera.
    Input:
        K -- 3 x 3 camera intrinsics calibration matrix
        Rt -- 3 x 4 camera extrinsics calibration matrix
        points -- height x width x 3 array of 3D points
    Output:
        projections -- height x width x 2 array of 2D projections
    """
    
    height =  points.shape[0]
    width =  points.shape[1]
    
    out_img = np.zeros((height,width,2))

    for h in range(height):
        for w in range(width):
            in_vec = np.zeros((4))
            in_vec[0] = points[h,w,0]
            in_vec[1] = points[h,w,1]
            in_vec[2] = points[h,w,2]
            in_vec[3] = 1
            ext_point = np.dot(Rt,in_vec)
            int_point = np.dot(K,ext_point)
            int_point /= int_point[2]
            out_img[h,w,0] =  int_point[0]
            out_img[h,w,1] =  int_point[1]
            
    return out_img

def unproject_corners_impl(K, width, height, depth, Rt):
    """
    Unproject the corners of a height-by-width image
    into world coordinates at depth d.
    Input:
        K -- 3x3 camera intrinsics calibration matrix
        width -- width of hte image in pixels
        height -- height of hte image in pixels
        depth -- depth the 3D point is unprojected to
        Rt -- 3 x 4 camera extrinsics calibration matrix
    Output:
        points -- 2 x 2 x 3 array of 3D positions of the image corners
    """
    
    Rt_inv = np.pad(Rt, [(0, 1), (0, 0)], mode='constant')
    # print(Rt_inv)
    Rt_inv[3][3] = 1
    # print(Rt_inv)
    Rt_inv = np.linalg.inv(Rt_inv)
    # print(Rt_inv)
    K_inv = np.linalg.inv(K)
    K_inv *= depth
    
    out_corners = np.zeros((2,2,3))
    
    out_corners[0,0,0] = 0
    out_corners[0,0,1] = 0
    
    out_corners[1,0,0] = 0
    out_corners[1,0,1] = height - 1
    
    out_corners[0,1,0] = width - 1
    out_corners[0,1,1] = 0
    
    out_corners[1,1,0] = width - 1
    out_corners[1,1,1] = height - 1
    
    for h in range(2):
        for w in range(2):
            
            curr_vec = np.zeros((3))
            
            curr_vec[0] = out_corners[h,w,0]
            curr_vec[1] = out_corners[h,w,1]
            curr_vec[2] = 1
            
            # print("input coords", curr_vec)

            curr_vec = np.dot(K_inv, curr_vec)
            
            temp_vec = np.zeros((4))
            temp_vec[0] = curr_vec[0]
            temp_vec[1] = curr_vec[1]
            temp_vec[2] = curr_vec[2]
            temp_vec[3] = 1
            
            curr_vec = np.dot(Rt_inv, temp_vec)
            
            curr_vec /= curr_vec[3]
            
            # print("output coords", curr_vec)
            
            out_corners[h,w,0] = curr_vec[0]
            out_corners[h,w,1] = curr_vec[1]
            out_corners[h,w,2] = curr_vec[2]
            
    return out_corners

def preprocess_ncc_impl(image, ncc_size):
    """
    Prepare normalized patch vectors according to normalized cross
    correlation.

    This is a preprocessing step for the NCC pipeline.  It is expected that
    'preprocess_ncc' is called on every input image to preprocess the NCC
    vectors and then 'compute_ncc' is called to compute the dot product
    between these vectors in two images.

    NCC preprocessing has two steps.
    (1) Compute and subtract the mean.
    (2) Normalize the vector.

    The mean is per channel.  i.e. For an RGB image, over the ncc_size**2
    patch, compute the R, G, and B means separately.  The normalization
    is over all channels.  i.e. For an RGB image, after subtracting out the
    RGB mean, compute the norm over the entire (ncc_size**2 * channels)
    vector and divide.

    If the norm of the vector is < 1e-6, then set the entire vector for that
    patch to zero.

    Patches that extend past the boundary of the input image at all should be
    considered zero.  Their entire vector should be set to 0.

    Patches are flattened into vectors with the default numpy row
    major order.  For example, the following 3D numpy array with shape
    2 (channels) x 2 (height) x 2 (width) patch...

    channel1         channel2
    +------+------+  +------+------+ height
    | x111 | x121 |  | x112 | x122 |  |
    +------+------+  +------+------+  |
    | x211 | x221 |  | x212 | x222 |  |
    +------+------+  +------+------+  v
    width ------->

    gets unrolled using np.reshape into a vector in the following order:

    v = [ x111, x121, x211, x221, x112, x122, x212, x222 ]

    Input:
        image -- height x width x channels image of type float32
        ncc_size -- integer side length of (square) NCC patch region; must be odd
    Output:
        normalized -- height x width x (channels * ncc_size**2) array
    """
    h, w, c = image.shape

    normalized = np.zeros((h, w, c, ncc_size, ncc_size), dtype=np.float32)

    k = ncc_size // 2 # half-width of the patch size

    # the following code fills in `normalized`, which can be thought
    # of as a height-by-width image where each pixel is
    #   a channels-by-ncc_size-by-ncc_size array

    for i in range(ncc_size):
        for j in range(ncc_size):
            # i, j is the top left corner of the the patch
            # so the (i=0,j=0) is the pixel in the top-left corner of the patch
            # which is an offset of (-k, -k) from the center pixel

            # example: image is 10x10x3; ncc_size is 3
            # the image pixels for the top left of all patches come from
            # (0, 0) thru (7, 7) because (7, 7) is an offset of -1, -1 
            # (corresponding to i=0, j=0) from the bottom-right-most patch, 
            # which is centered at (8, 8)
            # generalizing to patch halfsize k, it's (h-2k, w-2k)
            # generalizing to any offset into the patch,
            #   the top left will be i, j
            #   the bottom right will be h-2k + i, w-2k + j
            normalized[k:h-k, k:w-k, :, i, j] = image[i:h-2*k+i, j:w-2*k+j, :]

    # For each patch, subtract out its per-channel mean
    # Then divide the patch by its (not-per-channel) vector norm.
    # Patches with norm < 1e-6 should become all zeros.
    normalized = normalized.reshape(h, w, c, -1)
    normalized = normalized - np.mean(normalized, axis=3, keepdims=True)
    normalized = normalized.reshape(h, w, -1)
    norm = np.linalg.norm(normalized, axis=2, keepdims=True)
    norm[norm == 0] = 1
    # print(norm)
    mask = norm >= 1e-6
    # print(mask)
    mask[:k,:] = False
    mask[-k:,:] = False
    mask[:,:k] = False
    mask[:,-k:] = False
    # print(mask)
    normalized = normalized * mask
    normalized = normalized / norm
    # print(normalized)
    
    return normalized


def compute_ncc_impl(image1, image2):
    """
    Compute normalized cross correlation between two images that already have
    normalized vectors computed for each pixel with preprocess_ncc.

    Input:
        image1 -- height x width x (channels * ncc_size**2) array
        image2 -- height x width x (channels * ncc_size**2) array
    Output:
        ncc -- height x width normalized cross correlation between image1 and
                image2.
    """
    h, w, c = image1.shape[:3]
    ncc_size = int(np.sqrt(image1.shape[2] // c))
    image1 = image1.reshape((h, w, c, ncc_size, ncc_size))
    image2 = image2.reshape((h, w, c, ncc_size, ncc_size))

    numerator = np.sum(image1 * image2, axis=(2, 3, 4))
    denominator = np.sqrt(np.sum(image1**2, axis=(2, 3, 4)) * np.sum(image2**2, axis=(2, 3, 4)))

    denominator[denominator == 0] = 1

    ncc = numerator / denominator

    return ncc
    
    
