from __future__ import annotations

import ctypes
import os
import queue
import threading
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from qb_rss_autodl import (
    DEFAULT_CONFIG,
    DEFAULT_LIMIT,
    QBittorrentClient,
    archive_candidates,
    archive_db_path,
    collect_search_candidates,
    load_config,
    load_state,
    planned_save_path,
    read_sources,
    record_downloads,
    title_matches,
)


class AppError(Exception):
    pass


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
CREDENTIAL_PREFIX = "AutoDownloadWithBT/qBittorrent"


def credential_target(url: str, username: str) -> str:
    return f"{CREDENTIAL_PREFIX}/{url.strip().rstrip('/')}/{username.strip()}"


def read_windows_credential(target: str) -> str:
    if os.name != "nt":
        return ""
    advapi = ctypes.WinDLL("Advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [wintypes.LPVOID]
    advapi.CredFree.restype = None
    credential = ctypes.POINTER(CREDENTIALW)()
    if not advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(credential)):
        return ""
    try:
        size = credential.contents.CredentialBlobSize
        if not size:
            return ""
        raw = ctypes.string_at(credential.contents.CredentialBlob, size)
        return raw.decode("utf-16-le")
    finally:
        advapi.CredFree(credential)


def write_windows_credential(target: str, username: str, password: str) -> None:
    if os.name != "nt" or not password:
        return
    advapi = ctypes.WinDLL("Advapi32", use_last_error=True)
    advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    blob = password.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob)
    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_byte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = username
    if not advapi.CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise OSError(error, "Failed to save password to Windows Credential Manager")


def toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_bool(value: bool) -> str:
    return "true" if value else "false"


