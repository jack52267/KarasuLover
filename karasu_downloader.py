#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Karasu Downloader - Windows GUI (PyInstaller 單一 EXE 版)
預設載入 karasu_urls.txt，使用者只需載入 Cookie 即可下載
"""

import os
import sys
import platform
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import datetime
import shutil

def resource_path(relative_path):
    """取得打包後或開發時的資源路徑"""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / relative_path

def get_system_info():
    arch = platform.machine().lower()
    is_64 = arch in ("amd64", "x86_64", "arm64")
    return f"{'64位元' if is_64 else '32位元'} ({platform.machine()})"

def get_stable_tools_dir():
    """取得固定的工具目錄（%APPDATA%\\KarasuLover\\tools）"""
    appdata = os.environ.get("APPDATA", str(Path.home()))
    tools_dir = Path(appdata) / "KarasuLover" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return tools_dir

def ensure_tool(name):
    """確保工具存在於固定目錄，不存在或檔案過小則從打包資源複製"""
    stable = get_stable_tools_dir() / name
    # 如果已存在且大小合理（> 100KB），直接使用
    if stable.exists() and stable.stat().st_size > 100 * 1024:
        return stable
    # 從打包資源複製
    bundled = resource_path(f"tools/{name}")
    if bundled.exists() and bundled.stat().st_size > 100 * 1024:
        try:
            shutil.copy2(bundled, stable)
            print(f"[KarasuLover] 已複製工具：{name} ({bundled.stat().st_size // 1024} KB)")
            return stable
        except Exception:
            pass
    # 回傳可用的路徑（即使不理想）
    if stable.exists():
        return stable
    return bundled if bundled.exists() else stable

YTDLP = ensure_tool("yt-dlp.exe")
DENO = ensure_tool("deno.exe")
NODE = ensure_tool("node.exe")
DEFAULT_URLS = resource_path("karasu_urls_with_title.txt")
TITLES_FILE = resource_path("karasu_urls_with_title.txt")

class KarasuDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KarasuLover")
        self.geometry("980x780")
        self.minsize(900, 680)
        self.configure(bg="#1a1a1a")

        # 黑銀夜烏深色主題
        style = ttk.Style()
        style.theme_use("clam")
        # 設定預設字型支援中文
        default_font = ("Microsoft JhengHei", 9)
        style.configure(".", background="#1a1a1a", foreground="#e0e0e0", fieldbackground="#2d2d2d", font=default_font)
        style.configure("TLabel", background="#1a1a1a", foreground="#e0e0e0")
        style.configure("TFrame", background="#1a1a1a")
        style.configure("TLabelframe", background="#1a1a1a", foreground="#c0c0c0")
        style.configure("TLabelframe.Label", background="#1a1a1a", foreground="#c0c0c0")
        style.configure("TButton", background="#3a3a3a", foreground="#e0e0e0", padding=6)
        style.map("TButton", background=[("active", "#4a4a4a")])
        style.configure("TEntry", fieldbackground="#2d2d2d", foreground="#ffffff")
        style.configure("TCheckbutton", background="#1a1a1a", foreground="#e0e0e0")
        style.configure("Dark.TFrame", background="#1a1a1a")
        style.configure("Dark.TCheckbutton", background="#1a1a1a", foreground="#e0e0e0")
        style.map("Dark.TCheckbutton", 
                  background=[("active", "#3a2020"), ("selected", "#5a2828")],
                  foreground=[("active", "#ffdddd"), ("selected", "#ffcccc")])
        style.configure("Horizontal.TProgressbar", background="#8b3a3a", troughcolor="#2d2d2d")

        # 設定視窗圖示

        # 設定視窗圖示
        icon_path = resource_path("icon.png")
        if icon_path.exists():
            try:
                icon = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, icon)
                self._icon_ref = icon  # 防止被垃圾回收
            except Exception:
                pass

        # 設定視窗圖示
        try:
            icon_path = resource_path("icon2.png")
            if icon_path.exists():
                self.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
        except Exception:
            pass

        self.cookie_file = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "karasu_downloads"))
        self.browser_profile = tk.StringVar()
        self._use_browser_cookies = False
        self.running = False
        self.stop_flag = False
        self.process = None
        self.log_queue = queue.Queue()
        self.urls = []
        self.url_vars = []
        self.url_titles = []  # 儲存標題用於搜尋
        self.checkbuttons = []  # 儲存 checkbox widget
        self.log_file = None
        self._init_log_file()

        self._build_ui()
        self._load_settings()
        self._load_default_urls()
        self._check_tools()
        self.log(f"系統架構：{get_system_info()}")
        self.after(100, self._poll_log)
        # 啟動後檢查是否需要設定 Cookie
        self.after(500, self._check_first_run)

    def _check_first_run(self):
        """首次啟動時提示設定 Cookie"""
        if not self.cookie_file.get():
            result = messagebox.askyesno(
                "初次設定",
                "尚未設定 Cookie 檔。\n\n"
                "會員影片需要 Cookie 才能下載。\n\n"
                "【如何取得 Cookie】\n"
                "1. 安裝擴充功能「Get cookies.txt LOCALLY」\n"
                "2. 開啟 YouTube 並登入帳號\n"
                "3. 打開會員影片頁面\n"
                "4. 點擊擴充功能匯出 cookies.txt\n\n"
                "是否現在載入 Cookie？"
            )
            if result:
                self.load_cookie()

    def _load_settings(self):
        """載入已儲存的設定"""
        settings_path = get_stable_tools_dir().parent / "settings.json"
        if settings_path.exists():
            try:
                import json
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("browser_profile"):
                    self.browser_profile.set(data["browser_profile"])
                if data.get("cookie_file"):
                    self.cookie_file.set(data["cookie_file"])
                if data.get("output_dir"):
                    self.output_dir.set(data["output_dir"])
            except Exception:
                pass

    def _save_settings(self):
        """儲存設定"""
        settings_path = get_stable_tools_dir().parent / "settings.json"
        try:
            import json
            data = {
                "browser_profile": self.browser_profile.get(),
                "cookie_file": self.cookie_file.get(),
                "output_dir": self.output_dir.get()
            }
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _build_ui(self):
        frm = ttk.LabelFrame(self, text="設定", padding=8)
        frm.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frm, text="Cookie 檔：").grid(row=0, column=0, sticky="w", pady=4)
        cookie_entry = ttk.Entry(frm, textvariable=self.cookie_file, width=50)
        cookie_entry.grid(row=0, column=1, padx=5, sticky="ew")
        ttk.Button(frm, text="載入 Cookie...", command=self.load_cookie).grid(row=0, column=2, padx=2)

        # Cookie 使用說明
        help_text = "會員影片需 Cookie：安裝「Get cookies.txt LOCALLY」擴充功能 → YouTube 頁面匯出 → 載入"
        ttk.Label(frm, text=help_text, foreground="#888888", font=("Microsoft JhengHei", 8)).grid(row=1, column=0, columnspan=3, sticky="w", pady=2)

        ttk.Label(frm, text="儲存位置：").grid(row=2, column=0, sticky="w", pady=4)
        self.output_entry = ttk.Entry(frm, textvariable=self.output_dir, width=50)
        self.output_entry.grid(row=2, column=1, padx=5, sticky="ew")
        ttk.Button(frm, text="選擇資料夾...", command=self.select_output).grid(row=2, column=2, padx=2)

        # 顯示目前儲存路徑（更明顯）
        self.path_label = ttk.Label(frm, textvariable=self.output_dir, foreground="#88aaff", font=("", 9))
        self.path_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=2)

        self.tool_status = ttk.Label(frm, text="工具狀態：檢查中...", foreground="gray")
        self.tool_status.grid(row=4, column=0, columnspan=3, sticky="w", pady=4)

        frm.columnconfigure(1, weight=1)

        list_frm = ttk.LabelFrame(self, text="影片清單（可勾選）", padding=5)
        list_frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_bar = ttk.Frame(list_frm)
        btn_bar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_bar, text="全選", command=self.select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="全不選", command=self.select_none).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="重新載入清單", command=self._load_default_urls).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="檢查已下載", command=self._check_downloaded).pack(side=tk.LEFT, padx=2)

        # 搜尋框
        search_frm = ttk.Frame(list_frm)
        search_frm.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frm, text="搜尋：").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter_list())
        search_entry = ttk.Entry(search_frm, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(search_frm, text="清除", command=lambda: self.search_var.set("")).pack(side=tk.LEFT, padx=2)

        # 可滾動清單
        list_container = ttk.Frame(list_frm)
        list_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_container, highlightthickness=0, bg="#1a1a1a")
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        self.list_inner = ttk.Frame(canvas, style="Dark.TFrame")

        self.list_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 讓內部框架跟著 canvas 寬度調整
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 滑鼠滾輪只影響清單區域
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=10, pady=5)
        self.start_btn = ttk.Button(ctrl, text="開始下載勾選項目", command=self.start_download)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(ctrl, text="停止", command=self.stop_download, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="清除日誌", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="使用說明", command=self.show_help).pack(side=tk.LEFT, padx=5)

        self.progress_var = tk.StringVar(value="就緒")
        ttk.Label(self, textvariable=self.progress_var).pack(anchor="w", padx=10)
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=2)

        log_frm = ttk.LabelFrame(self, text="日誌", padding=5)
        log_frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(
            log_frm, height=10, state=tk.DISABLED, 
            font=("Consolas", 9), bg="#121212", fg="#d0d0d0",
            insertbackground="#ffffff"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _check_tools(self):
        ok = YTDLP.exists()
        self.tool_status.config(
            text=f"yt-dlp：{'已就緒' if ok else '未找到'}  |  Node：{'已就緒' if NODE.exists() else '未找到'}  |  Deno：{'已就緒' if DENO.exists() else '未找到'}"
        )
        self.log(f"工具目錄：{get_stable_tools_dir()}")
        self.log(f"yt-dlp：{YTDLP if YTDLP.exists() else '未找到'}")
        self.log(f"Deno：{DENO if DENO.exists() else '未找到'}")
        self.log(f"Node.js：{NODE if NODE.exists() else '未找到（可選）'}")
        if not ok:
            self.log("錯誤：找不到 yt-dlp.exe，請確認打包時已放入 tools/")

    def _init_log_file(self):
        """初始化外部日誌檔案"""
        try:
            log_dir = get_stable_tools_dir().parent
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"download_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.log_file = open(log_path, "w", encoding="utf-8")
            self.log(f"日誌檔案：{log_path}")
        except Exception:
            self.log_file = None

    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_queue.put(line)
        if self.log_file:
            try:
                self.log_file.write(line + "\n")
                self.log_file.flush()
            except Exception:
                pass

    def _poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    def _load_default_urls(self):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.urls.clear()
        self.url_vars.clear()
        if hasattr(self, 'url_titles'):
            self.url_titles.clear()
        if hasattr(self, 'checkbuttons'):
            self.checkbuttons.clear()

        # 優先使用 EXE 旁邊的外部檔案，其次用打包進去的
        external_urls = Path(sys.executable).parent / "karasu_urls_with_title.txt"
        if external_urls.exists():
            urls_file = external_urls
            self.log(f"使用外部清單：{urls_file}")
        else:
            urls_file = DEFAULT_URLS
            self.log(f"使用內建清單：{urls_file}")

        if not urls_file.exists():
            self.log("找不到網址清單 karasu_urls_with_title.txt")
            return

        with open(urls_file, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        
        self.log(f"檔案大小：{len(raw)} bytes")
        
        # 簡單分割，保留所有非空行
        all_lines = raw.splitlines()
        lines = [l.strip() for l in all_lines if l.strip()]
        
        self.log(f"原始行數：{len(all_lines)}，有效行數：{len(lines)}")

        self.log(f"清單檔案共 {len(lines)} 行")
        skipped = 0
        for i, line in enumerate(lines):
            if "|||" in line:
                title, url = line.split("|||", 1)
                title = title.strip()
                url = url.strip()
            else:
                title = line
                url = line
            if not url:
                skipped += 1
                continue
            self.urls.append(url)
            self.url_titles.append(title)
            var = tk.BooleanVar(value=True)
            self.url_vars.append(var)
            display = title[:50] + "..." if len(title) > 50 else title
            cb = ttk.Checkbutton(
                self.list_inner, 
                text=f"{len(self.urls):03d}. {display}", 
                variable=var,
                width=70,
                style="Dark.TCheckbutton"
            )
            cb.pack(anchor="w", fill=tk.X, padx=2, pady=1)
            self.checkbuttons.append(cb)

        self.log(f"已載入 {len(self.urls)} 支影片（含標題）")
        if skipped > 0:
            self.log(f"略過 {skipped} 筆無效資料")
        # 自動檢查已下載
        self.after(100, self._check_downloaded)

    def _check_downloaded(self):
        """檢查下載資料夾中已存在的影片並標註"""
        out_dir = Path(self.output_dir.get())
        if not out_dir.exists():
            self.log(f"下載資料夾不存在：{out_dir}")
            return

        # 取得已下載的檔案名稱
        downloaded_files = list(out_dir.glob("*.mp4")) + list(out_dir.glob("*.mkv")) + list(out_dir.glob("*.webm"))
        if not downloaded_files:
            self.log("下載資料夾中沒有影片檔案")
            return

        self.log(f"掃描到 {len(downloaded_files)} 個影片檔案")

        count = 0
        for i, (cb, title) in enumerate(zip(self.checkbuttons, self.url_titles)):
            # 用標題的前 15 個字元比對檔名
            title_key = title[:15].lower().strip()
            is_downloaded = False
            
            for f in downloaded_files:
                fname = f.stem.lower()
                # 檔名包含標題關鍵字
                if title_key and title_key in fname:
                    is_downloaded = True
                    break
                # 或標題包含檔名的主要部分（去掉日期前綴）
                fname_parts = fname.split(" ", 1)
                if len(fname_parts) > 1 and fname_parts[1][:15] in title.lower():
                    is_downloaded = True
                    break

            current_text = cb.cget('text')
            if is_downloaded:
                if not current_text.startswith("✓"):
                    cb.config(text=f"✓ {current_text}")
                self.url_vars[i].set(False)
                count += 1
            else:
                if current_text.startswith("✓ "):
                    cb.config(text=current_text[2:])

        self.log(f"已標註 {count} 支已下載的影片")

    def _filter_list(self):
        """根據搜尋關鍵字過濾清單"""
        keyword = self.search_var.get().lower().strip()
        for i, (cb, title) in enumerate(zip(self.checkbuttons, self.url_titles)):
            if not keyword or keyword in title.lower():
                cb.pack(anchor="w", fill=tk.X, padx=2, pady=1)
            else:
                cb.pack_forget()

    def select_all(self):
        for v in self.url_vars:
            v.set(True)

    def select_none(self):
        for v in self.url_vars:
            v.set(False)

    def refresh_cookie(self):
        """使用 ytdlp-cookie-keeper 刷新 Cookie"""
        cookie_path = self.cookie_file.get()
        if not cookie_path:
            messagebox.showwarning("提示", "請先選擇 Cookie 檔案")
            return
        if not NODE.exists():
            messagebox.showerror("錯誤", "找不到 node.exe，無法執行刷新")
            return

        # 詢問瀏覽器 profile 路徑
        profile = filedialog.askdirectory(title="選擇已登入 YouTube 的瀏覽器 Profile 資料夾")
        if not profile:
            return

        self.log("開始刷新 Cookie...")
        threading.Thread(target=self._refresh_cookie_worker, args=(cookie_path, profile), daemon=True).start()

    def _refresh_cookie_worker(self, cookie_path, profile):
        try:
            self.log(f"Cookie 檔：{cookie_path}")
            self.log(f"Profile：{profile}")

            if not NODE.exists():
                self.log("錯誤：找不到 node.exe")
                self.after(0, lambda: messagebox.showerror("錯誤", "找不到 node.exe"))
                return

            node_dir = NODE.parent
            # 優先找打包進去的 ytdlp-cookie-keeper
            keeper = node_dir / "node_modules" / "ytdlp-cookie-keeper" / "dist" / "cli.js"
            if not keeper.exists():
                # 也檢查 resource_path
                keeper = resource_path("tools/node_modules/ytdlp-cookie-keeper/dist/cli.js")
            if not keeper.exists():
                keeper = node_dir / "node_modules" / ".bin" / "ytdlp-cookie-keeper.cmd"

            if keeper.exists():
                self.log("使用打包的 ytdlp-cookie-keeper")
                if keeper.suffix == ".js":
                    cmd = [str(NODE), str(keeper), "refresh", "--cookies", cookie_path, "--browser", f"chrome+basictext:{profile}"]
                else:
                    cmd = [str(keeper), "refresh", "--cookies", cookie_path, "--browser", f"chrome+basictext:{profile}"]
            else:
                # 退回用 npx
                self.log("未找到打包版本，嘗試 npx...")
                npx_cmd = node_dir / "npx.cmd"
                if npx_cmd.exists():
                    cmd = [str(npx_cmd), "--yes", "ytdlp-cookie-keeper", "refresh", "--cookies", cookie_path, "--browser", f"chrome+basictext:{profile}"]
                else:
                    self.log("錯誤：找不到 ytdlp-cookie-keeper")
                    self.after(0, lambda: messagebox.showerror("錯誤", "找不到 ytdlp-cookie-keeper\n請在 tools/x64 執行 npm install ytdlp-cookie-keeper"))
                    return

            self.log(f"執行刷新...")
            env = os.environ.copy()
            env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                encoding="utf-8", errors="replace", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            output = (result.stdout or "") + (result.stderr or "")
            for line in output.splitlines():
                if line.strip():
                    self.log("  " + line.strip())

            if result.returncode == 0:
                self.after(0, lambda: messagebox.showinfo("完成", "Cookie 刷新成功"))
            else:
                self.after(0, lambda: messagebox.showerror("失敗", "Cookie 刷新失敗，請查看日誌"))
        except Exception as e:
            self.log(f"刷新錯誤：{e}")
            self.after(0, lambda: messagebox.showerror("錯誤", str(e)))

    def load_cookie(self):
        path = filedialog.askopenfilename(
            title="選擇 Cookie 檔案",
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")]
        )
        if path:
            self.cookie_file.set(path)
            self._save_settings()
            self.log(f"已載入 Cookie：{path}")

    def select_output(self):
        path = filedialog.askdirectory(title="選擇儲存位置")
        if path:
            self.output_dir.set(path)
            self._save_settings()
            self.log(f"儲存位置已更改：{path}")
            self._check_downloaded()

    def show_help(self):
        """顯示使用說明"""
        help_win = tk.Toplevel(self)
        help_win.title("使用說明")
        help_win.geometry("500x400")
        help_win.configure(bg="#1a1a1a")
        help_win.transient(self)
        help_win.grab_set()

        text = scrolledtext.ScrolledText(
            help_win, wrap=tk.WORD, font=("Microsoft JhengHei", 10),
            bg="#1a1a1a", fg="#e0e0e0", padx=10, pady=10
        )
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        help_content = """
【KarasuLover 使用說明】

