# TrayBeat dev

In this directory is all to build TrayBeat as AppImage, deb, rpm

## Directories

### nfpm
Directory for templates,assets to build deb and rpm packages.

### appimage
Directory for assets to build the AppImage.

## Scripts
- **clean.sh**
    - Clean the cache and all generated files and directories.
- **make_venv.sh**
    - Make the venv for develpment, include all needed python packages
- **build-icons.sh**
    -  Create the image resources for dark and light theme. 
- **build-appimage.sh**
    - This script create a AppImage from the source.
- **build-sys-package.sh**
    -  Create a deb and rpm package from the previous generated AppImage.    
- **build-release.sh**
    -  Create a release AppImage, deb and rpm from scratch.
