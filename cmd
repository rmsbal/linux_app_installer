binary - 

pyinstaller --noconfirm --onefile --windowed  --name LinuxAppInstaller  --add-data "Linux_installer_icon.png:." app.py

mkdir -p LinuxAppInstaller.AppDir/usr/bin
mkdir -p LinuxAppInstaller.AppDir/usr/share/applications
mkdir -p LinuxAppInstaller.AppDir/usr/share/icons/hicolor/256x256/apps

cp dist/LinuxAppInstaller LinuxAppInstaller.AppDir/usr/bin/
cp Linux_installer_icon.png LinuxAppInstaller.AppDir/usr/share/icons/hicolor/256x256/apps/linux-app-installer.png
cp Linux_installer_icon.png LinuxAppInstaller.AppDir/.DirIcon

====================================================================
nano LinuxAppInstaller.AppDir/linux-app-installer.desktop

[Desktop Entry]
Type=Application
Name=Linux App Installer
Exec=LinuxAppInstaller
Icon=linux-app-installer
Categories=Utility;
Comment=Install and manage AppImage and DEB packages
Terminal=false
======================================================================

#make sure you download appimagetool-x86_64.AppImage

~/Applications/tools/appimagetool-x86_64.AppImage LinuxAppInstaller.AppDir

