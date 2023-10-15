#!/usr/bin/env python3

"""Algorithms to create and merge alphascale images.

Used in Butterfly Registrator, but can be called separately in scripts without
the PyQt user interface library.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



from cv2 import cvtColor, COLOR_BGR2BGRA, imread, imwrite, IMREAD_UNCHANGED
import numpy as np



def grayscale_to_alphascale(img, which_color_rgb=[255, 255, 255]):
    """Convert a grayscale image to an alphascale image with a specified RGB color.
    
    Args:
        img (NumPy array): Grayscale image with BGR channels (blue, green, red). Recommended to be 
         loaded with cv2 imread() with default settings (for example, img = imread(filepath)).
        which_color_rgb (list): Color of the alphascale as RGB channels (red, blue, green).
    
    Returns:
        output (NumPy array): Alphascale image with BGRA channels (blue, green, red, alpha).
    """

    output = cvtColor(img, COLOR_BGR2BGRA) # Add alphachannel.

    # Calculate grayscale value, then set that to the alpha channel (white = opaque; black = transparent)
    # ITU-R BT.709 standard: Rlin * 0.2126 + Glin * 0.7152 + Blin * 0.0722 = Y 
    output[:,:,3] = np.dot(output[:,:,:3], [0.2126, 0.7152, 0.0722])

    # Create alpha-only image wherein only the alpha channel represents the level of intensity and all color is white
    # Can be thought of replacing the grayscale of black-to-white with an "alphascale" of transparentwhite-to-opaquewhite)
    output = output.copy()
    output[:,:,:3] = 0

    output[np.s_[:,:,0]] = which_color_rgb[2] # Apply blue
    output[np.s_[:,:,1]] = which_color_rgb[1] # Apply green
    output[np.s_[:,:,2]] = which_color_rgb[0] # Apply red

    return output



def merge_alphascale(imgs):
    """Merge multiple alphascale images into a single alphascale image.

    Color at each pixel is calculated as the weighted sum of the colors at that pixel across the 
    images, normalized by dividing all the channels by the maximum value of the channels. The 
    weight of an image's color at a pixel is its alphachannel value at that pixel divided by the 
    sum of all images' alphachannel values at that pixel.

    Alphachannel at each pixel is the maximum alphachannel value at that pixel across all images.
    
    Args:
        imgs (list of NumPy array): Alphascale images in a list having each been opened with 
         imread(filepath, IMREAD_UNCHANGED) to preserve BGRA channels (blue, green, red, alpha).
    
    Returns:
        output (NumPy array): Alphascale image with BGRA channels.
    """

    shape = imgs[0].shape
    rows = shape[0]
    cols = shape[1]

    a_appended = []
    a_sum = np.zeros((rows,cols))

    i = 0
    for img in imgs: 
        a_appended.append(imgs[i][:,:,3].astype(np.int_)) # Make a list of all alpha channel arrays (for finding the maximum later).
        a_sum = a_sum + a_appended[i] # Sum the alphachannel value of each pixel across the images.
        i += 1

    a = np.amax(np.dstack(a_appended), axis=2) # Stack the alphachannel arrays to find the maximum value amongst them at each pixel.

    f = []

    i = 0
    for img in imgs:
        with np.errstate(divide='ignore',invalid='ignore'): 
            f.append(a_appended[i]/a_sum) # Calculate the color weight of each image.
        i += 1

    b = np.zeros((rows,cols))
    g = np.zeros((rows,cols))
    r = np.zeros((rows,cols))

    i = 0
    for img in imgs:
        b = b + imgs[i][:,:,0]*f[i]
        g = g + imgs[i][:,:,1]*f[i]
        r = r + imgs[i][:,:,2]*f[i]
        i += 1
    
    bgr_max = np.amax(np.dstack((b,g,r)), axis=2) # Find the maximum RGB channel at each pixel.
    max_norm = 255./bgr_max # Normalize the RGB channels to the maximum RGB channel.
    b = b*max_norm
    g = g*max_norm
    r = r*max_norm

    output = np.dstack((b,g,r,a)).astype(np.uint8)

    return output



def main():

    filepath1 = r"C:\image1.png"
    filepath2 = r"C:\image2.png"

    filepath_output = r"C:\merged.png"

    imgs = []

    imgs.append(imread(filepath1, IMREAD_UNCHANGED))
    imgs.append(imread(filepath2, IMREAD_UNCHANGED))

    output = merge_alphascale(imgs=imgs)

    imwrite(filepath_output, output)



if __name__ == '__main__':
    main()