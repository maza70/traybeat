# TrayBeat dev

In this directory is all to build TrayBeat as AppImage, deb, rpm and flatpak

## build Dependencies for fedora

* sudo flatpak install flathub org.flatpak.Builder
* sudo dnf install cairo-devel cairo-gobject-devel gobject-introspection-devel glib2-devel python3-devel pkgconf-pkg-config


## Directories

### nfpm
Directory for templates, assets to build deb and rpm packages.

### appimage
Directory for assets to build the AppImage.

### flatpak
Directory for assets to build the flatpak and store the build-output from flatpak-builder.

### dist 
The files for distribution.


## Scripts
- **clean.sh**
    - Clean the cache and all generated files and directories.
- **make_venv.sh**
    - Make the venv for develpment, include all needed python packages
- **build-icons.sh**
    -  Create the image resources for dark and light theme. 
- **build-appimage.sh**
    - This script create a AppImage from the source.
- **build-flatpak.sh**
    - This script create a flatpak from the source.  
- **build-sys-package.sh**
    -  Create a deb and rpm package from the previous generated AppImage.    
- **make-pylock.sh**
    -  Update the pylock files.
- **build-release.sh**
    -  Create a release AppImage, deb and rpm from scratch. Use --full for a full build  (clean and rebuild all) 