def config_to_toml(config: dict[str, Any]) -> str:
    qbit = config.get("qbittorrent", {})
    archive = config.get("archive", {})
    lines: list[str] = [
        "[qbittorrent]",
        f"url = {toml_string(str(qbit.get('url', 'http://127.0.0.1:8080')))}",
        f"username = {toml_string(str(qbit.get('username', '')))}",
        f"password_env = {toml_string(str(qbit.get('password_env', 'QBIT_PASSWORD')))}",
        f"save_path = {toml_string(str(qbit.get('save_path', '')))}",
        f"category = {toml_string(str(qbit.get('category', '')))}",
        f"organize_by_title = {toml_bool(bool(qbit.get('organize_by_title', True)))}",
        f"folder_name_max_length = {int(qbit.get('folder_name_max_length', 120))}",
        f"remember_password = {toml_bool(bool(qbit.get('remember_password', True)))}",
        "",
        "[archive]",
        f"database = {toml_string(str(archive.get('database', 'archive.db')))}",
        f"include_in_search = {toml_bool(bool(archive.get('include_in_search', True)))}",
        f"daily_time = {toml_string(str(archive.get('daily_time', '12:00')))}",
        "",
    ]

    for source in config.get("sources", []):
        lines.extend(
            [
                "[[sources]]",
                f"name = {toml_string(str(source.get('name', '')))}",
                f"url = {toml_string(str(source.get('url', '')))}",
                f"enabled = {toml_bool(bool(source.get('enabled', True)))}",
                "",
            ]
        )

    for rule in config.get("rules", []):
        keywords = ", ".join(toml_string(str(item)) for item in rule.get("keywords", []))
        exclude = ", ".join(toml_string(str(item)) for item in rule.get("exclude", []))
        lines.extend(
            [
                "[[rules]]",
                f"name = {toml_string(str(rule.get('name', '')))}",
                f"enabled = {toml_bool(bool(rule.get('enabled', True)))}",
                f"keywords = [{keywords}]",
                f"exclude = [{exclude}]",
                f"limit = {int(rule.get('limit', DEFAULT_LIMIT))}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(config_to_toml(config), encoding="utf-8")


class RssAutodlGui(tk.Tk):
    def __init__(self, config_path: Path = DEFAULT_CONFIG) -> None:
        super().__init__()
        self.title("qBittorrent RSS Auto Download")
        self.geometry("1120x720")
        self.minsize(960, 620)

        self.config_path = config_path
        self.task_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.candidates: list[Any] = []

        self.config_data = self.load_or_default_config()
        self.build_variables()
        self.build_ui()
        self.refresh_sources()
        self.after(100, self.process_queue)
        self.after(700, self.auto_check_qbit)

    def load_or_default_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            return load_config(self.config_path)
        return {
            "qbittorrent": {
                "url": "http://127.0.0.1:8080",
                "username": "",
                "password_env": "QBIT_PASSWORD",
                "save_path": str(Path.home() / "Downloads"),
                "category": "",
                "organize_by_title": True,
                "folder_name_max_length": 120,
                "remember_password": True,
            },
            "archive": {"database": "archive.db", "include_in_search": True, "daily_time": "12:00"},
            "sources": [],
            "rules": [],
        }

    def build_variables(self) -> None:
        qbit = self.config_data.setdefault("qbittorrent", {})
        archive = self.config_data.setdefault("archive", {})
        self.qbit_url_var = tk.StringVar(value=str(qbit.get("url", "http://127.0.0.1:8080")))
        self.qbit_user_var = tk.StringVar(value=str(qbit.get("username", "")))
        remembered_password = read_windows_credential(
            credential_target(str(qbit.get("url", "")), str(qbit.get("username", "")))
        )
        self.qbit_password_var = tk.StringVar(
            value=os.environ.get(str(qbit.get("password_env", "QBIT_PASSWORD")), remembered_password)
        )
        self.save_path_var = tk.StringVar(value=str(qbit.get("save_path", "")))
        self.category_var = tk.StringVar(value=str(qbit.get("category", "")))
        self.organize_var = tk.BooleanVar(value=bool(qbit.get("organize_by_title", True)))
        self.remember_password_var = tk.BooleanVar(value=bool(qbit.get("remember_password", True)))
        self.include_archive_var = tk.BooleanVar(value=bool(archive.get("include_in_search", True)))
        self.query_var = tk.StringVar()
        self.include_var = tk.StringVar()
        self.exclude_var = tk.StringVar()
        self.limit_var = tk.IntVar(value=DEFAULT_LIMIT)
        self.status_var = tk.StringVar(value="Ready.")

    def build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        settings = ttk.LabelFrame(root, text="Settings", padding=8)
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        ttk.Label(settings, text="qBittorrent URL").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.qbit_url_var).grid(row=0, column=1, sticky=tk.EW, pady=3)
        ttk.Label(settings, text="Username").grid(row=0, column=2, sticky=tk.W, padx=(12, 6), pady=3)
        ttk.Entry(settings, textvariable=self.qbit_user_var, width=24).grid(row=0, column=3, sticky=tk.EW, pady=3)

        ttk.Label(settings, text="Password").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.qbit_password_var, show="*").grid(row=1, column=1, sticky=tk.EW, pady=3)
        ttk.Label(settings, text="Category").grid(row=1, column=2, sticky=tk.W, padx=(12, 6), pady=3)
        ttk.Entry(settings, textvariable=self.category_var, width=24).grid(row=1, column=3, sticky=tk.EW, pady=3)

        ttk.Label(settings, text="Download Root").grid(row=2, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.save_path_var).grid(row=2, column=1, sticky=tk.EW, pady=3)
        ttk.Button(settings, text="Browse", command=self.browse_save_path).grid(row=2, column=2, sticky=tk.W, padx=(12, 6), pady=3)
        ttk.Checkbutton(settings, text="Organize by title", variable=self.organize_var).grid(
            row=2, column=3, sticky=tk.W, pady=3
        )
        ttk.Checkbutton(settings, text="Remember password and auto-login", variable=self.remember_password_var).grid(
            row=3, column=1, sticky=tk.W, pady=3
        )

        settings_buttons = ttk.Frame(settings)
        settings_buttons.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(8, 0))
        ttk.Button(settings_buttons, text="Save Settings", command=self.save_settings).pack(side=tk.LEFT)
        ttk.Button(settings_buttons, text="Check qBittorrent", command=self.check_qbit).pack(side=tk.LEFT, padx=6)
        ttk.Button(settings_buttons, text="Archive RSS Now", command=self.archive_now).pack(side=tk.LEFT)

        body = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        sources_frame = ttk.LabelFrame(body, text="RSS Sources", padding=8)
        body.add(sources_frame, weight=1)
        sources_frame.rowconfigure(0, weight=1)
        sources_frame.columnconfigure(0, weight=1)

        self.sources_tree = ttk.Treeview(sources_frame, columns=("enabled", "url"), show="tree headings", selectmode="browse")
        self.sources_tree.heading("#0", text="Name")
        self.sources_tree.heading("enabled", text="Enabled")
        self.sources_tree.heading("url", text="URL")
        self.sources_tree.column("#0", width=150)
        self.sources_tree.column("enabled", width=70, anchor=tk.CENTER)
        self.sources_tree.column("url", width=300)
        self.sources_tree.grid(row=0, column=0, sticky=tk.NSEW)
        source_scroll = ttk.Scrollbar(sources_frame, orient=tk.VERTICAL, command=self.sources_tree.yview)
        self.sources_tree.configure(yscrollcommand=source_scroll.set)
        source_scroll.grid(row=0, column=1, sticky=tk.NS)

        source_buttons = ttk.Frame(sources_frame)
        source_buttons.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
        ttk.Button(source_buttons, text="Add", command=self.add_source_dialog).pack(side=tk.LEFT)
        ttk.Button(source_buttons, text="Toggle", command=self.toggle_selected_source).pack(side=tk.LEFT, padx=6)
        ttk.Button(source_buttons, text="Remove", command=self.remove_selected_source).pack(side=tk.LEFT)

        search_frame = ttk.LabelFrame(body, text="Search and Download", padding=8)
        body.add(search_frame, weight=3)
        search_frame.rowconfigure(2, weight=1)
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Title").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(search_frame, textvariable=self.query_var).grid(row=0, column=1, sticky=tk.EW, pady=3)
        ttk.Label(search_frame, text="Limit").grid(row=0, column=2, sticky=tk.W, padx=(12, 6), pady=3)
        ttk.Spinbox(search_frame, textvariable=self.limit_var, from_=1, to=200, width=8).grid(row=0, column=3, sticky=tk.W, pady=3)

        ttk.Label(search_frame, text="Must include").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(search_frame, textvariable=self.include_var).grid(row=1, column=1, sticky=tk.EW, pady=3)
        ttk.Label(search_frame, text="Exclude").grid(row=1, column=2, sticky=tk.W, padx=(12, 6), pady=3)
        ttk.Entry(search_frame, textvariable=self.exclude_var).grid(row=1, column=3, sticky=tk.EW, pady=3)

        self.results_tree = ttk.Treeview(
            search_frame,
            columns=("source", "published", "savepath", "url"),
            show="tree headings",
            selectmode="extended",
        )
        self.results_tree.heading("#0", text="Title")
        self.results_tree.heading("source", text="Source")
        self.results_tree.heading("published", text="Published")
        self.results_tree.heading("savepath", text="Save Path")
        self.results_tree.heading("url", text="URL")
        self.results_tree.column("#0", width=720, stretch=False)
        self.results_tree.column("source", width=110, stretch=False)
        self.results_tree.column("published", width=210, stretch=False)
        self.results_tree.column("savepath", width=520, stretch=False)
        self.results_tree.column("url", width=520, stretch=False)
        self.results_tree.grid(row=2, column=0, columnspan=4, sticky=tk.NSEW, pady=(8, 0))
        result_scroll = ttk.Scrollbar(search_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        result_xscroll = ttk.Scrollbar(search_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=result_scroll.set, xscrollcommand=result_xscroll.set)
        result_scroll.grid(row=2, column=4, sticky=tk.NS, pady=(8, 0))
        result_xscroll.grid(row=3, column=0, columnspan=4, sticky=tk.EW)

        actions = ttk.Frame(search_frame)
        actions.grid(row=4, column=0, columnspan=5, sticky=tk.EW, pady=(8, 0))
        ttk.Checkbutton(actions, text="Search archive", variable=self.include_archive_var).pack(side=tk.LEFT)
        ttk.Button(actions, text="Search", command=self.search).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="Add Selected", command=self.add_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="Clear Results", command=self.clear_results).pack(side=tk.LEFT, padx=8)

        ttk.Label(root, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, pady=(8, 0))

    def current_config(self) -> dict[str, Any]:
        config = dict(self.config_data)
        config["qbittorrent"] = {
            "url": self.qbit_url_var.get().strip(),
            "username": self.qbit_user_var.get().strip(),
            "password_env": str(self.config_data.get("qbittorrent", {}).get("password_env", "QBIT_PASSWORD")),
            "save_path": self.save_path_var.get().strip(),
            "category": self.category_var.get().strip(),
            "organize_by_title": bool(self.organize_var.get()),
            "folder_name_max_length": int(self.config_data.get("qbittorrent", {}).get("folder_name_max_length", 120)),
            "remember_password": bool(self.remember_password_var.get()),
        }
        archive = dict(self.config_data.get("archive", {}))
        archive["include_in_search"] = bool(self.include_archive_var.get())
        config["archive"] = archive
        config["sources"] = list(self.config_data.get("sources", []))
        config["rules"] = list(self.config_data.get("rules", []))
        return config

    def save_settings(self) -> None:
        self.config_data = self.current_config()
        save_config(self.config_path, self.config_data)
        self.save_remembered_password()
        self.status_var.set(f"Saved settings to {self.config_path}.")

    def save_remembered_password(self) -> None:
        if not self.remember_password_var.get():
            return
        password = self.qbit_password_var.get()
        if not password:
            return
        qbit = self.current_config()["qbittorrent"]
        write_windows_credential(
            credential_target(str(qbit["url"]), str(qbit["username"])),
            str(qbit["username"]),
            password,
        )

    def browse_save_path(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.save_path_var.get() or str(Path.home()))
        if selected:
            self.save_path_var.set(selected)

    def refresh_sources(self) -> None:
        self.sources_tree.delete(*self.sources_tree.get_children())
        for index, source in enumerate(self.config_data.get("sources", [])):
            enabled = "yes" if source.get("enabled", True) else "no"
            self.sources_tree.insert("", tk.END, iid=str(index), text=source.get("name", ""), values=(enabled, source.get("url", "")))

    def add_source_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add RSS Source")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        name_var = tk.StringVar()
        url_var = tk.StringVar()

        ttk.Label(dialog, text="Name").grid(row=0, column=0, sticky=tk.W, padx=10, pady=(10, 4))
        ttk.Entry(dialog, textvariable=name_var, width=52).grid(row=0, column=1, padx=10, pady=(10, 4))
        ttk.Label(dialog, text="RSS URL").grid(row=1, column=0, sticky=tk.W, padx=10, pady=4)
        ttk.Entry(dialog, textvariable=url_var, width=52).grid(row=1, column=1, padx=10, pady=4)

        def submit() -> None:
            name = name_var.get().strip()
            url = url_var.get().strip()
            if not name or not url:
                messagebox.showerror("Missing Source", "Name and RSS URL are required.", parent=dialog)
                return
            sources = self.config_data.setdefault("sources", [])
            if any(source.get("name") == name for source in sources):
                messagebox.showerror("Duplicate Source", "A source with this name already exists.", parent=dialog)
                return
            sources.append({"name": name, "url": url, "enabled": True})
            self.save_settings()
            self.refresh_sources()
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=2, column=0, columnspan=2, sticky=tk.E, padx=10, pady=10)
        ttk.Button(buttons, text="Add", command=submit).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=(6, 0))

    def selected_source_index(self) -> int | None:
        selection = self.sources_tree.selection()
        if not selection:
            return None
        return int(selection[0])

    def toggle_selected_source(self) -> None:
        index = self.selected_source_index()
        if index is None:
            return
        source = self.config_data["sources"][index]
        source["enabled"] = not bool(source.get("enabled", True))
        self.save_settings()
        self.refresh_sources()

    def remove_selected_source(self) -> None:
        index = self.selected_source_index()
        if index is None:
            return
        source = self.config_data["sources"][index]
        if not messagebox.askyesno("Remove Source", f"Remove RSS source '{source.get('name', '')}'?"):
            return
        del self.config_data["sources"][index]
        self.save_settings()
        self.refresh_sources()

    def run_worker(self, label: str, work: Callable[[], Any]) -> None:
        self.status_var.set(label)

        def target() -> None:
            try:
                self.task_queue.put(("ok", work()))
            except Exception as exc:
                self.task_queue.put(("error", exc))

        threading.Thread(target=target, daemon=True).start()

    def process_queue(self) -> None:
        try:
            while True:
                kind, payload = self.task_queue.get_nowait()
                if kind == "ok":
                    callback, result = payload
                    callback(result)
                else:
                    self.status_var.set("Error.")
                    messagebox.showerror("Error", str(payload))
        except queue.Empty:
            pass
        self.after(100, self.process_queue)

    def split_words(self, value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.replace(";", ",").split(",") if item.strip())

    def search(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Missing Title", "Enter a title or keyword to search.")
            return
        self.save_settings()
        config = self.current_config()
        state_path = self.config_path.parent / "state.json"

        def work() -> tuple[Callable[[list[Any]], None], list[Any]]:
            state = load_state(state_path)
            candidates = collect_search_candidates(
                config,
                read_sources(config),
                state,
                ignore_state=False,
                no_archive=not bool(self.include_archive_var.get()),
            )
            keywords = self.split_words(self.include_var.get()) + (query,)
            exclude = self.split_words(self.exclude_var.get())
            matches = [item for item in candidates if title_matches(item.title, keywords, exclude)]
            return self.show_results, matches[: int(self.limit_var.get())]

        self.run_worker("Searching RSS and archive...", work)

    def show_results(self, candidates: list[Any]) -> None:
        self.candidates = candidates
        self.results_tree.delete(*self.results_tree.get_children())
        config = self.current_config()
        qbit = config["qbittorrent"]
        for index, item in enumerate(candidates):
            self.results_tree.insert(
                "",
                tk.END,
                iid=str(index),
                text=item.title,
                values=(item.source, item.published, planned_save_path(qbit, item), item.url),
            )
        self.status_var.set(f"Found {len(candidates)} candidate(s).")

    def selected_candidates(self) -> list[Any]:
        selected = []
        for iid in self.results_tree.selection():
            selected.append(self.candidates[int(iid)])
        return selected

    def add_selected(self) -> None:
        selected = self.selected_candidates()
        if not selected:
            messagebox.showerror("No Selection", "Select one or more candidates first.")
            return
        if not messagebox.askyesno("Confirm Download", f"Add {len(selected)} selected item(s) to qBittorrent?"):
            return
        self.save_settings()
        config = self.current_config()
        qbit = config["qbittorrent"]
        password = self.qbit_password()
        if not password:
            messagebox.showerror("Missing Password", "Enter the qBittorrent password or set QBIT_PASSWORD.")
            return
        state_path = self.config_path.parent / "state.json"

        def work() -> tuple[Callable[[int], None], int]:
            state = load_state(state_path)
            client = QBittorrentClient(str(qbit["url"]), str(qbit["username"]), password)
            client.login()
            for item in selected:
                save_path = planned_save_path(qbit, item)
                if save_path:
                    Path(save_path).mkdir(parents=True, exist_ok=True)
                client.add_urls([item.url], save_path=save_path, category=str(qbit.get("category", "")))
            record_downloads(state_path, state, selected)
            return self.download_complete, len(selected)

        self.run_worker("Adding selected items to qBittorrent...", work)

    def download_complete(self, count: int) -> None:
        self.status_var.set(f"Added {count} item(s) to qBittorrent.")
        messagebox.showinfo("Added", f"Added {count} item(s) to qBittorrent.")

    def qbit_password(self) -> str:
        qbit = self.current_config()["qbittorrent"]
        return (
            self.qbit_password_var.get()
            or os.environ.get(str(qbit.get("password_env", "QBIT_PASSWORD")), "")
            or read_windows_credential(credential_target(str(qbit.get("url", "")), str(qbit.get("username", ""))))
        )

    def check_qbit(self, show_message: bool = True) -> None:
        self.save_settings()
        qbit = self.current_config()["qbittorrent"]
        password = self.qbit_password()
        if not password:
            if show_message:
                messagebox.showerror("Missing Password", "Enter the qBittorrent password or set QBIT_PASSWORD.")
            return

        def work() -> tuple[Callable[[str], None], str]:
            client = QBittorrentClient(str(qbit["url"]), str(qbit["username"]), password)
            try:
                client.login()
            except Exception as exc:
                if not show_message:
                    return self.set_status_text, f"qBittorrent auto-login failed: {exc}"
                raise
            if show_message:
                return self.set_status_message, "qBittorrent login OK. Password will be remembered."
            return self.set_status_text, "qBittorrent auto-login OK."

        self.run_worker("Checking qBittorrent login...", work)

    def auto_check_qbit(self) -> None:
        if self.qbit_password():
            self.check_qbit(show_message=False)

    def archive_now(self) -> None:
        self.save_settings()
        config = self.current_config()

        def work() -> tuple[Callable[[str], None], str]:
            candidates = collect_search_candidates(
                config,
                read_sources(config),
                {"downloads": []},
                ignore_state=True,
                no_archive=True,
            )
            result = archive_candidates(archive_db_path(config), candidates)
            return self.set_status_message, (
                f"Archived {result.total} RSS item(s): {result.inserted} new, "
                f"{result.updated} duplicate/update."
            )

        self.run_worker("Archiving RSS items...", work)

    def clear_results(self) -> None:
        self.candidates = []
        self.results_tree.delete(*self.results_tree.get_children())
        self.status_var.set("Cleared results.")

    def set_status_message(self, message: str) -> None:
        self.status_var.set(message)
        messagebox.showinfo("Status", message)

    def set_status_text(self, message: str) -> None:
        self.status_var.set(message)


def main() -> None:
    app = RssAutodlGui()
    app.mainloop()


if __name__ == "__main__":
    main()
