# Image Pixel Cropper

This is a standalone image crop/export tool. It does not change the existing
NetBlocker firewall tool.

## Features

- Load common image formats.
- Enter an exact target output size in pixels.
- Center-scale the image with mouse wheel zoom.
- Hold the middle mouse button and drag to scale from the center.
- Drag the image to reposition it.
- Drag the orange corner handles to scale from the center.
- Export as PNG, JPG, WebP, or BMP.
- Use `Fill crop` to remove white borders.
- Use `White padding` to keep small images centered on a white background.

## Run

Install Pillow first if it is not already installed:

```bat
python -m pip install Pillow
```

Then run:

```bat
run_image_cropper.bat
```
