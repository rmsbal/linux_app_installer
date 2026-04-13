import json
import os
import re
import sys
import stat
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Linux App Installer"
APP_COMMENT = "Install, manage, and uninstall AppImage and DEB packages"
APP_CATEGORIES = "Utility;System;"
INSTALL_DIR = os.path.expanduser("~/Applications")
DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
ICON_DIR = os.path.expanduser("~/.local/share/icons")
APP_STATE_DIR = os.path.expanduser("~/.local/share/linux-app-installer")
MANIFEST_FILE = os.path.join(APP_STATE_DIR, "installed_appimages.json")
DEB_MANIFEST_FILE = os.path.join(APP_STATE_DIR, "installed_debs.json")
DESKTOP_FILE_NAME = "linux-app-installer.desktop"

APPIMAGE_MIME = "application/x-iso9660-appimage"
DEB_MIME = "application/vnd.debian.binary-package"

# Change this to your real icon path
INSTALLER_ICON_PATH = "/home/mark/Pictures/Linux_installer_icon.png"


class LinuxInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1080x720")
        self.root.minsize(960, 640)

        self.selected_file = ""
        self.selected_icon = ""
        self.detected_name = ""
        self.detected_comment = ""
        self.detected_package_name = ""
        self.detected_version = ""
        self.temp_extract_dir = None
        self.installed_apps_cache = []
        self.busy_dialog = None
        self.busy_bar = None

        self.ensure_app_dirs()
        self.build_ui()
        self.load_cli_file()
        self.refresh_installed_apps()

        self.root.after(300, self.auto_register_handler)

    def ensure_app_dirs(self):
        os.makedirs(INSTALL_DIR, exist_ok=True)
        os.makedirs(DESKTOP_DIR, exist_ok=True)
        os.makedirs(ICON_DIR, exist_ok=True)
        os.makedirs(APP_STATE_DIR, exist_ok=True)

        if not os.path.exists(MANIFEST_FILE):
            self.save_manifest([])

        if not os.path.exists(DEB_MANIFEST_FILE):
            self.save_deb_manifest([])

    # -------------------------
    # UI
    # -------------------------

    def build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.installer_tab = tk.Frame(self.notebook)
        self.apps_tab = tk.Frame(self.notebook)

        self.notebook.add(self.installer_tab, text="Installer")
        self.notebook.add(self.apps_tab, text="Installed Apps")

        self.build_installer_tab()
        self.build_apps_tab()

    def build_installer_tab(self):
        wrapper = tk.Frame(self.installer_tab, padx=14, pady=14)
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

        tk.Button(
            top,
            text="Install",
            width=16,
            command=lambda: self.run_with_loader_safe("Installing package...", self.install_selected)
        ).pack(side="left", padx=(0, 6))

        tk.Button(top, text="Clear", width=16, command=self.clear_selection).pack(side="left")

        info = tk.LabelFrame(wrapper, text="Package Info", padx=10, pady=10)
        info.pack(fill="x", pady=(0, 10))

        self.file_var = tk.StringVar(value="No file selected")
        self.type_var = tk.StringVar(value="Type: -")
        self.name_var = tk.StringVar(value="Detected name: -")
        self.comment_var = tk.StringVar(value="Comment: -")
        self.icon_var = tk.StringVar(value="Detected icon: -")
        self.pkg_var = tk.StringVar(value="Package name: -")
        self.version_var = tk.StringVar(value="Version: -")

        tk.Label(info, textvariable=self.file_var, justify="left", wraplength=950, anchor="w").pack(anchor="w", fill="x")
        tk.Label(info, textvariable=self.type_var, anchor="w").pack(anchor="w", pady=(8, 0))
        tk.Label(info, textvariable=self.name_var, anchor="w").pack(anchor="w", pady=(6, 0))
        tk.Label(info, textvariable=self.pkg_var, anchor="w").pack(anchor="w", pady=(6, 0))
        tk.Label(info, textvariable=self.version_var, anchor="w").pack(anchor="w", pady=(6, 0))
        tk.Label(info, textvariable=self.comment_var, anchor="w").pack(anchor="w", pady=(6, 0))
        tk.Label(info, textvariable=self.icon_var, justify="left", wraplength=950, anchor="w").pack(anchor="w", pady=(6, 0))

        log_frame = tk.LabelFrame(wrapper, text="Status", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True)

        self.log_widget = tk.Text(log_frame, height=16, wrap="word")
        self.log_widget.pack(fill="both", expand=True)

        self.log("Ready.")

    def build_apps_tab(self):
        wrapper = tk.Frame(self.apps_tab, padx=14, pady=14)
        wrapper.pack(fill="both", expand=True)

        tk.Label(
            wrapper,
            text="Installed Apps",
            font=("Arial", 18, "bold")
        ).pack(anchor="w")

        tk.Label(
            wrapper,
            text="Shows apps managed or tracked by this installer.",
            fg="#444"
        ).pack(anchor="w", pady=(4, 12))

        controls = tk.Frame(wrapper)
        controls.pack(fill="x", pady=(0, 10))

        tk.Label(controls, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(controls, textvariable=self.search_var, width=40)
        search_entry.pack(side="left", padx=(6, 10))
        search_entry.bind("<KeyRelease>", lambda e: self.populate_installed_apps_tree())

        tk.Button(
            controls,
            text="Refresh",
            width=14,
            command=lambda: self.run_with_loader_safe("Refreshing installed apps...", self.refresh_installed_apps)
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            controls,
            text="Uninstall Selected",
            width=18,
            command=lambda: self.run_with_loader_safe("Uninstalling selected app...", self.uninstall_selected_installed_app)
        ).pack(side="left", padx=(0, 6))

        tree_frame = tk.Frame(wrapper)
        tree_frame.pack(fill="both", expand=True)

        columns = ("name", "version", "source", "desktop", "exec")
        self.apps_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.apps_tree.heading("name", text="Name")
        self.apps_tree.heading("version", text="Version")
        self.apps_tree.heading("source", text="Source")
        self.apps_tree.heading("desktop", text="Desktop File / Package")
        self.apps_tree.heading("exec", text="Exec / Source File")

        self.apps_tree.column("name", width=240)
        self.apps_tree.column("version", width=110)
        self.apps_tree.column("source", width=100)
        self.apps_tree.column("desktop", width=300)
        self.apps_tree.column("exec", width=280)

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.apps_tree.yview)
        self.apps_tree.configure(yscrollcommand=yscroll.set)

        self.apps_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        details = tk.LabelFrame(wrapper, text="Selected App Details", padx=10, pady=10)
        details.pack(fill="x", pady=(10, 0))

        self.selected_app_details = tk.StringVar(value="No app selected.")
        tk.Label(details, textvariable=self.selected_app_details, justify="left", anchor="w", wraplength=980).pack(anchor="w", fill="x")

        self.apps_tree.bind("<<TreeviewSelect>>", lambda e: self.update_selected_app_details())

    # -------------------------
    # Busy dialog
    # -------------------------

    def show_busy_dialog(self, message="Processing..."):
        self.close_busy_dialog()

        self.root.config(cursor="watch")
        self.root.update_idletasks()

        self.busy_dialog = tk.Toplevel(self.root)
        self.busy_dialog.title("Please wait")
        self.busy_dialog.resizable(False, False)
        self.busy_dialog.transient(self.root)
        self.busy_dialog.grab_set()
        self.busy_dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        width = 320
        height = 120

        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        x = root_x + (root_width // 2) - (width // 2)
        y = root_y + (root_height // 2) - (height // 2)

        self.busy_dialog.geometry(f"{width}x{height}+{x}+{y}")

        frame = tk.Frame(self.busy_dialog, padx=16, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=message, font=("Arial", 11)).pack(pady=(0, 12))

        self.busy_bar = ttk.Progressbar(frame, mode="indeterminate", length=260)
        self.busy_bar.pack()
        self.busy_bar.start(10)

        self.busy_dialog.update_idletasks()

    def close_busy_dialog(self):
        try:
            if self.busy_bar:
                self.busy_bar.stop()
        except Exception:
            pass

        try:
            if self.busy_dialog:
                self.busy_dialog.grab_release()
                self.busy_dialog.destroy()
        except Exception:
            pass

        self.busy_bar = None
        self.busy_dialog = None

        try:
            self.root.config(cursor="")
            self.root.update_idletasks()
        except Exception:
            pass

    def run_with_loader(self, message, func, *args, **kwargs):
        self.show_busy_dialog(message)
        try:
            self.root.update_idletasks()
            return func(*args, **kwargs)
        finally:
            self.close_busy_dialog()

    def run_with_loader_safe(self, message, func, *args, **kwargs):
        self.show_busy_dialog(message)
        try:
            self.root.update_idletasks()
            return func(*args, **kwargs)
        except Exception as e:
            self.log(f"Operation failed: {e}")
            messagebox.showerror("Error", str(e))
            return None
        finally:
            self.close_busy_dialog()

    # -------------------------
    # Logging
    # -------------------------

    def log(self, text):
        self.log_widget.insert("end", text + "\n")
        self.log_widget.see("end")

    # -------------------------
    # Installer tab logic
    # -------------------------

    def clear_selection(self):
        self.selected_file = ""
        self.selected_icon = ""
        self.detected_name = ""
        self.detected_comment = ""
        self.detected_package_name = ""
        self.detected_version = ""

        self.file_var.set("No file selected")
        self.type_var.set("Type: -")
        self.name_var.set("Detected name: -")
        self.comment_var.set("Comment: -")
        self.icon_var.set("Detected icon: -")
        self.pkg_var.set("Package name: -")
        self.version_var.set("Version: -")

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
            self.run_with_loader_safe("Loading selected file...", self.set_selected_file, path)

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
        self.detected_package_name = ""
        self.detected_version = ""

        if file_type == "AppImage":
            info = self.extract_appimage_metadata(self.selected_file)
            self.detected_version = info.get("version", "") or self.detect_app_version(self.selected_file, self.detected_name)
        elif file_type == "DEB package":
            info = self.extract_deb_metadata(self.selected_file)
            self.detected_package_name = info.get("package_name", "")
            self.detected_version = info.get("version", "")
        else:
            info = {"name": self.detected_name, "comment": "", "icon_path": "", "package_name": "", "version": ""}

        if info.get("name"):
            self.detected_name = info["name"]
        if info.get("comment"):
            self.detected_comment = info["comment"]
        if info.get("icon_path"):
            self.selected_icon = info["icon_path"]
        elif self.get_fallback_icon():
            self.selected_icon = self.get_fallback_icon()

        if info.get("package_name"):
            self.detected_package_name = info["package_name"]
        if info.get("version"):
            self.detected_version = info["version"]

        self.name_var.set(f"Detected name: {self.detected_name or '-'}")
        self.comment_var.set(f"Comment: {self.detected_comment or '-'}")
        self.icon_var.set(f"Detected icon: {self.selected_icon or '-'}")
        self.pkg_var.set(f"Package name: {self.detected_package_name or '-'}")
        self.version_var.set(f"Version: {self.detected_version or '-'}")

        self.log(f"Detected name: {self.detected_name or '-'}")
        self.log(f"Detected package name: {self.detected_package_name or '-'}")
        self.log(f"Detected version: {self.detected_version or '-'}")
        self.log(f"Detected comment: {self.detected_comment or '-'}")
        self.log(f"Detected icon: {self.selected_icon or '-'}")

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

    # -------------------------
    # Executable handling
    # -------------------------

    def is_executable(self, path):
        return os.access(path, os.X_OK)

    def make_file_executable(self, path):
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def ensure_appimage_executable_for_backend(self, source_path, working_path):
        source_exec = self.is_executable(source_path)
        work_exec = self.is_executable(working_path)

        self.log(f"Source executable: {source_exec}")
        self.log(f"Working copy executable: {work_exec}")

        if not source_exec:
            allow = messagebox.askyesno(
                "AppImage not executable",
                "This AppImage is not executable yet.\n\nDo you want Linux App Installer to add execute permission automatically?"
            )
            if not allow:
                self.log("User declined making the AppImage executable.")
                return False

            try:
                self.make_file_executable(source_path)
                self.log(f"Made source AppImage executable: {source_path}")
            except Exception as e:
                self.log(f"Failed to make source AppImage executable: {e}")
                messagebox.showerror(
                    "Permission change failed",
                    f"Could not make the original AppImage executable.\n\n{e}"
                )
                return False

        try:
            self.make_file_executable(working_path)
            self.log(f"Made working AppImage executable: {working_path}")
        except Exception as e:
            self.log(f"Failed to make working AppImage executable: {e}")
            messagebox.showerror(
                "Permission change failed",
                f"Could not make the backend working copy executable.\n\n{e}"
            )
            return False

        return True

    # -------------------------
    # Version / duplicate checks
    # -------------------------

    def normalize_app_name(self, name):
        return re.sub(r"[\s._-]+", "", (name or "").strip().lower())

    def extract_version_from_text(self, text):
        if not text:
            return ""

        patterns = [
            r"\b\d+\.\d+\.\d+(?:\.\d+)?\b",
            r"\b\d+\.\d+\b",
            r"\b\d{4}\.\d+\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        return ""

    def detect_app_version(self, file_path, detected_name=""):
        sources = [
            detected_name or "",
            os.path.splitext(os.path.basename(file_path))[0]
        ]

        for src in sources:
            version = self.extract_version_from_text(src)
            if version:
                return version

        return ""

    def find_existing_installed_app(self, app_name):
        manifest = self.load_manifest()
        target_name = self.normalize_app_name(app_name)

        for item in manifest:
            existing_name = self.normalize_app_name(item.get("name", ""))
            existing_slug = self.normalize_app_name(item.get("slug", ""))
            if existing_name == target_name or existing_slug == target_name:
                return item

        return None

    def compare_versions(self, v1, v2):
        def parts(v):
            return [int(x) for x in re.findall(r"\d+", v or "0")]

        a = parts(v1)
        b = parts(v2)

        max_len = max(len(a), len(b))
        a += [0] * (max_len - len(a))
        b += [0] * (max_len - len(b))

        if a > b:
            return 1
        if a < b:
            return -1
        return 0

    def decide_install_action(self, app_name, new_version, existing_version, source_label="package"):
        if not existing_version:
            return "install"

        if new_version and existing_version:
            cmp_result = self.compare_versions(new_version, existing_version)

            if cmp_result == 0:
                answer = messagebox.askyesno(
                    f"{source_label} already installed",
                    f"'{app_name}' version '{new_version}' is already installed.\n\n"
                    "Do you want to reinstall it?"
                )
                return "reinstall" if answer else "cancel"

            if cmp_result > 0:
                answer = messagebox.askyesno(
                    "Update available",
                    f"'{app_name}' is already installed.\n\n"
                    f"Installed version: {existing_version}\n"
                    f"New version: {new_version}\n\n"
                    "Do you want to update it?"
                )
                return "upgrade" if answer else "cancel"

            if cmp_result < 0:
                answer = messagebox.askyesno(
                    "Older version detected",
                    f"'{app_name}' is already installed.\n\n"
                    f"Installed version: {existing_version}\n"
                    f"Selected version: {new_version}\n\n"
                    "Do you want to replace it with the older version?"
                )
                return "downgrade" if answer else "cancel"

        answer = messagebox.askyesno(
            f"{source_label} already installed",
            f"'{app_name}' is already installed.\n\n"
            f"Installed version: {existing_version or '-'}\n"
            f"New version: {new_version or '-'}\n\n"
            "Do you want to replace/reinstall it?"
        )
        return "replace" if answer else "cancel"

    def get_installed_deb_version(self, package_name):
        if not package_name or not shutil.which("dpkg-query"):
            return ""

        try:
            version = subprocess.check_output(
                ["dpkg-query", "-W", "-f=${Version}", package_name],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            return version
        except Exception:
            return ""

    # -------------------------
    # AppImage metadata
    # -------------------------

    def extract_appimage_metadata(self, appimage_path):
        result = {"name": "", "comment": "", "icon_path": "", "version": ""}
        extract_dir = self.make_temp_dir("appimage_extract_")

        try:
            temp_appimage = os.path.join(extract_dir, os.path.basename(appimage_path))
            shutil.copy2(appimage_path, temp_appimage)
            self.log(f"Copied AppImage to temp location: {temp_appimage}")

            result["version"] = self.detect_app_version(appimage_path, self.default_name_from_file(appimage_path))

            if not self.ensure_appimage_executable_for_backend(appimage_path, temp_appimage):
                result["name"] = self.default_name_from_file(appimage_path)
                return result

            proc = subprocess.run(
                [temp_appimage, "--appimage-extract"],
                cwd=extract_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )

            if proc.returncode != 0:
                err = (proc.stderr or "").strip()
                self.log(f"AppImage extract command failed with code {proc.returncode}")
                if err:
                    self.log(f"stderr: {err}")
        except Exception as e:
            self.log(f"AppImage extraction failed: {e}")
            result["name"] = self.default_name_from_file(appimage_path)
            result["version"] = self.detect_app_version(appimage_path, result["name"])
            return result

        root = os.path.join(extract_dir, "squashfs-root")
        if not os.path.isdir(root):
            self.log("AppImage extraction did not produce squashfs-root.")
            result["name"] = self.default_name_from_file(appimage_path)
            result["version"] = self.detect_app_version(appimage_path, result["name"])
            return result

        self.log(f"AppImage extracted to: {root}")

        diricon = self.find_diricon(root)
        if diricon:
            self.log(f"Found .DirIcon: {diricon}")

        desktop_files = self.find_files(root, [".desktop"])
        self.log(f"Found {len(desktop_files)} desktop file(s).")

        best_desktop = self.choose_best_desktop_file(desktop_files, appimage_path)
        icon_name = ""

        if best_desktop:
            self.log(f"Using desktop file: {best_desktop}")
            desktop_info = self.parse_desktop_file(best_desktop)
            result["name"] = desktop_info.get("Name", "") or self.default_name_from_file(appimage_path)
            result["comment"] = desktop_info.get("Comment", "")
            icon_name = desktop_info.get("Icon", "")
            self.log(f"Desktop Icon field: {icon_name or '-'}")
        else:
            result["name"] = self.default_name_from_file(appimage_path)
            self.log("No desktop file selected, using filename as app name.")

        if not result["version"]:
            result["version"] = self.detect_app_version(appimage_path, result["name"])

        if diricon:
            result["icon_path"] = diricon
            return result

        icon_path = self.find_icon_in_extracted_tree(root, icon_name)
        if icon_path:
            self.log(f"Matched icon by name: {icon_path}")

        if not icon_path:
            icon_path = self.find_first_image(root)
            if icon_path:
                self.log(f"Using best fallback image: {icon_path}")

        if icon_path:
            result["icon_path"] = icon_path
        else:
            self.log("No AppImage icon found. Falling back to installer icon if available.")

        return result

    def find_diricon(self, root_dir):
        candidates = [
            os.path.join(root_dir, ".DirIcon"),
            os.path.join(root_dir, ".diricon"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return ""

    def choose_best_desktop_file(self, desktop_files, appimage_path):
        if not desktop_files:
            return ""

        app_name = os.path.splitext(os.path.basename(appimage_path))[0].lower()
        scored = []

        for path in desktop_files:
            info = self.parse_desktop_file(path)
            score = 0

            exec_val = info.get("Exec", "").lower()
            name_val = info.get("Name", "").lower()

            if "apprun" in exec_val:
                score += 100
            if app_name and app_name in name_val:
                score += 50
            if "/applications/" in path.lower():
                score += 20

            scored.append((score, path))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else ""

    # -------------------------
    # DEB metadata
    # -------------------------

    def extract_deb_metadata(self, deb_path):
        result = {
            "name": "",
            "comment": "",
            "icon_path": "",
            "package_name": "",
            "version": ""
        }
        extract_dir = self.make_temp_dir("deb_extract_")

        if not shutil.which("dpkg-deb"):
            self.log("dpkg-deb not found. Cannot inspect DEB contents.")
            result["name"] = self.default_name_from_file(deb_path)
            return result

        try:
            pkg_name = subprocess.check_output(
                ["dpkg-deb", "-f", deb_path, "Package"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            version = subprocess.check_output(
                ["dpkg-deb", "-f", deb_path, "Version"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            result["package_name"] = pkg_name
            result["version"] = version
            self.log(f"DEB package name: {pkg_name or '-'}")
            self.log(f"DEB version: {version or '-'}")
        except Exception as e:
            self.log(f"Could not read DEB control fields: {e}")

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
            best_desktop = desktop_files[0]
            desktop_info = self.parse_desktop_file(best_desktop)
            result["name"] = desktop_info.get("Name", "") or self.default_name_from_file(deb_path)
            result["comment"] = desktop_info.get("Comment", "")
            icon_name = desktop_info.get("Icon", "")
            self.log(f"DEB desktop icon field: {icon_name or '-'}")
        else:
            result["name"] = self.default_name_from_file(deb_path)
            icon_name = ""

        icon_path = self.find_icon_in_extracted_tree(extract_dir, icon_name)
        if not icon_path:
            icon_path = self.find_first_image(extract_dir)

        if icon_path:
            result["icon_path"] = icon_path
        else:
            self.log("No DEB icon found. Falling back to installer icon if available.")

        return result

    # -------------------------
    # Install / uninstall selected package
    # -------------------------

    def install_appimage(self):
        if not self.ensure_file_selected():
            return
        if self.detect_file_type(self.selected_file) != "AppImage":
            messagebox.showerror("Wrong file type", "Please select an .AppImage file.")
            return

        self.analyze_selected_file()

        app_name = self.detected_name or self.default_name_from_file(self.selected_file)
        safe_name = self.slugify(app_name)
        version = self.detected_version or self.detect_app_version(self.selected_file, app_name)
        self.log(f"Detected version: {version or '-'}")

        existing_app = self.find_existing_installed_app(app_name)
        existing_version = existing_app.get("version", "") if existing_app else ""

        action = self.decide_install_action(
            app_name=app_name,
            new_version=version,
            existing_version=existing_version,
            source_label="AppImage"
        )

        if action == "cancel":
            self.log("User cancelled AppImage installation.")
            return

        self.log(f"AppImage action selected: {action}")

        target_appimage = os.path.join(INSTALL_DIR, f"{safe_name}.AppImage")
        shutil.copy2(self.selected_file, target_appimage)

        if not self.is_executable(target_appimage):
            self.make_file_executable(target_appimage)
            self.log(f"Made installed AppImage executable: {target_appimage}")

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

        self.add_appimage_to_manifest({
            "name": app_name,
            "slug": safe_name,
            "version": version,
            "source_file": os.path.abspath(self.selected_file),
            "installed_appimage": target_appimage,
            "desktop_file": desktop_path,
            "icon_file": installed_icon_path,
        })

        self.log(f"Installed AppImage to: {target_appimage}")
        self.log(f"Created launcher: {desktop_path}")
        if installed_icon_path:
            self.log(f"Installed icon: {installed_icon_path}")

        self.refresh_installed_apps()

        if action == "install":
            msg = f"{app_name} was installed.\n\nIt should appear in your app menu."
        elif action == "reinstall":
            msg = f"{app_name} was reinstalled."
        elif action == "upgrade":
            msg = f"{app_name} was updated."
        elif action == "downgrade":
            msg = f"{app_name} was replaced with an older version."
        else:
            msg = f"{app_name} was replaced."

        messagebox.showinfo("Installed", msg)

    def install_deb(self):
        if not self.ensure_file_selected():
            return
        if self.detect_file_type(self.selected_file) != "DEB package":
            messagebox.showerror("Wrong file type", "Please select a .deb file.")
            return

        deb_path = os.path.abspath(self.selected_file)
        deb_info = self.extract_deb_metadata(deb_path)

        app_name = deb_info.get("name") or self.default_name_from_file(deb_path)
        package_name = deb_info.get("package_name") or ""
        new_version = deb_info.get("version") or ""
        installed_version = self.get_installed_deb_version(package_name)

        self.log(f"DEB detected app name: {app_name}")
        self.log(f"DEB detected package name: {package_name or '-'}")
        self.log(f"DEB detected version: {new_version or '-'}")
        self.log(f"DEB installed version: {installed_version or '-'}")

        action = self.decide_install_action(
            app_name=app_name,
            new_version=new_version,
            existing_version=installed_version,
            source_label="DEB package"
        )

        if action == "cancel":
            self.log("User cancelled DEB installation.")
            return

        self.add_deb_to_manifest({
            "name": app_name,
            "package_name": package_name,
            "version": new_version,
            "source_file": deb_path,
            "source": "DEB",
        })

        if shutil.which("pkexec") and shutil.which("dpkg"):
            try:
                shell_cmd = f"dpkg -i '{deb_path}'; apt-get install -f -y"
                subprocess.Popen(["pkexec", "bash", "-c", shell_cmd])
                self.log(f"Started DEB install for: {deb_path}")
                self.log("Using primary method: dpkg -i ... ; apt-get install -f -y")
                self.refresh_installed_apps()
                messagebox.showinfo(
                    "Started",
                    f"{action.capitalize()} started using dpkg + apt-get fix."
                )
                return
            except Exception as e:
                self.log(f"Primary DEB install failed: {e}")
                messagebox.showerror("Install failed", str(e))
                return

        messagebox.showerror(
            "Missing tools",
            "This system does not have the required pkexec/dpkg tools."
        )

    def remove_installed_appimage_by_name(self, app_name):
        safe_name = self.slugify(app_name)
        removed = False

        manifest = self.load_manifest()
        new_manifest = []

        for item in manifest:
            if item.get("slug") == safe_name or item.get("name") == app_name:
                for path_key in ("installed_appimage", "desktop_file", "icon_file"):
                    path = item.get(path_key, "")
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                            self.log(f"Removed: {path}")
                            removed = True
                        except Exception as e:
                            self.log(f"Could not remove {path}: {e}")
            else:
                new_manifest.append(item)

        if not removed:
            candidates = [
                os.path.join(INSTALL_DIR, f"{safe_name}.AppImage"),
                os.path.join(DESKTOP_DIR, f"{safe_name}.desktop"),
            ]
            for ext in [".png", ".svg", ".xpm", ".ico"]:
                candidates.append(os.path.join(ICON_DIR, f"{safe_name}{ext}"))

            for path in candidates:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        self.log(f"Removed: {path}")
                        removed = True
                    except Exception as e:
                        self.log(f"Could not remove {path}: {e}")

        self.save_manifest(new_manifest)
        self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)
        self.refresh_installed_apps()

        if removed:
            messagebox.showinfo("Uninstalled", f"{app_name} was removed.")
        else:
            messagebox.showinfo("Nothing found", "No installed files were found for that app.")

    # -------------------------
    # Registration
    # -------------------------

    def auto_register_handler(self):
        self.register_as_handler()

    def register_as_handler(self):
        if self.is_handler_registered():
            self.log("Registration skipped (already registered).")
            return

        script_path = os.path.abspath(sys.argv[0])
        python_exec = sys.executable or "python3"
        desktop_path = os.path.join(DESKTOP_DIR, DESKTOP_FILE_NAME)

        installer_icon_name = "linux-app-installer"
        installer_icon_target = ""

        fallback_icon = self.get_fallback_icon()
        if fallback_icon:
            ext = os.path.splitext(fallback_icon)[1].lower() or ".png"
            installer_icon_target = os.path.join(
                ICON_DIR, f"{installer_icon_name}{ext}"
            )
            try:
                shutil.copy2(fallback_icon, installer_icon_target)
            except Exception as e:
                self.log(f"Could not copy installer icon: {e}")

        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(self.build_handler_desktop(
                script_path, python_exec, installer_icon_target)
            )
        os.chmod(desktop_path, 0o755)

        if shutil.which("xdg-mime"):
            self.try_run(["xdg-mime", "default", DESKTOP_FILE_NAME, APPIMAGE_MIME], check=False)
            self.try_run(["xdg-mime", "default", DESKTOP_FILE_NAME, DEB_MIME], check=False)

        self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)

        self.log(f"Registered handler desktop file: {desktop_path}")
        if installer_icon_target:
            self.log(f"Installer icon copied to: {installer_icon_target}")
        self.log("Associated Linux App Installer with AppImage and DEB MIME types.")

        messagebox.showinfo(
            "Registered",
            "Linux App Installer was registered.\n\nIts app-menu icon now uses "
            "your custom icon, and that same icon is the fallback for installed apps."
        )

    def unregister_as_handler(self):
        desktop_path = os.path.join(DESKTOP_DIR, DESKTOP_FILE_NAME)
        if os.path.exists(desktop_path):
            try:
                os.remove(desktop_path)
                self.log(f"Removed: {desktop_path}")
            except Exception as e:
                self.log(f"Could not remove desktop handler: {e}")

        for ext in [".png", ".svg", ".xpm", ".ico"]:
            installer_icon = os.path.join(ICON_DIR, f"linux-app-installer{ext}")
            if os.path.exists(installer_icon):
                try:
                    os.remove(installer_icon)
                    self.log(f"Removed: {installer_icon}")
                except Exception as e:
                    self.log(f"Could not remove icon {installer_icon}: {e}")

        self.try_run(["update-desktop-database", DESKTOP_DIR], check=False)
        messagebox.showinfo("Removed", "Linux App Installer registration was removed.")

    def is_handler_registered(self) -> bool:
        desktop_path = os.path.join(DESKTOP_DIR, DESKTOP_FILE_NAME)
        if not os.path.exists(desktop_path):
            return False

        if not shutil.which("xdg-mime"):
            return True

        try:
            for m in (APPIMAGE_MIME, DEB_MIME):
                out = subprocess.check_output(
                    ["xdg-mime", "query", "default", m],
                    text=True,
                    stderr=subprocess.DEVNULL
                ).strip()
                if out != DESKTOP_FILE_NAME:
                    return False
        except Exception:
            return False

        return True

    # -------------------------
    # Installed apps manager
    # -------------------------

    def refresh_installed_apps(self):
        self.installed_apps_cache = self.collect_installed_apps()
        self.populate_installed_apps_tree()
        self.update_selected_app_details()

    def populate_installed_apps_tree(self):
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""

        for item in self.apps_tree.get_children():
            self.apps_tree.delete(item)

        filtered = []
        for app in self.installed_apps_cache:
            haystack = " ".join([
                app.get("name", ""),
                app.get("version", ""),
                app.get("source", ""),
                app.get("desktop_file", ""),
                app.get("exec", ""),
                app.get("package_name", ""),
            ]).lower()

            if query and query not in haystack:
                continue
            filtered.append(app)

        for idx, app in enumerate(filtered):
            self.apps_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    app.get("name", ""),
                    app.get("version", ""),
                    app.get("source", ""),
                    app.get("desktop_file", ""),
                    app.get("exec", "")
                )
            )

    def update_selected_app_details(self):
        selected = self.get_selected_installed_app()
        if not selected:
            self.selected_app_details.set("No app selected.")
            return

        text = (
            f"Name: {selected.get('name', '-')}\n"
            f"Version: {selected.get('version', '-')}\n"
            f"Source: {selected.get('source', '-')}\n"
            f"Package name: {selected.get('package_name', '-')}\n"
            f"Desktop file: {selected.get('desktop_file', '-')}\n"
            f"Exec / Source file: {selected.get('exec', '-')}\n"
            f"Managed by installer: {'Yes' if selected.get('managed') else 'No'}\n"
            f"Uninstall method: {selected.get('uninstall_method', '-')}"
        )
        self.selected_app_details.set(text)

    def get_selected_installed_app(self):
        selection = self.apps_tree.selection()
        if not selection:
            return None

        selected_values = self.apps_tree.item(selection[0], "values")
        if not selected_values:
            return None

        name, version, source, desktop_file, exec_cmd = selected_values

        for app in self.installed_apps_cache:
            if (
                app.get("name", "") == name
                and app.get("version", "") == version
                and app.get("source", "") == source
                and app.get("desktop_file", "") == desktop_file
                and app.get("exec", "") == exec_cmd
            ):
                return app
        return None

    def uninstall_selected_installed_app(self):
        app = self.get_selected_installed_app()
        if not app:
            messagebox.showerror("No selection", "Please select an installed app first.")
            return

        name = app.get("name", "Unknown App")
        uninstall_method = app.get("uninstall_method", "")

        if not messagebox.askyesno("Uninstall", f"Remove '{name}'?"):
            return

        if uninstall_method == "manifest_appimage":
            self.remove_installed_appimage_by_name(name)
            return

        if uninstall_method == "system_deb":
            package_name = app.get("package_name", "")
            if not package_name:
                messagebox.showerror(
                    "Missing package name",
                    "This DEB entry has no package name, so it cannot be removed automatically."
                )
                return

            if shutil.which("pkexec") and shutil.which("apt"):
                try:
                    subprocess.Popen(["pkexec", "apt", "remove", "-y", package_name])
                    self.log(f"Started DEB uninstall: pkexec apt remove -y {package_name}")

                    manifest = [
                        x for x in self.load_deb_manifest()
                        if x.get("package_name") != package_name
                    ]
                    self.save_deb_manifest(manifest)
                    self.refresh_installed_apps()

                    messagebox.showinfo(
                        "Started",
                        f"Removal command started for package: {package_name}"
                    )
                    return
                except Exception as e:
                    self.log(f"DEB uninstall failed: {e}")
                    messagebox.showerror("Uninstall failed", str(e))
                    return

            messagebox.showerror(
                "Cannot uninstall",
                "Required tools for DEB removal were not found."
            )
            return

        messagebox.showerror("Unsupported", "Unknown uninstall method.")

    def collect_installed_apps(self):
        apps = []
        seen = set()

        for item in self.load_manifest():
            app = {
                "name": item.get("name", ""),
                "version": item.get("version", ""),
                "source": "AppImage",
                "desktop_file": item.get("desktop_file", ""),
                "exec": item.get("installed_appimage", ""),
                "managed": True,
                "uninstall_method": "manifest_appimage",
                "package_name": "",
            }
            key = (app["name"], app["source"], app["desktop_file"])
            if key not in seen:
                apps.append(app)
                seen.add(key)

        for item in self.load_deb_manifest():
            package_name = item.get("package_name", "")
            actual_version = self.get_installed_deb_version(package_name) if package_name else item.get("version", "")

            app = {
                "name": item.get("name", ""),
                "version": actual_version or item.get("version", ""),
                "source": "DEB",
                "desktop_file": package_name,
                "exec": item.get("source_file", ""),
                "managed": False,
                "uninstall_method": "system_deb",
                "package_name": package_name,
            }
            key = (app["name"], app["source"], app["desktop_file"])
            if key not in seen:
                apps.append(app)
                seen.add(key)

        apps.sort(key=lambda a: (a.get("name", "").lower(), a.get("source", "").lower()))
        return apps

    # -------------------------
    # Manifest
    # -------------------------

    def load_manifest(self):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def save_manifest(self, data):
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_appimage_to_manifest(self, item):
        manifest = self.load_manifest()

        filtered = []
        for existing in manifest:
            if existing.get("slug") != item.get("slug"):
                filtered.append(existing)

        filtered.append(item)
        self.save_manifest(filtered)

    def load_deb_manifest(self):
        try:
            with open(DEB_MANIFEST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def save_deb_manifest(self, data):
        with open(DEB_MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_deb_to_manifest(self, item):
        manifest = self.load_deb_manifest()
        filtered = []

        new_pkg = item.get("package_name", "")
        new_name = item.get("name", "")

        for existing in manifest:
            same_pkg = new_pkg and existing.get("package_name", "") == new_pkg
            same_name = new_name and existing.get("name", "") == new_name

            if not same_pkg and not same_name:
                filtered.append(existing)

        filtered.append(item)
        self.save_deb_manifest(filtered)

    # -------------------------
    # Desktop and icon helpers
    # -------------------------

    def build_app_desktop(self, app_name, comment, exec_path, icon_path):
        icon_value = icon_path if icon_path else "application-x-executable"
        return f"""[Desktop Entry]
Version=1.0
Type=Application
Name={app_name}
Comment={comment}
Exec="{exec_path}"
Icon={icon_value}
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
                    if key in ("Name", "Comment", "Icon", "Exec", "NoDisplay"):
                        data[key] = value.strip()
        except Exception:
            pass
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
                if low.endswith((".png", ".svg", ".xpm", ".ico")):
                    preferred.append(os.path.join(dirpath, name))

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
            elif "128x128" in low:
                s += 20
            elif "64x64" in low:
                s += 10
            if low.endswith(".png"):
                s += 10
            elif low.endswith(".svg"):
                s += 8
            return s

        preferred.sort(key=score, reverse=True)
        return preferred[0]

    def find_icon_in_extracted_tree(self, root_dir, icon_name):
        candidates = []
        wanted = (icon_name or "").lower().strip()
        wanted = os.path.basename(wanted) if wanted else ""

        for dirpath, _, filenames in os.walk(root_dir):
            for name in filenames:
                full_path = os.path.join(dirpath, name)
                file_base, file_ext = os.path.splitext(name)
                file_ext = file_ext.lower()

                if file_ext not in (".png", ".svg", ".xpm", ".ico"):
                    continue

                score = 0
                low_path = full_path.lower()
                low_base = file_base.lower()
                low_name = name.lower()

                if wanted:
                    if low_name == wanted:
                        score += 120
                    if low_base == wanted:
                        score += 100
                    if wanted in low_base:
                        score += 70

                if "/usr/share/icons/" in low_path:
                    score += 40
                if "/usr/share/pixmaps/" in low_path:
                    score += 35
                if "256x256" in low_path:
                    score += 30
                elif "128x128" in low_path:
                    score += 20
                elif "64x64" in low_path:
                    score += 10

                if file_ext == ".png":
                    score += 10
                elif file_ext == ".svg":
                    score += 8

                candidates.append((score, full_path))

        if not candidates:
            return ""

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # -------------------------
    # Utilities
    # -------------------------

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
        app.close_busy_dialog()
        app.cleanup_temp_dir()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()