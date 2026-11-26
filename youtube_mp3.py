"""YouTube -> MP3 downloader (Tkinter GUI + yt-dlp + ffmpeg).

GUI mode (default):  python youtube_mp3.py
Command-line mode:   python youtube_mp3.py --url LINK [--url ...]
                     [--out DIR] [--quality 320|192|128] [--playlist]

The command-line mode prints progress to the console and returns
exit code 0 on full success, 1 otherwise. It is intended both for
humans and for agents (Codex etc.) controlling the program.
"""

import argparse
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

DARK_BG = "#1e1e2e"
PANEL_BG = "#181825"
DISPLAY_BG = "#11111b"
TEXT_FG = "#cdd6f4"
SUBTLE_FG = "#a6adc8"
ACCENT_FG = "#11111b"
BUTTON_BG = "#313244"
BUTTON_ACTIVE = "#45475a"
GREEN = "#a6e3a1"
RED = "#f38ba8"
BLUE = "#89b4fa"
PURPLE = "#cba6f7"
YELLOW = "#f9e2af"
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_MED = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 10)
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Music")


def app_base_dir() -> str:
    """Folder of the running exe (frozen) or of this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg_dir() -> str:
    """Directory that must be passed to yt-dlp as ffmpeg_location."""
    candidates = [
        os.path.join(app_base_dir(), "ffmpeg"),
        app_base_dir(),
    ]
    for cand in candidates:
        if os.path.exists(os.path.join(cand, "ffmpeg.exe")):
            return cand
    return ""  # fall back to PATH


def build_ydl_opts(outdir: str, quality: str, playlist: bool,
                   ffdir: str, on_hook) -> dict:
    """Common yt-dlp options for GUI and CLI downloads."""
    return {
        "format": "bestaudio/best",
        "noplaylist": not playlist,
        "outtmpl": os.path.join(outdir, "%(title)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [on_hook],
        "ffmpeg_location": ffdir or None,
        "ignoreerrors": False,
    }


def download_links(links, outdir: str, quality: str, playlist: bool,
                   report) -> list:
    """Download links; report(event dict) receives progress.

    Returns a list of (link, ok, message) tuples.
    """
    ffdir = find_ffmpeg_dir()
    results = []

    def hook(data: dict, prefix: str) -> None:
        report({"type": "hook", "prefix": prefix, "data": data})

    for index, link in enumerate(links, 1):
        prefix = f"[{index}/{len(links)}]"
        report({"type": "status", "prefix": prefix, "state": "fetch"})
        try:
            opts = build_ydl_opts(
                outdir, quality, playlist, ffdir,
                lambda d, pre=prefix: hook(d, pre))
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([link])
        except Exception as exc:                               # noqa: BLE001
            report({"type": "status", "prefix": prefix, "state": "error",
                    "message": str(exc)})
            results.append((link, False, str(exc)))
            continue
        report({"type": "status", "prefix": prefix, "state": "done"})
        results.append((link, True, "ok"))
    return results


def run_cli() -> int:
    """Agent-facing command-line mode. Output is ASCII English on purpose:
    console codepages (cp866/cp1251) garble Cyrillic, so keep it safe."""
    parser = argparse.ArgumentParser(
        description="Download YouTube audio as mp3.",
        epilog="Example: python youtube_mp3.py --url "
               "https://www.youtube.com/watch?v=jNQXAC9IVRw --out D:\\Music")
    parser.add_argument("urls", nargs="*", help="YouTube links")
    parser.add_argument("-u", "--url", action="append", default=[],
                        help="YouTube link (repeatable)")
    parser.add_argument("-o", "--out", default=DEFAULT_DIR,
                        help=f"Folder for mp3 files (default {DEFAULT_DIR})")
    parser.add_argument("-q", "--quality", choices=("320", "192", "128"),
                        default="192", help="mp3 bitrate (default 192)")
    parser.add_argument("-p", "--playlist", action="store_true",
                        help="Download the whole playlist")
    args = parser.parse_args()
    links = args.urls + args.url
    if not links:
        parser.error("no links given: python youtube_mp3.py --url LINK")
    if yt_dlp is None:
        print("ERROR: yt-dlp is not installed (pip install yt-dlp)",
              file=sys.stderr)
        return 2

    statuses = {"fetch": "Fetching video info...", "done": "Downloaded"}
    def report(event: dict) -> None:
        prefix = event.get("prefix") or ""
        data = event.get("data") or {}
        if event["type"] == "hook":
            if data.get("status") == "downloading":
                total = (data.get("total_bytes")
                         or data.get("total_bytes_estimate") or 0)
                done = data.get("downloaded_bytes") or 0
                if total:
                    print(f"\r{prefix} {done / 1e6:6.1f} / {total / 1e6:6.1f}"
                          f" MB ({done / total * 100:3.0f}%)",
                          end="", flush=True)
            elif data.get("status") == "finished":
                print(f"\r{prefix} Converting to mp3...", flush=True)
        else:
            state = event.get("state")
            if state == "error":
                print(f"{prefix} FAILED: {event.get('message', '')}")
            else:
                print(f"{prefix + ' ' if prefix else ''}"
                      f"{statuses.get(state, '')}".rstrip())

    os.makedirs(args.out, exist_ok=True)
    results = download_links(links, args.out, args.quality, args.playlist,
                             report)
    failed = [r for r in results if not r[1]]
    print(f"\nRESULT: downloaded {len(results) - len(failed)} of "
          f"{len(results)}")
    for link, ok, message in failed:
        print(f"  FAILED {link}: {message}")
    return 1 if failed else 0


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube -> MP3")
        self.configure(bg=DARK_BG, padx=14, pady=14)
        self.resizable(False, False)
        self.events = queue.Queue()
        self.downloading = False

        self.build_ui()
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)
        self.maxsize(width, height)
        self.after(100, self.poll_events)

    # ----------------------------------------------------------------- UI

    def build_ui(self) -> None:
        title = tk.Label(self, text="Скачивание mp3 с YouTube",
                         font=FONT_TITLE, bg=DARK_BG, fg=TEXT_FG)
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        urls_label = tk.Label(self, text="Ссылки (по одной в строке):",
                              font=FONT_MED, bg=DARK_BG, fg=SUBTLE_FG)
        urls_label.grid(row=1, column=0, columnspan=2, sticky="w")

        self.urls = tk.Text(self, height=4, width=56, font=FONT_MONO,
                            bg=DISPLAY_BG, fg=TEXT_FG, insertbackground=TEXT_FG,
                            relief="flat", highlightthickness=1,
                            highlightbackground=BUTTON_BG, padx=8, pady=6)
        self.urls.grid(row=2, column=0, columnspan=2, sticky="we",
                       pady=(4, 10))

        folder_label = tk.Label(self, text="Папка для mp3:",
                                font=FONT_MED, bg=DARK_BG, fg=SUBTLE_FG)
        folder_label.grid(row=3, column=0, sticky="w")
        self.folder_var = tk.StringVar(value=DEFAULT_DIR)
        self.folder_entry = tk.Entry(self, textvariable=self.folder_var,
                                     width=38, font=FONT_MONO, bg=DISPLAY_BG,
                                     fg=TEXT_FG, insertbackground=TEXT_FG,
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=BUTTON_BG)
        self.folder_entry.grid(row=4, column=0, sticky="we", pady=4)
        browse = tk.Button(self, text="Обзор...", font=FONT_MED, bg=BUTTON_BG,
                           fg=TEXT_FG, activebackground=BUTTON_ACTIVE,
                           activeforeground=TEXT_FG, relief="flat",
                           padx=12, pady=4, command=self.choose_folder)
        browse.grid(row=4, column=1, sticky="we", padx=(8, 0))

        quality_row = tk.Frame(self, bg=DARK_BG)
        quality_row.grid(row=5, column=0, sticky="w", pady=(10, 0))
        q_label = tk.Label(quality_row, text="Качество:",
                           font=FONT_MED, bg=DARK_BG, fg=SUBTLE_FG)
        q_label.pack(side="left")
        self.quality = tk.StringVar(value="192")
        for value in ("320", "192", "128"):
            btn = tk.Radiobutton(
                quality_row, text=value + " kbps", variable=self.quality,
                value=value, font=FONT_MED, bg=DARK_BG, fg=TEXT_FG,
                selectcolor=DISPLAY_BG, activebackground=DARK_BG,
                activeforeground=TEXT_FG, highlightthickness=0,
                indicatoron=False, padx=10, pady=3,
            )
            btn.pack(side="left", padx=4)

        self.playlist_var = tk.BooleanVar(value=False)
        self.playlist_check = tk.Checkbutton(
            self, text="Скачивать плейлист целиком", variable=self.playlist_var,
            font=FONT_MED, bg=DARK_BG, fg=TEXT_FG, selectcolor=DISPLAY_BG,
            activebackground=DARK_BG, activeforeground=TEXT_FG,
            highlightthickness=0,
        )
        self.playlist_check.grid(row=6, column=0, sticky="w", pady=(6, 0))

        self.go_button = tk.Button(
            self, text="Скачать MP3", font=("Segoe UI", 12, "bold"),
            bg=GREEN, fg=ACCENT_FG, activebackground=BUTTON_ACTIVE,
            activeforeground=ACCENT_FG, relief="flat", padx=14, pady=8,
            command=self.start_download,
        )
        self.go_button.grid(row=7, column=0, columnspan=2, sticky="we",
                            pady=(12, 0))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=DISPLAY_BG,
                        background=PURPLE, bordercolor=DARK_BG,
                        lightcolor=PURPLE, darkcolor=PURPLE)
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100,
                                        style="TProgressbar")
        self.progress.grid(row=8, column=0, columnspan=2, sticky="we",
                           pady=(10, 0))

        self.status = tk.Label(self, text="Готово к работе", font=FONT_MED,
                               bg=DARK_BG, fg=SUBTLE_FG, anchor="w",
                               wraplength=420, justify="left")
        self.status.grid(row=9, column=0, columnspan=2, sticky="we",
                         pady=(8, 0))
        if yt_dlp is None:
            self.set_status("Библиотека yt-dlp не установлена: pip install "
                            "yt-dlp", RED)

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(
            initialdir=self.folder_var.get() or os.path.expanduser("~"))
        if chosen:
            self.folder_var.set(os.path.normpath(chosen))

    def set_status(self, text: str, color: str = SUBTLE_FG) -> None:
        self.status.configure(text=text, fg=color)

    # ------------------------------------------------------------ download

    def start_download(self) -> None:
        if self.downloading:
            return
        if yt_dlp is None:
            self.set_status("Нет модуля yt-dlp; установите: pip install "
                            "yt-dlp", RED)
            return
        links = [line.strip() for line in
                 self.urls.get("1.0", "end").splitlines() if line.strip()]
        outdir = self.folder_var.get().strip()
        if not links:
            self.set_status("Вставьте хотя бы одну ссылку", RED)
            return
        if not outdir:
            self.set_status("Укажите папку для сохранения", RED)
            return
        os.makedirs(outdir, exist_ok=True)
        self.downloading = True
        self.go_button.configure(text="Скачиваю...", state="disabled",
                                 bg=BUTTON_BG)
        thread = threading.Thread(
            target=self.download_thread,
            args=(links, outdir, self.quality.get(), self.playlist_var.get()),
            daemon=True)
        thread.start()

    def download_thread(self, links, outdir, quality, playlist) -> None:
        def report(event: dict) -> None:
            self.events.put(event)

        results = download_links(links, outdir, quality, playlist, report)
        self.events.put({"type": "done", "results": results})

    # -------------------------------------------------------------- events

    def poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event["type"] == "hook":
                    self.on_hook(event["prefix"], event["data"])
                elif event["type"] == "status":
                    state = event.get("state")
                    prefix = event.get("prefix") or ""
                    text = {"fetch": "Получаю данные о видео...",
                            "done": "Скачано"}.get(state, "")
                    color = {"fetch": YELLOW, "done": GREEN}.get(state,
                                                                 SUBTLE_FG)
                    if state == "error":
                        text = f"Ошибка: {event.get('message', '')}"
                        color = RED
                    self.set_status((prefix + " " if prefix else "") + text,
                                    color)
                elif event["type"] == "done":
                    results = event["results"]
                    failed = [r for r in results if not r[1]]
                    self.downloading = False
                    self.go_button.configure(text="Скачать MP3",
                                             state="normal", bg=GREEN)
                    self.progress.configure(value=0)
                    if failed:
                        self.set_status(
                            f"Готово с ошибками: {len(results) - len(failed)}"
                            f" из {len(results)}", RED)
                    else:
                        self.set_status("Готово", GREEN)
        except queue.Empty:
            pass
        self.after(100, self.poll_events)

    def on_hook(self, prefix: str, data: dict) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done_bytes = data.get("downloaded_bytes") or 0
            if total:
                percent = done_bytes / total * 100
                self.progress.configure(value=percent)
            self.set_status(prefix + " Скачиваю: "
                            f"{done_bytes / 1e6:.1f} МБ")
        elif data.get("status") == "finished":
            self.set_status(prefix + " Конвертирую в mp3...", YELLOW)
            self.progress.configure(value=100)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(run_cli())
    DownloaderApp().mainloop()