■ 基本使用
1. 載入 Cookie 檔（會員影片需要）
2. 選擇儲存位置
3. 勾選要下載的影片
4. 點擊「開始下載」

■ 如何取得 Cookie
1. 安裝瀏覽器擴充功能「Get cookies.txt LOCALLY」
   Chrome：https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc
2. 開啟 YouTube 並登入帳號，打開會員影片
3. 點擊擴充功能圖示，匯出 cookies.txt
4. 在程式中點「載入 Cookie」選擇該檔案

■ 注意事項
• 沒有 Cookie 只能下載公開影片
• 會員影片必須有有效的 Cookie
• Cookie 過期時需重新匯出
• 下載的檔案會以「日期 標題.mp4」命名

■ 搜尋功能
在搜尋框輸入關鍵字可過濾影片清單
"""
        text.insert(tk.END, help_content)
        text.config(state=tk.DISABLED)

        ttk.Button(help_win, text="關閉", command=help_win.destroy).pack(pady=10)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def start_download(self):
        if self.running:
            return
        selected = [self.urls[i] for i, v in enumerate(self.url_vars) if v.get()]
        if not selected:
            messagebox.showwarning("提示", "請至少勾選一支影片")
            return
        # 檢查 Cookie
        if not self.cookie_file.get() or not Path(self.cookie_file.get()).exists():
            result = messagebox.askyesno(
                "未設定 Cookie",
                "沒設定 Cookie 的話，會員影片無法下載。\n\n是否仍要繼續？（僅能下載公開影片）"
            )
            if not result:
                return
        if not YTDLP.exists():
            messagebox.showerror("錯誤", "找不到 yt-dlp.exe")
            return

        self.running = True
        self.stop_flag = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self._download_worker, args=(selected,), daemon=True).start()

    def stop_download(self):
        self.stop_flag = True
        self.log("正在停止...")
        if self.process:
            try:
                self.process.terminate()
            except:
                pass

    def _switch_log_to_output(self, out_dir):
        """把日誌切換到目標資料夾的 log.txt"""
        try:
            if self.log_file:
                self.log_file.close()
            log_path = out_dir / "log.txt"
            self.log_file = open(log_path, "a", encoding="utf-8")
            self.log(f"日誌寫入：{log_path}")
        except Exception as e:
            self.log(f"無法寫入目標資料夾日誌：{e}")

    def _download_worker(self, urls):
        try:
            out_dir = Path(self.output_dir.get())
            out_dir.mkdir(parents=True, exist_ok=True)

            # 日誌切換到目標資料夾
            self._switch_log_to_output(out_dir)

            cookie = self.cookie_file.get()
            total = len(urls)
            self.progress["maximum"] = total
            failed = []

            self.log(f"開始下載 {total} 支影片")
            self.log(f"儲存位置：{out_dir}")

            for i, url in enumerate(urls, 1):
                if self.stop_flag:
                    self.log("使用者停止")
                    break
                self.progress_var.set(f"進度：{i} / {total}")
                self.progress["value"] = i - 1
                self.log(f"({i}/{total}) {url}")

                if self._download_one(url, out_dir, cookie):
                    self.log("  → 成功")
                else:
                    failed.append(url)
                    self.log("  → 失敗")
                self.progress["value"] = i

            failed_path = out_dir / "failed.txt"
            with open(failed_path, "w", encoding="utf-8") as f:
                f.write("\n".join(failed))

            self.log("=" * 40)
            self.log(f"完成。成功 {total - len(failed)}，失敗 {len(failed)}")
            if failed:
                self.log(f"失敗清單：{failed_path}")
        except Exception as e:
            self.log(f"錯誤：{e}")
        finally:
            self.running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.progress_var.set("就緒")

    def _prompt_use_cookie_file(self):
        """提示使用 Cookie 檔"""
        result = messagebox.askyesno(
            "需要 Cookie 才能下載",
            "這是會員限定影片，需要 Cookie 才能下載。\n\n"
            "請先載入 Cookie 檔：\n"
            "1. 安裝擴充功能「Get cookies.txt LOCALLY」\n"
            "2. 在 YouTube 會員影片頁面匯出 cookies.txt\n"
            "3. 點「載入 Cookie」選擇該檔案\n\n"
            "是否現在選擇 Cookie 檔？"
        )
        if result:
            path = filedialog.askopenfilename(
                title="選擇 cookies.txt",
                filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")]
            )
            if path:
                self.cookie_file.set(path)
                self._save_settings()
                self.log(f"已載入 Cookie 檔：{path}")
                messagebox.showinfo("完成", "Cookie 已載入，請重新開始下載。")

    def _prompt_membership_required(self):
        """Cookie 沒有會員權限時提示"""
        messagebox.showwarning(
            "無法下載會員影片",
            "下載失敗：Cookie 沒有此頻道的會員權限。\n\n"
            "請重新匯出 Cookie：\n"
            "1. 用已加入會員的帳號登入 YouTube\n"
            "2. 打開該頻道的會員影片頁面\n"
            "3. 用擴充功能重新匯出 cookies.txt\n"
            "4. 在程式中載入新的 Cookie 檔"
        )

    def _prompt_cookie_update(self):
        """Cookie 失效時：有 Profile 就自動刷新，否則提示手動選擇"""
        profile = self.browser_profile.get()
        cookie = self.cookie_file.get()

        if profile and Path(profile).exists() and cookie:
            self.log("Cookie 失效，嘗試自動刷新...")
            threading.Thread(target=self._auto_refresh_cookie, daemon=True).start()
        else:
            result = messagebox.askyesno(
                "Cookie 已失效",
                "YouTube Cookie 已失效。\n\n是否要選擇新的 Cookie 檔案？"
            )
            if result:
                path = filedialog.askopenfilename(
                    title="選擇新的 Cookie 檔案",
                    filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")]
                )
                if path:
                    self.cookie_file.set(path)
                    self._save_settings()
                    self.log(f"已更新 Cookie：{path}")
                    messagebox.showinfo("提示", "Cookie 已更新，請重新開始下載。")

    def _auto_refresh_cookie(self):
        """自動刷新 Cookie"""
        cookie = self.cookie_file.get()
        profile = self.browser_profile.get()
        try:
            self._refresh_cookie_worker(cookie, profile)
            self.after(0, lambda: self.log("自動刷新完成，請重新開始下載"))
        except Exception as e:
            self.after(0, lambda: self.log(f"自動刷新失敗：{e}"))
            self.after(0, lambda: messagebox.showerror("刷新失敗", "自動刷新失敗，請手動更新 Cookie。"))

    def _extract_cookie_from_profile(self, profile):
        """從瀏覽器 Profile 取出 Cookie 到暫存檔"""
        try:
            if not NODE.exists():
                return None
            node_dir = NODE.parent
            keeper = resource_path("tools/node_modules/ytdlp-cookie-keeper/dist/cli.js")
            if not keeper.exists():
                keeper = node_dir / "node_modules" / "ytdlp-cookie-keeper" / "dist" / "cli.js"
            if not keeper.exists():
                self.log("    找不到 ytdlp-cookie-keeper")
                return None

            temp_cookie = get_stable_tools_dir().parent / "temp_cookies.txt"
            cmd = [str(NODE), str(keeper), "refresh", "--cookies", str(temp_cookie), "--browser", f"chrome+basictext:{profile}"]
            env = os.environ.copy()
            env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0 and temp_cookie.exists():
                return str(temp_cookie)
            else:
                self.log(f"    取出 Cookie 失敗：{result.stderr or result.stdout}")
                return None
        except Exception as e:
            self.log(f"    取出 Cookie 錯誤：{e}")
            return None

    def _download_one(self, url, out_dir, cookie, max_retry=3):
        """先不帶 Cookie 嘗試，遇到會員影片再用 Cookie"""
        for attempt in range(1, max_retry + 1):
            if self.stop_flag:
                return False

            # 第一次不帶 Cookie，之後或需要時帶 Cookie
            use_cookie = (attempt > 1) and (cookie and Path(cookie).exists() or getattr(self, '_use_browser_cookies', False))
            use_browser = getattr(self, '_use_browser_cookies', False) and attempt > 1

            cmd = [
                str(YTDLP),
                "-f", "bv*+ba/b",
                "--merge-output-format", "mp4",
                "--continue",
                "--no-overwrites",
                "--sleep-interval", "1",
                "--max-sleep-interval", "3",
                "--retries", "3",
                "--fragment-retries", "5",
                "-o", str(out_dir / "%(upload_date)s %(title)s.%(ext)s"),
                url
            ]
            if use_browser and self.browser_profile.get():
                # 用 yt-dlp 內建從瀏覽器取 Cookie
                profile = self.browser_profile.get()
                # 判斷瀏覽器類型
                profile_lower = profile.lower()
                if "brave" in profile_lower:
                    browser = "brave"
                elif "firefox" in profile_lower or "mozilla" in profile_lower:
                    browser = "firefox"
                elif "edge" in profile_lower:
                    browser = "edge"
                else:
                    browser = "chrome"
                cmd[1:1] = ["--cookies-from-browser", f"{browser}:{profile}"]
                self.log(f"    使用 {browser} 瀏覽器 Cookie")
            elif use_cookie and cookie and Path(cookie).exists():
                cmd[1:1] = ["--cookies", cookie]
                self.log("    使用 Cookie 檔重試（會員影片）")
            else:
                self.log("    嘗試下載（無 Cookie）")

            env = os.environ.copy()
            if NODE.exists():
                env["PATH"] = str(NODE.parent) + os.pathsep + env.get("PATH", "")
                cmd.insert(1, "--js-runtimes")
                cmd.insert(2, "node")
            elif DENO.exists():
                env["PATH"] = str(DENO.parent) + os.pathsep + env.get("PATH", "")
                cmd.insert(1, "--js-runtimes")
                cmd.insert(2, "deno")

            need_cookie = False
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                for line in self.process.stdout:
                    if self.stop_flag:
                        self.process.terminate()
                        return False
                    line = line.rstrip()
                    if line:
                        self.log("    " + line)
                        low = line.lower()
                        # 偵測會員限定
                        if "members only" in low or "join this channel" in low or "available to this channel's members" in low:
                            need_cookie = True
                            # 如果已經用 Cookie 還是會員錯誤，提示權限不足
                            if use_cookie:
                                self.after(0, self._prompt_membership_required)
                                self.process.terminate()
                                return False
                        # 偵測瀏覽器 Cookie 讀取失敗 - 改提示用 Cookie 檔
                        if "could not copy chrome cookie database" in low or "failed to decrypt with dpapi" in low:
                            self.after(0, self._prompt_use_cookie_file)
                            self.process.terminate()
                            return False
                        # 偵測 Cookie 失效
                        if "cookies are no longer valid" in low or "sign in to confirm" in low:
                            self.after(0, self._prompt_cookie_update)
                            self.process.terminate()
                            return False
                self.process.wait()

                if self.process.returncode == 0:
                    return True

                # 需要 Cookie
                if need_cookie and not use_cookie:
                    if cookie and Path(cookie).exists():
                        self.log("    準備用 Cookie 檔重試...")
                        continue
                    else:
                        self.log("    會員影片需要 Cookie")
                        self.after(0, self._prompt_use_cookie_file)
                        return False

                if attempt < max_retry:
                    self.log(f"  重試 {attempt}/{max_retry}...")
                    import time; time.sleep(2)
            except Exception as e:
                self.log(f"  執行錯誤：{e}")
        return False

if __name__ == "__main__":
    app = KarasuDownloader()
    app.mainloop()
