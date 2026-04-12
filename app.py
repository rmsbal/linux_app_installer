import os
import re
import sys
import stat
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

APP_TITLE = "Linux App Installer"
APP_COMMENT = "Open and install AppImage and DEB packages"
APP_CATEGORIES = "Utility;System;"
INSTALL_DIR = os.path.expanduser("~/Applications")
DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
ICON_DIR = os.path.expanduser("~/.local/share/icons")
DESKTOP_FILE_NAME = "linux-app-installer.desktop"

APPIMAGE_MIME = "application/x-iso9660-appimage"
DEB_MIME = "application/vnd.debian.binary-package"

# Put your Linux Installer icon here
INSTALLER_ICON_PATH = "Linux_installer_icon.png"


class LinuxInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("860x620")
        self.root.minsize(820, 560)

        self.selected_file = ""
        self.selected_icon = ""
        self.detected_name = ""
        self.detected_comment = ""
        self.temp_extract_dir = None

        self.build_ui()
        self.load_cli_file()

    def build_ui(self):
        wrapper = tk.Frame(self.root, padx=14, pady=14)
        wrapper.pack(fill="both", expand=True)

        tk.Label(
            wrapper,
            text=APP_TITLE,
            font=("Arial", 18, "bold")
        ).pack(anchor="w")

        tk.Label(
            wrapper,
            text="Install AppImage or DEB packages and use the original app icon when available.",
            fg="#444"
        ).pack(anchor="w", pady=(4, 12))

        top = tk.Frame(wrapper)
        top.pack(fill="x", pady=(0, 10))

        tk.Button(top, text="Open File", width=16, command=self.pick_file).pack(side="left", padx=(0, 6))
        tk.Button(top, text="Detect Icon", width=16, command=self.detect_icon_now).pack(side="left", padx=(0, 6))
        tk.Button(top, text="Install Selected", width=16, command=self.install_selected).pack(side="left", padx=(0, 6))
        tk.Button(top, text="Register Opener", width=16, command=self.register_as_handler).pack(side="left", padx=(0, 6))
        tk.Button(top, text="Clear", width=16, command=self.clear_selection).pack(side="left")

        info = tk.LabelFrame(wrapper, text="Package Info", padx=10, pady=10)
        info.pack(fill="x", pady=(0, 10))

        self.file_var = tk.StringVar(value="No file selected")
        self.type_var = tk.StringVar(value="Type: -")
        self.name_var = tk.StringVar(value="Detected name: -")
        self.comment_var = tk.StringVar(value="Comment: -")
        self.icon_var = tk.StringVar(value="Detected icon: -")

        tk.Label(info, textvariable=self.file_var, justify="left", wraplength=780, anchor="w").pack(anchor="w", fill="x")
        tk.Label(info, textvariable=self.type_var, anchor="w").pack(anchor="w", pady=(8, 0))
        tk.Label(info, textvariable=self.name_var, anchor="w").pack(anchor="w", pady=(6, 0))
        tk.Label(info, textvariable=self.comment_var, anchor="w").pack(anchor="w", pady=(6, 0))
        tk.Label(info, textvariable=self.icon_var, justify="left", wraplength=780, anchor="w").pack(anchor="w", pady=(6, 0))

        actions = tk.LabelFrame(wrapper, text="Actions", padx=10, pady=10)
        actions.pack(fill="x", pady=(0, 10))

        tk.Button(actions, text="Install AppImage", width=22, command=self.install_appimage).grid(row=0, column=0, padx=6, pady=6, sticky="w")
        tk.Button(actions, text="Install DEB", width=22, command=self.install_deb).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        tk.Button(actions, text="Uninstall AppImage", width=22, command=self.uninstall_appimage).grid(row=1, column=0, padx=6, pady=6, sticky="w")
        tk.Button(actions, text="Unregister Opener", width=22, command=self.unregister_as_handler).grid(row=1, column=1, padx=6, pady=6, sticky="w")

        log_frame = tk.LabelFrame(wrapper, text="Status", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True)

        self.log_widget = tk.Text(log_frame, height=18, wrap="word")
        self.log_widget.pack(fill="both", expand=True)

        self.log("Ready.")

    def log(self, text):
        self.log_widget.insert("end", text + "\n")
        self.log_widget.see("end")

    def clear_selection(self):
        self.selected_file = ""
        self.selected_icon = ""
        self.detected_name = ""
        self.detected_comment = ""
        self.file_var.set("No file selected")
        self.type_var.set("Type: -")
        self.name_var.set("Detected name: -")
        self.comment_var.set("Comment: -")
        self.icon_var.set("Detected icon: -")
        self.cleanup_temp_dir()
        self.log("Selection cleared.")

    def load_cli_file(self):
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path):
                self.set_selected_file(file_path)
                self.log(f"Opened from file association: {file_path}")

    def pick_file(self):
        path = filedialog.askopenfilename(
            title="Choose AppImage or DEB",
            filetypes=[
                ("Supported files", "*.AppImage *.appimage *.deb"),
                ("AppImage files", "*.AppImage *.appimage"),
                ("Debian packages", "*.deb"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.set_selected_file(path)

    def set_selected_file(self, path):
        self.cleanup_temp_dir()
        self.selected_file = path
        file_type = self.detect_file_type(path)
        self.file_var.set(path)
        self.type_var.set(f"Type: {file_type}")
        self.log(f"Selected file: {path}")
        self.analyze_selected_file()

    def analyze_selected_file(self):
        if not self.ensure_file_selected(show_error=False):
            return

        file_type = self.detect_file_type(self.selected_file)
        self.detected_name = self.default_name_from_file(self.selected_file)
        self.detected_comment = ""
        self.selected_icon = ""

        if file_type == "AppImage":
            info = self.extract_appimage_metadata(self.selected_file)
        elif file_type == "DEB package":
            info = self.extract_deb_metadata(self.selected_file)
        else:
            info = {"name": self.detected_name, "comment": "", "icon_path": ""}

        if info.get("name"):
            self.detected_name = info["name"]
        if info.get("comment"):
            self.detected_comment = info["comment"]
        if info.get("icon_path"):
            self.selected_icon = info["icon_path"]
        elif self.get_fallback_icon():
            self.selected_icon = self.get_fallback_icon()

        self.name_var.set(f"Detected name: {self.detected_name or '-'}")
        self.comment_var.set(f"Comment: {self.detected_comment or '-'}")
        self.icon_var.set(f"Detected icon: {self.selected_icon or '-'}")

        self.log(f"Detected name: {self.detected_name or '-'}")
        self.log(f"Detected comment: {self.detected_comment or '-'}")
        self.log(f"Detected icon: {self.selected_icon or '-'}")

    def detect_icon_now(self):
        if not self.ensure_file_selected():
            return
        self.analyze_selected_file()
        messagebox.showinfo("Detection complete", "Metadata and icon detection finished.")

    def detect_file_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".deb":
            return "DEB package"
        if ext == ".appimage":
            return "AppImage"
        return "Unknown"

    def default_name_from_file(self, path):
        return os.path.splitext(os.path.basename(path))[0]

    def ensure_file_selected(self, show_error=True):
        if not self.selected_file:
            if show_error:
                messagebox.showerror("No file selected", "Please choose a .AppImage or .deb file first.")
            return False
        if not os.path.exists(self.selected_file):
            if show_error:
                messagebox.showerror("Missing file", "The selected file does not exist.")
            return False
        return True

    def get_fallback_icon(self):
        if INSTALLER_ICON_PATH and os.path.exists(INSTALLER_ICON_PATH):
            return INSTALLER_ICON_PATH
        return ""

    def install_selected(self):
        if not self.ensure_file_selected():
            return

        file_type = self.detect_file_type(self.selected_file)
        if file_type == "AppImage":
            self.install_appimage()
        elif file_type == "DEB package":
            self.install_deb()
        else:
            messagebox.showerror("Unsupported", "Only .AppImage and .deb files are supported.")

    def extract_appimage_metadata(self, appimage_path):
        result = {"name": "", "comment": "", "icon_path": ""}
        extract_dir = self.make_temp_dir("appimage_extract_")

        try:
            subprocess.run(
                [appimage_path, "--appimage-extract"],
                cwd=extract_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception as e:
            self.log(f"AppImage extraction failed: {e}")
            return result

        root = os.path.join(extract_dir, "squashfs-root")
        if not os.path.isdir(root):
            self.log("AppImage extraction did not produce squashfs-root.")
            return result

        desktop_files = self.find_files(root, [".desktop"])

        if desktop_files:
            desktop_info = self.parse_desktop_file(desktop_files[0])
            result["name"] = desktop_info.get("Name", "") or self.default_name_from_file(appimage_path)
            result["comment"] = desktop_info.get("Comment", "")
            icon_name = desktop_info.get("Icon", "")
        else:
            result["name"] = self.default_name_from_file(appimage_path)
            icon_name = ""

        icon_path = self.find_icon_in_extracted_tree(root, icon_name)
        if not icon_path:
            icon_path = self.find_first_image(root)

        if icon_path:
            result["icon_path"] = icon_path

        return result

    def extract_deb_metadata(self, deb_path):
        result = {"name": "", "comment": "", "icon_path": ""}
        extract_dir = self.make_temp_dir("deb_extract_")

        if not shutil.which("dpkg-deb"):
            self.log("dpkg-deb not found. Cannot inspect DEB contents.")
            result["name"] = self.default_name_from_file(deb_path)
            return result

        try:
            subprocess.run(
                ["dpkg-deb", "-x", deb_path, extract_dir],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception as e:
            self.log(f"DEB extraction failed: {e}")
            result["name"] = self.default_name_from_file(deb_path)
            return result

        desktop_files = self.find_files(extract_dir, [".desktop"])

        if desktop_files:
            desktop_info = self.parse_desktop_file(desktop_files[0])
            result["name"] = desktop_info.get("Name", "") or self.default_name_from_file(deb_path)
            result["comment"] = desktop_info.get("Comment", "")
            icon_name = desktop_info.get("Icon", "")
        else:
            result["name"] = self.default_name_from_file(deb_path)
            icon_name = ""

        icon_path = self.find_icon_in_extracted_tree(extract_dir, icon_name)
        if not icon_path:
            icon_path = self.find_first_image(extract_dir)

        if icon_path:
            result["icon_path"] = icon_path

        return result

    def install_appimage(self):
        if not self.ensure_file_selected():
            return
        if self.detect_file_type(self.selected_file) != "AppImage":
            messagebox.showerror("Wrong file type", "Please select an .AppImage file.")
            return

        self.analyze_selected_file()

        try:
            os.makedirs(INSTALL_DIR, exist_ok=True)
            os.makedirs(DESKTOP_DIR, exist_ok=True)
            os.makedirs(ICON_DIR, exist_ok=True)

            app_name = self.detected_name or self.default_name_from_file(self.selected_file)
            safe_name = self.slugify(app_name)

            target_appimage = os.path.join(INSTALL_DIR, f"{safe_name}.AppImage")
            shutil.copy2(self.selected_file, target_appimage)

            mode = os.stat(target_appimage).st_mode
            os.chmod(target_appimage, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            installed_icon_path = ""
            source_icon = self.selected_icon or self.get_fallback_icon()

            if source_icon and os.path.exists(source_icon):
                ext = os.path.splitext(source_icon)[1].lower() or ".png"
                installed_icon_path = os.path.join(ICON_DIR, f"{safe_name}{ext}")
                shutil.copy2(source_icon, installed_icon_path)

            desktop_path = os.path.join(DESKTOP_DIR, f"{safe_name}.desktop")
            desktop_content = self.build_app_desktop(
                app_name=app_name,
                comment=self.detected_comment or "Installed by Linux Installer",
                exec_path=target_appimage,
                icon_path=installed_icon_path,
            )

            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(desktop_content)

            os.chmod(desktop_path, 0o755)
            self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)

            self.log(f"Installed AppImage to: {target_appimage}")
            self.log(f"Created launcher: {desktop_path}")
            if installed_icon_path:
                self.log(f"Installed icon: {installed_icon_path}")

            messagebox.showinfo(
                "Installed",
                f"{app_name} was installed.\n\nIt should appear in your app menu."
            )
        except Exception as e:
            self.log(f"AppImage install failed: {e}")
            messagebox.showerror("Install failed", str(e))

    def uninstall_appimage(self):
        if not self.ensure_file_selected():
            return
        if self.detect_file_type(self.selected_file) != "AppImage":
            messagebox.showerror("Wrong file type", "Please select the original .AppImage file.")
            return

        self.analyze_selected_file()

        try:
            app_name = self.detected_name or self.default_name_from_file(self.selected_file)
            safe_name = self.slugify(app_name)

            removed = False
            candidates = [
                os.path.join(INSTALL_DIR, f"{safe_name}.AppImage"),
                os.path.join(DESKTOP_DIR, f"{safe_name}.desktop"),
            ]

            for ext in [".png", ".svg", ".xpm", ".ico"]:
                candidates.append(os.path.join(ICON_DIR, f"{safe_name}{ext}"))

            for path in candidates:
                if os.path.exists(path):
                    os.remove(path)
                    self.log(f"Removed: {path}")
                    removed = True

            self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)

            if removed:
                messagebox.showinfo("Uninstalled", f"{app_name} was removed.")
            else:
                messagebox.showinfo("Nothing found", "No installed files were found for that app.")
        except Exception as e:
            self.log(f"Uninstall failed: {e}")
            messagebox.showerror("Uninstall failed", str(e))

    def install_deb(self):
        if not self.ensure_file_selected():
            return
        if self.detect_file_type(self.selected_file) != "DEB package":
            messagebox.showerror("Wrong file type", "Please select a .deb file.")
            return

        deb_path = os.path.abspath(self.selected_file)

        gui_installers = [
            ["gdebi-gtk", deb_path],
            ["plasma-discover", deb_path],
            ["gnome-software", deb_path],
            ["software-center", deb_path],
        ]

        for cmd in gui_installers:
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd)
                    self.log(f"Opened DEB in GUI installer: {' '.join(cmd)}")
                    messagebox.showinfo("Opened", "The DEB package was opened in a package installer.")
                    return
                except Exception as e:
                    self.log(f"Failed to launch {cmd[0]}: {e}")

        if shutil.which("pkexec") and shutil.which("apt"):
            use_pkexec = messagebox.askyesno(
                "Install DEB",
                "No GUI package installer was found.\n\nDo you want to install it using administrator permission?"
            )
            if use_pkexec:
                try:
                    subprocess.Popen(["pkexec", "apt", "install", "-y", deb_path])
                    self.log(f"Started privileged DEB install: pkexec apt install -y {deb_path}")
                    messagebox.showinfo("Started", "Installation command was started.")
                    return
                except Exception as e:
                    self.log(f"pkexec install failed: {e}")
                    messagebox.showerror("Install failed", str(e))
                    return

        messagebox.showerror(
            "No installer found",
            "No GUI package installer or pkexec+apt was found on this system."
        )

    def register_as_handler(self):
        try:
            os.makedirs(DESKTOP_DIR, exist_ok=True)
            os.makedirs(ICON_DIR, exist_ok=True)

            script_path = os.path.abspath(sys.argv[0])
            python_exec = sys.executable or "python3"
            desktop_path = os.path.join(DESKTOP_DIR, DESKTOP_FILE_NAME)

            installer_icon_name = "linux-installer"
            installer_icon_target = ""

            fallback_icon = self.get_fallback_icon()
            if fallback_icon:
                ext = os.path.splitext(fallback_icon)[1].lower() or ".png"
                installer_icon_target = os.path.join(ICON_DIR, f"{installer_icon_name}{ext}")
                shutil.copy2(fallback_icon, installer_icon_target)

            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(self.build_handler_desktop(script_path, python_exec, installer_icon_target))

            os.chmod(desktop_path, 0o755)

            if shutil.which("xdg-mime"):
                self.try_run(["xdg-mime", "default", DESKTOP_FILE_NAME, APPIMAGE_MIME], check=False)
                self.try_run(["xdg-mime", "default", DESKTOP_FILE_NAME, DEB_MIME], check=False)

            self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)

            self.log(f"Registered handler desktop file: {desktop_path}")
            if installer_icon_target:
                self.log(f"Installer icon copied to: {installer_icon_target}")
            self.log("Associated Linux Installer with AppImage and DEB MIME types.")

            messagebox.showinfo(
                "Registered",
                "Linux Installer was registered.\n\nIts app menu icon now uses your custom icon, and that same icon is the fallback for installed apps."
            )
        except Exception as e:
            self.log(f"Registration failed: {e}")
            messagebox.showerror("Registration failed", str(e))

    def unregister_as_handler(self):
        try:
            desktop_path = os.path.join(DESKTOP_DIR, DESKTOP_FILE_NAME)
            if os.path.exists(desktop_path):
                os.remove(desktop_path)
                self.log(f"Removed: {desktop_path}")

            for ext in [".png", ".svg", ".xpm", ".ico"]:
                installer_icon = os.path.join(ICON_DIR, f"linux-installer{ext}")
                if os.path.exists(installer_icon):
                    os.remove(installer_icon)
                    self.log(f"Removed: {installer_icon}")

            self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)
            messagebox.showinfo("Removed", "Linux Installer registration was removed.")
        except Exception as e:
            self.log(f"Unregister failed: {e}")
            messagebox.showerror("Unregister failed", str(e))

    def build_app_desktop(self, app_name, comment, exec_path, icon_path):
        return f"""[Desktop Entry]
Version=1.0
Type=Application
Name={app_name}
Comment={comment}
Exec="{exec_path}"
Icon={icon_path}
Terminal=false
Categories=Utility;
StartupNotify=true
"""

    def build_handler_desktop(self, script_path, python_exec, icon_path):
        icon_value = icon_path if icon_path else "system-software-install"
        return f"""[Desktop Entry]
Version=1.0
Type=Application
Name={APP_TITLE}
Comment={APP_COMMENT}
Exec="{python_exec}" "{script_path}" %f
Icon={icon_value}
Terminal=false
Categories={APP_CATEGORIES}
MimeType={APPIMAGE_MIME};{DEB_MIME};
StartupNotify=true
NoDisplay=false
"""

    def parse_desktop_file(self, path):
        data = {}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key in ("Name", "Comment", "Icon", "Exec"):
                        data[key] = value.strip()
        except Exception as e:
            self.log(f"Failed to parse desktop file {path}: {e}")
        return data

    def find_files(self, root_dir, extensions):
        found = []
        exts = tuple(e.lower() for e in extensions)
        for dirpath, _, filenames in os.walk(root_dir):
            for name in filenames:
                if name.lower().endswith(exts):
                    found.append(os.path.join(dirpath, name))
        return found

    def find_first_image(self, root_dir):
        preferred = []
        for dirpath, _, filenames in os.walk(root_dir):
            for name in filenames:
                low = name.lower()
                if low.endswith((".png", ".svg", ".xpm")):
                    path = os.path.join(dirpath, name)
                    preferred.append(path)

        if not preferred:
            return ""

        def score(path):
            low = path.lower()
            s = 0
            if "/usr/share/icons/" in low:
                s += 50
            if "/usr/share/pixmaps/" in low:
                s += 40
            if "256x256" in low:
                s += 30
            if "128x128" in low:
                s += 20
            if low.endswith(".png"):
                s += 10
            return s

        preferred.sort(key=score, reverse=True)
        return preferred[0]

    def find_icon_in_extracted_tree(self, root_dir, icon_name):
        if not icon_name:
            return ""

        icon_name = os.path.basename(icon_name.strip())
        candidates = []

        for dirpath, _, filenames in os.walk(root_dir):
            for name in filenames:
                file_base, file_ext = os.path.splitext(name)
                if file_ext.lower() not in (".png", ".svg", ".xpm", ".ico"):
                    continue

                full_path = os.path.join(dirpath, name)

                if name == icon_name:
                    candidates.append((100, full_path))
                elif file_base == icon_name:
                    candidates.append((90, full_path))
                elif icon_name.lower() in file_base.lower():
                    candidates.append((70, full_path))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

        return ""

    def slugify(self, value):
        value = value.strip().lower()
        value = re.sub(r"[^\w\s.-]", "", value)
        value = re.sub(r"[\s.]+", "-", value)
        value = re.sub(r"-+", "-", value)
        return value.strip("-") or "app"

    def try_run(self, command, check=False):
        try:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=check)
            return True
        except Exception:
            return False

    def make_temp_dir(self, prefix):
        self.cleanup_temp_dir()
        self.temp_extract_dir = tempfile.mkdtemp(prefix=prefix)
        return self.temp_extract_dir

    def cleanup_temp_dir(self):
        if self.temp_extract_dir and os.path.isdir(self.temp_extract_dir):
            try:
                shutil.rmtree(self.temp_extract_dir, ignore_errors=True)
            except Exception:
                pass
        self.temp_extract_dir = None


if __name__ == "__main__":
    root = tk.Tk()
    app = LinuxInstallerApp(root)

    def on_close():
        app.cleanup_temp_dir()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()