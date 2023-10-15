<div id="user-content-toc" align="center">
  <ul>
    <summary>
      <h2 style="display: inline-block;">
        <a href="https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#download-and-install">Download</a>
        ·
        <a href="https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#tutorial">Tutorial</a>
        <br>
        <a href="https://github.com/olive-groves/butterfly_viewer">Butterfly Viewer</a>
      </h2>
    </summary>
  </ul>
</div>

<h1 align="center"> 
  Butterfly Registrator
</h1>

<p align="center">
  <img src="https://olive-groves.github.io/butterfly_registrator/images/registrator_registration.gif" alt="Animated screencapture of the Butterfly Registrator showing a control point of a moving image being moved to match that of a reference image, the registration being applied, and the sliding overlay preview being moved to compare the registered image with the reference image.">
  <br />
  <i>Registering an XRF element map to a color image¹</i>
</p>

<p align="center">
  <img src="https://olive-groves.github.io/butterfly_registrator/images/registrator_alphascale.gif" alt="Animated screencapture of the Butterfly Registrator showing an XRF map dragged into the alphascale converter, the color picker selector being changed, and the save alphascale shown in the Butterfly Viewer.">
  <br />
  <i>Alphascale conversion of grayscale XRF element maps¹, then shown in <a href="https://olive-groves.github.io/butterfly_viewer">Butterfly Viewer</a></i>
</p>

Butterfly Registrator is a preprocessing app for aligning images using pairs of control points you click and drag. It helps you align (or [*register*](#how-does-the-registrator-register-images)) images to a given reference such that their heights and widths match and the features within those images line up, making it easy to later overlay and compare them without the hassle of manually zooming, stretching, and cropping them beforehand.

The Registrator also creates alphascale images. You can convert individual grayscale images using a color picker and also merge multiple alphascale images into a single image.

The Registrator runs as an [installable Windows executable](#windows-executable) or directly on its [Python source code](#python).

Most types of PNG, JPEG, and TIFF can be loaded into the Registrator. It can likewise save registered image files to PNG, JPEG, and TIFF.

With [Butterfly Viewer](https://olive-groves.github.io/butterfly_viewer) you can rapidly compare your registered images with sliding overlays and synchronized side-by-side pan and zoom. The Viewer is handy for visually inspecting painting research data such as high-res and raking-light photos, X-rays, and element maps from XRF and RIS — especially with element maps [converted to alphascale](#convert-to-alphascale).

## Key features

- **Side-by-side image previews** to rapidly check the accuracy of registration and make adjustments before saving a copy.

- **Batch mode** to apply the same registration to multiple images of the same capture/perspective, which is useful for registering element maps from scanning X-ray fluorescence (XRF) and reflectance imaging spectroscopy (RIS) to a ground truth like a color photograph.

- **Save registration control points to CSV** to easily document and trace the images you register, and import later if you want to reproduce or adjust a registration.

<sup>¹*Small Pear Tree in Blossom* by Vincent van Gogh (Van Gogh Museum, Amsterdam)</sup>

## How-to's

Our [Butterfly Registrator page](https://olive-groves.github.io/butterfly_registrator) documents how to install and use the Registrator, as well how contribute to it as a developer. 

### Install as [Windows executable](https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#windows-executable)

### Run on [Python](https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#python)

### [Tutorial](https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#tutorial) of main features

### [Help](https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#help) with common questions

### [Developers](https://olive-groves.github.io/butterfly_registrator/butterfly_registrator.html#developers)

Or see the source markdown file in the `docs` branch under `docs/DEVELOPERS.md`.