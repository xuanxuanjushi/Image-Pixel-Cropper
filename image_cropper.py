import ctypes
import math
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # pragma: no cover - shown only when dependency is missing.
    Image = None
    ImageDraw = None
    ImageTk = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # pragma: no cover - drag and drop remains optional.
    DND_FILES = None
    TkinterDnD = None

from watermark_remover import WatermarkRemovalError, remove_masked_area


MIN_SCALE = 0.01
MAX_SCALE = 50.0
MIN_VIEW_ZOOM = 0.25
MAX_VIEW_ZOOM = 5.0
HANDLE_SIZE = 12
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
APP_BG = "#050916"
SIDEBAR_BG = "#202b3d"
SIDEBAR_DARK = "#172235"
CONTROL_BG = "#334257"
WORK_BG = "#050916"
SURFACE_BG = "#121a2a"
TEXT_MAIN = "#eef5ff"
TEXT_MUTED = "#9eafc6"
ACCENT = "#41c8ee"
ACCENT_DARK = "#24364c"
PURPLE = "#6657f2"
WARNING = "#ff5c6a"
SUPPORTED_OPEN_TYPES = [
    ("图片文件", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff"),
    ("所有文件", "*.*"),
]
SUPPORTED_SAVE_TYPES = [
    ("PNG 图片", "*.png"),
    ("JPEG 图片", "*.jpg"),
    ("WebP 图片", "*.webp"),
    ("BMP 图片", "*.bmp"),
]


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


APP_ICON_PATH = resource_path("assets/app_icon.ico")

BaseWindow = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk


def enable_high_dpi() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


class ImageCropperApp(BaseWindow):
    def __init__(self) -> None:
        super().__init__()
        self.ui_scale = self._compute_ui_scale()
        self.title("像素裁剪工作台")
        self._configure_window_size()
        self.configure(bg=APP_BG)
        self._set_window_icon()
        self._apply_tk_scaling()

        self.source_path: Path | None = None
        self.source_image: Image.Image | None = None
        self.preview_image_ref: ImageTk.PhotoImage | None = None
        self.mask_preview_ref: ImageTk.PhotoImage | None = None

        self.target_width = tk.IntVar(value=1000)
        self.target_height = tk.IntVar(value=1000)
        self.output_format = tk.StringVar(value="PNG")
        self.quality = tk.IntVar(value=95)
        self.fit_mode = tk.StringVar(value="cover")
        self.canvas_resize_mode = tk.BooleanVar(value=False)
        self.repair_mode = tk.BooleanVar(value=False)
        self.repair_tool = tk.StringVar(value="画笔")
        self.brush_size = tk.IntVar(value=36)
        self.repair_radius = tk.IntVar(value=5)
        self.status = tk.StringVar(value="选择或拖拽图片开始裁剪。")
        self.source_info = tk.StringVar(value="未导入图片")
        self.target_info = tk.StringVar(value="目标 1000 x 1000")
        self.zoom_info = tk.StringVar(value="缩放 100%")
        self.mode_info = tk.StringVar(value="填充裁剪")

        self.image_scale = 1.0
        self.view_zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.view_scale = 1.0
        self.view_left = 0.0
        self.view_top = 0.0
        self.view_pan_x = 0.0
        self.view_pan_y = 0.0
        self.drag_mode: str | None = None
        self.last_mouse: tuple[int, int] | None = None
        self.canvas_pan_start: tuple[int, int] | None = None
        self.canvas_pan_initial: tuple[float, float] | None = None
        self.canvas_resize_region: str | None = None
        self.canvas_resize_start: tuple[int, int] | None = None
        self.canvas_resize_initial_size: tuple[int, int] | None = None
        self.repair_mask: Image.Image | None = None
        self.repair_rect_start: tuple[int, int] | None = None
        self.repair_rect_preview: tuple[int, int, int, int] | None = None
        self.repair_last_source_point: tuple[int, int] | None = None
        self.repair_brush_preview_point: tuple[int, int] | None = None
        self.sidebar_canvas: tk.Canvas | None = None
        self.sidebar_scrollbar: ttk.Scrollbar | None = None
        self.sidebar_window: int | None = None

        self._build_ui()
        self._bind_events()
        self._setup_drag_drop()
        self.after(50, self.redraw)

        if Image is None:
            messagebox.showerror(
                "缺少依赖",
                "需要安装 Pillow：python -m pip install Pillow",
            )

    def _compute_ui_scale(self) -> float:
        screen_height = max(720, self.winfo_screenheight())
        if screen_height <= 1080:
            return 0.74
        if screen_height <= 1440:
            return 0.90
        return 1.0

    def _scaled(self, value: int | float) -> int:
        return max(1, round(value * self.ui_scale))

    def _font(self, size: int, weight: str | None = None) -> tuple:
        scaled_size = max(8, round(size * self.ui_scale))
        if weight is None:
            return ("Microsoft YaHei UI", scaled_size)
        return ("Microsoft YaHei UI", scaled_size, weight)

    def _configure_window_size(self) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(self._scaled(1280), max(980, screen_w - 140))
        height = min(self._scaled(820), max(660, screen_h - 140))
        self.geometry(f"{width}x{height}")
        self.minsize(min(980, width), min(660, height))

    def _set_window_icon(self) -> None:
        if not APP_ICON_PATH.exists():
            return
        try:
            self.iconbitmap(default=str(APP_ICON_PATH))
        except tk.TclError:
            pass

    def _apply_tk_scaling(self) -> None:
        try:
            scaling = max(1.0, self.winfo_fpixels("1i") / 72)
            self.tk.call("tk", "scaling", scaling)
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        self._configure_style()

        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True)

        sidebar_shell = ttk.Frame(root, style="Sidebar.TFrame")
        sidebar_shell.pack(side=tk.LEFT, fill=tk.Y)
        sidebar_shell.pack_propagate(False)
        sidebar_shell.configure(width=self._scaled(310))

        self.sidebar_canvas = tk.Canvas(
            sidebar_shell,
            bg=SIDEBAR_BG,
            highlightthickness=0,
            bd=0,
        )
        self.sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_shell,
            orient=tk.VERTICAL,
            command=self.sidebar_canvas.yview,
        )
        self.sidebar_canvas.configure(yscrollcommand=self._on_sidebar_scroll)
        sidebar = ttk.Frame(
            self.sidebar_canvas,
            padding=(
                self._scaled(22),
                self._scaled(14),
                self._scaled(22),
                self._scaled(10),
            ),
            style="Sidebar.TFrame",
        )
        self.sidebar_window = self.sidebar_canvas.create_window(
            (0, 0),
            window=sidebar,
            anchor=tk.NW,
        )
        sidebar.bind("<Configure>", self._update_sidebar_scrollregion)
        self.sidebar_canvas.bind("<Configure>", self._resize_sidebar_window)

        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.pack(fill=tk.X)
        self.logo = tk.Canvas(
            brand,
            width=self._scaled(54),
            height=self._scaled(54),
            bg=SIDEBAR_BG,
            highlightthickness=0,
        )
        self.logo.pack(side=tk.LEFT, padx=(0, self._scaled(14)))
        self._draw_logo()
        ttk.Label(brand, text="像素裁剪", style="Brand.TLabel").pack(anchor=tk.W)
        ttk.Label(brand, text="图片尺寸与构图工具", style="SidebarSubtle.TLabel").pack(
            anchor=tk.W, pady=(self._scaled(2), 0)
        )
        ttk.Label(brand, text="轩轩居士开发", style="Developer.TLabel").pack(
            anchor=tk.W, pady=(self._scaled(8), 0)
        )

        ttk.Button(sidebar, text="选择图片", command=self.load_image, style="Primary.TButton").pack(
            fill=tk.X, pady=(self._scaled(28), self._scaled(22))
        )

        self._section_title(sidebar, "第一步")
        ttk.Label(sidebar, text="设置输出尺寸", style="SidebarText.TLabel").pack(
            anchor=tk.W, pady=(self._scaled(6), self._scaled(6))
        )
        size_grid = ttk.Frame(sidebar, style="Sidebar.TFrame")
        size_grid.pack(fill=tk.X, pady=(0, self._scaled(18)))
        ttk.Label(size_grid, text="宽度", style="SidebarSubtle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(size_grid, text="高度", style="SidebarSubtle.TLabel").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        ttk.Spinbox(
            size_grid,
            from_=1,
            to=20000,
            textvariable=self.target_width,
            width=9,
            command=self.apply_target_size,
            style="Modern.TSpinbox",
        ).grid(row=1, column=0, sticky="ew", pady=(self._scaled(5), 0))
        ttk.Spinbox(
            size_grid,
            from_=1,
            to=20000,
            textvariable=self.target_height,
            width=9,
            command=self.apply_target_size,
            style="Modern.TSpinbox",
        ).grid(row=1, column=1, sticky="ew", padx=(self._scaled(12), 0), pady=(self._scaled(5), 0))
        size_grid.columnconfigure((0, 1), weight=1)
        ttk.Button(sidebar, text="应用尺寸", command=self.apply_target_size).pack(
            fill=tk.X, pady=(0, self._scaled(10))
        )
        self._section_separator(sidebar)

        self._section_title(sidebar, "第二步")
        ttk.Label(sidebar, text="选择适配方式", style="SidebarText.TLabel").pack(
            anchor=tk.W, pady=(self._scaled(6), self._scaled(6))
        )
        ttk.Radiobutton(
            sidebar,
            text="填充裁剪",
            value="cover",
            variable=self.fit_mode,
            command=self.reset_image_fit,
            style="Modern.TRadiobutton",
        ).pack(anchor=tk.W, pady=(0, self._scaled(6)))
        ttk.Radiobutton(
            sidebar,
            text="白底留边",
            value="contain",
            variable=self.fit_mode,
            command=self.reset_image_fit,
            style="Modern.TRadiobutton",
        ).pack(anchor=tk.W, pady=(0, self._scaled(10)))
        self._section_separator(sidebar)

        self._section_title(sidebar, "第三步")
        ttk.Label(sidebar, text="导出格式与质量", style="SidebarText.TLabel").pack(
            anchor=tk.W, pady=(self._scaled(6), self._scaled(6))
        )
        export_grid = ttk.Frame(sidebar, style="Sidebar.TFrame")
        export_grid.pack(fill=tk.X, pady=(0, self._scaled(14)))
        ttk.Label(export_grid, text="格式", style="SidebarSubtle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(export_grid, text="质量", style="SidebarSubtle.TLabel").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        format_menu = tk.OptionMenu(
            export_grid,
            self.output_format,
            "PNG",
            "JPG",
            "WEBP",
            "BMP",
        )
        self._style_dark_option_menu(format_menu)
        format_menu.grid(row=1, column=0, sticky="ew", pady=(self._scaled(5), 0))
        quality_spinbox = tk.Spinbox(
            export_grid,
            from_=1,
            to=100,
            textvariable=self.quality,
            width=8,
            bg=SIDEBAR_DARK,
            fg=TEXT_MAIN,
            buttonbackground=CONTROL_BG,
            insertbackground=TEXT_MAIN,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground="#40506a",
            highlightcolor=ACCENT,
            selectbackground=CONTROL_BG,
            selectforeground=TEXT_MAIN,
            font=self._font(10),
        )
        quality_spinbox.grid(row=1, column=1, sticky="ew", padx=(self._scaled(12), 0), pady=(self._scaled(5), 0), ipady=self._scaled(4))
        export_grid.columnconfigure((0, 1), weight=1)
        self._section_separator(sidebar)

        self._section_title(sidebar, "第四步")
        ttk.Label(sidebar, text="局部水印修复", style="SidebarText.TLabel").pack(
            anchor=tk.W, pady=(self._scaled(6), self._scaled(6))
        )
        ttk.Checkbutton(
            sidebar,
            text="修复模式",
            variable=self.repair_mode,
            command=self._on_repair_mode_changed,
            style="Modern.TCheckbutton",
        ).pack(anchor=tk.W, pady=(0, self._scaled(6)))
        repair_grid = ttk.Frame(sidebar, style="Sidebar.TFrame")
        repair_grid.pack(fill=tk.X, pady=(0, self._scaled(8)))
        ttk.Label(repair_grid, text="工具", style="SidebarSubtle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(repair_grid, text="画笔", style="SidebarSubtle.TLabel").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        tool_menu = tk.OptionMenu(repair_grid, self.repair_tool, "画笔", "矩形")
        self._style_dark_option_menu(tool_menu)
        tool_menu.grid(row=1, column=0, sticky="ew", pady=(self._scaled(5), 0))
        brush_spinbox = tk.Spinbox(
            repair_grid,
            from_=4,
            to=300,
            textvariable=self.brush_size,
            width=8,
            bg=SIDEBAR_DARK,
            fg=TEXT_MAIN,
            buttonbackground=CONTROL_BG,
            insertbackground=TEXT_MAIN,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground="#40506a",
            highlightcolor=ACCENT,
            selectbackground=CONTROL_BG,
            selectforeground=TEXT_MAIN,
            font=self._font(10),
        )
        brush_spinbox.grid(row=1, column=1, sticky="ew", padx=(self._scaled(12), 0), pady=(self._scaled(5), 0), ipady=self._scaled(4))
        repair_grid.columnconfigure((0, 1), weight=1)
        ttk.Button(sidebar, text="应用修复", command=self.apply_watermark_repair).pack(
            fill=tk.X, pady=(0, self._scaled(7))
        )
        ttk.Button(sidebar, text="清空标记", command=self.clear_repair_mask).pack(
            fill=tk.X, pady=(0, self._scaled(10))
        )
        self._section_separator(sidebar)

        ttk.Label(sidebar, text="画面调整", style="SidebarText.TLabel").pack(
            anchor=tk.W, pady=(0, self._scaled(6))
        )
        ttk.Button(sidebar, text="恢复原图尺寸", command=self.restore_original_size).pack(
            fill=tk.X, pady=(0, self._scaled(7))
        )
        ttk.Button(sidebar, text="居中图片", command=self.center_image).pack(
            fill=tk.X, pady=(0, self._scaled(7))
        )
        ttk.Checkbutton(
            sidebar,
            text="调整画布",
            variable=self.canvas_resize_mode,
            command=self._on_canvas_resize_mode_changed,
            style="Modern.TCheckbutton",
        ).pack(fill=tk.X, pady=(0, self._scaled(12)))

        self._bind_sidebar_mousewheel(sidebar_shell)

        workspace = ttk.Frame(root, padding=(self._scaled(28), self._scaled(22), self._scaled(28), self._scaled(16)), style="App.TFrame")
        workspace.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header = ttk.Frame(workspace, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, self._scaled(16)))
        title = ttk.Frame(header, style="App.TFrame")
        title.pack(side=tk.LEFT)
        ttk.Label(title, text="裁剪工作区", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            title,
            text="精确尺寸 · 实时预览 · 快速导出",
            style="Subtle.TLabel",
        ).pack(anchor=tk.W, pady=(self._scaled(4), 0))
        ttk.Button(header, text="导出", command=self.export_image, style="Accent.TButton").pack(
            side=tk.RIGHT
        )
        ttk.Button(header, text="导入图片", command=self.load_image).pack(
            side=tk.RIGHT, padx=(0, self._scaled(12))
        )

        info_bar = ttk.Frame(workspace, style="App.TFrame")
        info_bar.pack(fill=tk.X, pady=(0, self._scaled(12)))
        for text_var in (self.source_info, self.target_info, self.zoom_info, self.mode_info):
            ttk.Label(info_bar, textvariable=text_var, style="Pill.TLabel").pack(
                side=tk.LEFT, padx=(0, self._scaled(10))
            )

        self.canvas = tk.Canvas(
            workspace,
            bg=WORK_BG,
            highlightthickness=0,
            insertbackground=TEXT_MAIN,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        status_bar = ttk.Frame(workspace, style="App.TFrame")
        status_bar.pack(fill=tk.X, pady=(self._scaled(10), 0))
        ttk.Label(status_bar, textvariable=self.status, style="Status.TLabel").pack(
            side=tk.LEFT
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background=APP_BG)
        style.configure("Sidebar.TFrame", background=SIDEBAR_BG)
        style.configure("Title.TLabel", background=APP_BG, foreground=TEXT_MAIN, font=self._font(20, "bold"))
        style.configure("Brand.TLabel", background=SIDEBAR_BG, foreground=TEXT_MAIN, font=self._font(21, "bold"))
        style.configure("Developer.TLabel", background=SIDEBAR_BG, foreground=ACCENT, font=self._font(10, "bold"))
        style.configure("Subtle.TLabel", background=APP_BG, foreground=TEXT_MUTED, font=self._font(10))
        style.configure("SidebarText.TLabel", background=SIDEBAR_BG, foreground=TEXT_MAIN, font=self._font(10))
        style.configure("SidebarSubtle.TLabel", background=SIDEBAR_BG, foreground=TEXT_MUTED, font=self._font(9))
        style.configure("Section.TLabel", background=SIDEBAR_BG, foreground=TEXT_MAIN, font=self._font(13, "bold"))
        style.configure("Hint.TLabel", background=SIDEBAR_BG, foreground=TEXT_MUTED, font=self._font(9))
        style.configure("Status.TLabel", background=APP_BG, foreground=TEXT_MUTED, font=self._font(9))
        style.configure("Pill.TLabel", background=SURFACE_BG, foreground="#d9e6f7", padding=(self._scaled(14), self._scaled(8)), font=self._font(9))
        style.configure("TButton", background=CONTROL_BG, foreground=TEXT_MAIN, borderwidth=0, focusthickness=0, padding=(self._scaled(14), self._scaled(10)), font=self._font(10, "bold"))
        style.map("TButton", background=[("active", "#40506a"), ("pressed", "#2a3850")], foreground=[("disabled", "#6f7f93")])
        style.configure("Primary.TButton", background=CONTROL_BG, foreground=TEXT_MAIN, borderwidth=0, padding=(self._scaled(18), self._scaled(13)), font=self._font(11, "bold"))
        style.map("Primary.TButton", background=[("active", "#465872"), ("pressed", "#2d3c53")])
        style.configure("Accent.TButton", background=PURPLE, foreground="#ffffff", borderwidth=0, padding=(self._scaled(22), self._scaled(10)), font=self._font(10, "bold"))
        style.map("Accent.TButton", background=[("active", "#7668ff"), ("pressed", "#5145d8")])
        style.configure("Modern.TRadiobutton", background=SIDEBAR_BG, foreground=TEXT_MAIN, font=self._font(10), indicatorcolor=SIDEBAR_DARK)
        style.map("Modern.TRadiobutton", background=[("active", SIDEBAR_BG)], foreground=[("active", ACCENT)])
        style.configure("Modern.TCheckbutton", background=SIDEBAR_BG, foreground=TEXT_MAIN, font=self._font(10), indicatorcolor=SIDEBAR_DARK)
        style.map("Modern.TCheckbutton", background=[("active", SIDEBAR_BG)], foreground=[("active", ACCENT)])
        style.configure("Modern.TCombobox", fieldbackground=SIDEBAR_DARK, background=CONTROL_BG, foreground=TEXT_MAIN, arrowcolor=ACCENT, bordercolor="#40506a", lightcolor="#40506a", darkcolor="#40506a", padding=(self._scaled(8), self._scaled(6)))
        style.map("Modern.TCombobox", fieldbackground=[("readonly", SIDEBAR_DARK)], selectbackground=[("readonly", SIDEBAR_DARK)], selectforeground=[("readonly", TEXT_MAIN)])
        style.configure("Modern.TSpinbox", fieldbackground=SIDEBAR_DARK, background=CONTROL_BG, foreground=TEXT_MAIN, arrowcolor=ACCENT, bordercolor="#40506a", lightcolor="#40506a", darkcolor="#40506a", padding=(self._scaled(8), self._scaled(6)))

    def _style_dark_option_menu(self, option_menu: tk.OptionMenu) -> None:
        option_menu.configure(
            bg=SIDEBAR_DARK,
            fg=TEXT_MAIN,
            activebackground=CONTROL_BG,
            activeforeground=TEXT_MAIN,
            highlightthickness=1,
            highlightbackground="#40506a",
            bd=0,
            relief=tk.FLAT,
            font=self._font(10),
            indicatoron=False,
        )
        menu = option_menu["menu"]
        menu.configure(
            bg=SIDEBAR_DARK,
            fg=TEXT_MAIN,
            activebackground=CONTROL_BG,
            activeforeground=TEXT_MAIN,
            bd=0,
            relief=tk.FLAT,
            font=self._font(10),
        )

    def _section_title(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor=tk.W)

    def _section_separator(self, parent: ttk.Frame) -> None:
        tk.Frame(
            parent,
            height=1,
            bg="#34445b",
            highlightthickness=0,
            bd=0,
        ).pack(fill=tk.X, pady=(self._scaled(5), self._scaled(5)))

    def _update_sidebar_scrollregion(self, _event: tk.Event | None = None) -> None:
        if self.sidebar_canvas is None:
            return
        self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
        self.after_idle(self._sync_sidebar_scrollbar)

    def _resize_sidebar_window(self, event: tk.Event) -> None:
        if self.sidebar_canvas is None or self.sidebar_window is None:
            return
        self.sidebar_canvas.itemconfigure(self.sidebar_window, width=event.width)
        self.after_idle(self._sync_sidebar_scrollbar)

    def _on_sidebar_scroll(self, first: str, last: str) -> None:
        if self.sidebar_scrollbar is not None:
            self.sidebar_scrollbar.set(first, last)
        self._sync_sidebar_scrollbar()

    def _sync_sidebar_scrollbar(self) -> None:
        if self.sidebar_canvas is None or self.sidebar_scrollbar is None:
            return
        bbox = self.sidebar_canvas.bbox("all")
        content_height = 0 if bbox is None else bbox[3] - bbox[1]
        needs_scroll = content_height > self.sidebar_canvas.winfo_height() + 2
        if needs_scroll:
            if not self.sidebar_scrollbar.winfo_ismapped():
                self.sidebar_canvas.pack_forget()
                self.sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        else:
            if self.sidebar_scrollbar.winfo_ismapped():
                self.sidebar_scrollbar.pack_forget()
            if self.sidebar_canvas.yview()[0] != 0.0:
                self.sidebar_canvas.yview_moveto(0)

    def _bind_sidebar_mousewheel(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", self._scroll_sidebar, add="+")
        widget.bind("<Button-4>", self._scroll_sidebar, add="+")
        widget.bind("<Button-5>", self._scroll_sidebar, add="+")
        for child in widget.winfo_children():
            self._bind_sidebar_mousewheel(child)

    def _scroll_sidebar(self, event: tk.Event) -> str | None:
        if self.sidebar_canvas is None:
            return None
        bbox = self.sidebar_canvas.bbox("all")
        if bbox is None or bbox[3] - bbox[1] <= self.sidebar_canvas.winfo_height() + 2:
            return None
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
        self.sidebar_canvas.yview_scroll(delta * 3, "units")
        return "break"

    def _draw_logo(self) -> None:
        self.logo.create_round_rect = self._canvas_round_rect.__get__(self.logo, tk.Canvas)
        self.logo.create_round_rect(4, 4, 50, 50, radius=14, fill="#78b9f5", outline="#111a2a", width=3)
        for x in (12, 24):
            self.logo.create_line(x, 10, x, 45, fill="#3b78b7", width=2)
        for y in (18, 30):
            self.logo.create_line(10, y, 35, y, fill="#3b78b7", width=2)
        self.logo.create_oval(30, 21, 43, 34, fill="#24364c", outline="")
        self.logo.create_line(35, 27, 48, 27, fill="#24364c", width=4)

    @staticmethod
    def _canvas_round_rect(
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        **kwargs,
    ) -> int:
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def _bind_events(self) -> None:
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.canvas.bind("<ButtonPress-2>", self.start_center_scale)
        self.canvas.bind("<B2-Motion>", self.center_scale_drag)
        self.canvas.bind("<ButtonRelease-2>", self.end_drag)
        self.canvas.bind("<ButtonPress-3>", self.start_canvas_pan)
        self.canvas.bind("<B3-Motion>", self.drag_canvas_pan)
        self.canvas.bind("<ButtonRelease-3>", self.end_canvas_pan)
        self.canvas.bind("<Motion>", self.update_cursor)
        self.canvas.bind("<Leave>", lambda _event: self.canvas.configure(cursor=""))
        self.canvas.bind("<MouseWheel>", self.zoom_with_wheel)
        self.canvas.bind("<Button-4>", self.zoom_with_wheel)
        self.canvas.bind("<Button-5>", self.zoom_with_wheel)
        self.bind("<Return>", lambda _event: self.apply_target_size())
        self.bind("<Delete>", self.delete_image)
        self.bind("<BackSpace>", self.delete_image)

    def _setup_drag_drop(self) -> None:
        if TkinterDnD is None or DND_FILES is None:
            return
        for widget in (self, self.canvas):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.drop_image)

    def load_image(self) -> None:
        if Image is None:
            return
        path = filedialog.askopenfilename(filetypes=SUPPORTED_OPEN_TYPES)
        if path:
            self.load_image_path(path)

    def drop_image(self, event: tk.Event) -> None:
        files = self.tk.splitlist(event.data)
        if not files:
            return
        self.load_image_path(files[0])

    def load_image_path(self, path: str | Path) -> None:
        if Image is None:
            return
        image_path = Path(path)
        if image_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            messagebox.showwarning("格式不支持", "请导入 PNG、JPG、WEBP、BMP、GIF 或 TIFF 图片。")
            return
        try:
            image = Image.open(image_path)
            image.load()
            self.source_image = image.convert("RGBA")
        except Exception as exc:
            messagebox.showerror("导入失败", f"无法打开图片：\n{exc}")
            return
        self.source_path = image_path
        self.repair_mask = None
        self.repair_rect_start = None
        self.repair_rect_preview = None
        self.repair_last_source_point = None
        self.repair_brush_preview_point = None
        self.reset_image_fit()

    def open_image_when_empty(self, _event: tk.Event) -> None:
        if self.source_image is None:
            self.load_image()

    def delete_image(self, _event: tk.Event | None = None) -> None:
        if self.source_image is None:
            return
        self.source_path = None
        self.source_image = None
        self.preview_image_ref = None
        self.mask_preview_ref = None
        self.repair_mask = None
        self.repair_rect_start = None
        self.repair_rect_preview = None
        self.repair_last_source_point = None
        self.repair_brush_preview_point = None
        self.image_scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.canvas.configure(cursor="")
        self._update_status()
        self.redraw()

    def _on_repair_mode_changed(self) -> None:
        if self.repair_mode.get():
            self.canvas_resize_mode.set(False)
            if self.source_image is None:
                self.status.set("请先导入图片，再进入修复模式。")
            else:
                self._ensure_repair_mask()
                self.status.set("修复模式：用画笔涂抹或矩形框选水印区域，然后点击应用修复。")
        else:
            self.repair_rect_start = None
            self.repair_rect_preview = None
            self._update_status()
        self.redraw()

    def _on_canvas_resize_mode_changed(self) -> None:
        if self.canvas_resize_mode.get():
            self.repair_mode.set(False)
            self.repair_rect_start = None
            self.repair_rect_preview = None
            self.status.set("调整画布：拖动画布边缘或角点修改输出尺寸，图片位置不会重新适配。")
        else:
            self.canvas_resize_region = None
            self.canvas_resize_start = None
            self.canvas_resize_initial_size = None
            self._update_status()
        self.redraw()

    def _ensure_repair_mask(self) -> Image.Image | None:
        if self.source_image is None or Image is None:
            return None
        if self.repair_mask is None or self.repair_mask.size != self.source_image.size:
            self.repair_mask = Image.new("L", self.source_image.size, 0)
        return self.repair_mask

    def clear_repair_mask(self, redraw: bool = True) -> None:
        if self.source_image is not None and Image is not None:
            self.repair_mask = Image.new("L", self.source_image.size, 0)
        else:
            self.repair_mask = None
        self.repair_rect_start = None
        self.repair_rect_preview = None
        self.repair_last_source_point = None
        self.repair_brush_preview_point = None
        if redraw:
            self.status.set("已清空修复标记。")
            self.redraw()

    def apply_watermark_repair(self) -> None:
        if self.source_image is None:
            messagebox.showwarning("未导入图片", "请先导入一张图片。")
            return
        mask = self._ensure_repair_mask()
        if mask is None:
            return
        try:
            self.source_image = remove_masked_area(
                self.source_image,
                mask,
                radius=self.repair_radius.get(),
            )
        except WatermarkRemovalError as exc:
            messagebox.showwarning("修复失败", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("修复失败", f"局部修复时出错：\n{exc}")
            return
        self.clear_repair_mask(redraw=False)
        self.status.set("局部修复已应用，可继续裁剪或导出。")
        self.redraw()

    def apply_target_size(self) -> None:
        if not self._valid_target_size():
            return
        self.reset_image_fit()

    def reset_image_fit(self) -> None:
        if self.source_image is None or not self._valid_target_size():
            self._update_status()
            self.redraw()
            return

        src_w, src_h = self.source_image.size
        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        if self.fit_mode.get() == "cover":
            self.image_scale = max(dst_w / src_w, dst_h / src_h)
        else:
            self.image_scale = min(1.0, dst_w / src_w, dst_h / src_h)
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.view_pan_x = 0.0
        self.view_pan_y = 0.0
        self._update_status()
        self.redraw()

    def restore_original_size(self) -> None:
        if self.source_image is None:
            messagebox.showwarning("未导入图片", "请先导入一张图片。")
            return
        src_w, src_h = self.source_image.size
        self.target_width.set(src_w)
        self.target_height.set(src_h)
        self.image_scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.view_pan_x = 0.0
        self.view_pan_y = 0.0
        self.canvas_resize_mode.set(False)
        self._update_status()
        self.status.set(f"已恢复原图尺寸：{src_w} x {src_h}。")
        self.redraw()

    def center_image(self) -> None:
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._update_status()
        self.redraw()

    def start_drag(self, event: tk.Event) -> None:
        if self.source_image is None:
            self.load_image()
            return
        if self.repair_mode.get():
            self.start_repair_mark(event)
            return
        if self.canvas_resize_mode.get():
            self.start_canvas_resize(event)
            return
        hit_region = self._image_hit_region(event.x, event.y)
        if hit_region is None:
            return
        self.last_mouse = (event.x, event.y)
        self.drag_mode = "scale" if hit_region != "inside" else "move"

    def drag(self, event: tk.Event) -> None:
        if self.source_image is None or self.last_mouse is None:
            return
        if self.drag_mode in {"repair_brush", "repair_rect"}:
            self.drag_repair_mark(event)
            return
        if self.drag_mode == "resize_canvas":
            self.drag_canvas_resize(event)
            return
        last_x, last_y = self.last_mouse
        dx = event.x - last_x
        dy = event.y - last_y
        self.last_mouse = (event.x, event.y)

        if self.drag_mode == "scale":
            self._scale_from_center(dx, dy, event.x, event.y)
        elif self.drag_mode == "move":
            self.offset_x += dx / self.view_scale
            self.offset_y += dy / self.view_scale
        self._update_status()
        self.redraw()

    def end_drag(self, _event: tk.Event) -> None:
        if self.drag_mode == "repair_rect":
            self.finish_repair_rect()
        if self.drag_mode == "repair_brush":
            self.repair_last_source_point = None
        if self.drag_mode == "resize_canvas":
            self.canvas_resize_region = None
            self.canvas_resize_start = None
            self.canvas_resize_initial_size = None
        self.drag_mode = None
        self.last_mouse = None

    def start_center_scale(self, event: tk.Event) -> None:
        if (
            self.repair_mode.get()
            or self.source_image is None
            or self._image_hit_region(event.x, event.y) != "inside"
        ):
            return
        self.drag_mode = "middle_scale"
        self.last_mouse = (event.x, event.y)

    def center_scale_drag(self, event: tk.Event) -> None:
        if self.source_image is None or self.last_mouse is None:
            return
        last_x, last_y = self.last_mouse
        dx = event.x - last_x
        dy = event.y - last_y
        self.last_mouse = (event.x, event.y)
        factor = 1 + ((dx - dy) * 0.006)
        if factor <= 0:
            factor = 0.1
        self.image_scale = self._clamp_scale(self.image_scale * factor)
        self._update_status()
        self.redraw()

    def start_canvas_pan(self, event: tk.Event) -> None:
        if not self._valid_target_size(show_error=False):
            return
        self.canvas_pan_start = (event.x, event.y)
        self.canvas_pan_initial = (self.view_pan_x, self.view_pan_y)
        self._set_canvas_cursor("fleur")

    def drag_canvas_pan(self, event: tk.Event) -> None:
        if self.canvas_pan_start is None or self.canvas_pan_initial is None:
            return
        start_x, start_y = self.canvas_pan_start
        initial_x, initial_y = self.canvas_pan_initial
        self.view_pan_x = initial_x + event.x - start_x
        self.view_pan_y = initial_y + event.y - start_y
        self.redraw()

    def end_canvas_pan(self, _event: tk.Event) -> None:
        self.canvas_pan_start = None
        self.canvas_pan_initial = None
        self._set_canvas_cursor("")

    def start_canvas_resize(self, event: tk.Event) -> None:
        region = self._output_hit_region(event.x, event.y)
        if region is None:
            return
        self.drag_mode = "resize_canvas"
        self.last_mouse = (event.x, event.y)
        self.canvas_resize_region = region
        self.canvas_resize_start = (event.x, event.y)
        self.canvas_resize_initial_size = (
            self.target_width.get(),
            self.target_height.get(),
        )

    def drag_canvas_resize(self, event: tk.Event) -> None:
        if (
            self.canvas_resize_start is None
            or self.canvas_resize_initial_size is None
            or self.canvas_resize_region is None
        ):
            return
        old_left = self.view_left
        old_top = self.view_top
        old_scale = max(0.01, self.view_scale)
        start_x, start_y = self.canvas_resize_start
        initial_w, initial_h = self.canvas_resize_initial_size
        dx = round((event.x - start_x) / old_scale)
        dy = round((event.y - start_y) / old_scale)
        region = self.canvas_resize_region
        new_w = initial_w
        new_h = initial_h
        if "left" in region:
            new_w = initial_w - dx
        elif "right" in region:
            new_w = initial_w + dx
        if "top" in region:
            new_h = initial_h - dy
        elif "bottom" in region:
            new_h = initial_h + dy
        new_w = max(1, min(20000, new_w))
        new_h = max(1, min(20000, new_h))
        old_w, old_h = self.target_width.get(), self.target_height.get()
        if new_w == old_w and new_h == old_h:
            return

        desired_left = old_left
        desired_top = old_top
        if "left" in region:
            desired_left = old_left + (old_w - new_w) * old_scale
        if "top" in region:
            desired_top = old_top + (old_h - new_h) * old_scale

        self.target_width.set(new_w)
        self.target_height.set(new_h)
        self._preserve_view_scale(new_w, new_h, old_scale)
        self._set_view_origin(desired_left, desired_top, new_w, new_h)
        self.offset_x += (old_w - new_w) / 2 + (old_left - desired_left) / old_scale
        self.offset_y += (old_h - new_h) / 2 + (old_top - desired_top) / old_scale
        self._update_status()
        self.status.set(f"画布尺寸已调整为 {new_w} x {new_h}。")
        self.redraw()

    def start_repair_mark(self, event: tk.Event) -> None:
        if self._ensure_repair_mask() is None:
            return
        source_point = self._canvas_to_source_point(event.x, event.y)
        if source_point is None:
            return
        self.last_mouse = (event.x, event.y)
        if self.repair_tool.get() == "矩形":
            self.drag_mode = "repair_rect"
            self.repair_rect_start = source_point
            self.repair_rect_preview = (*source_point, *source_point)
        else:
            self.drag_mode = "repair_brush"
            self.repair_last_source_point = source_point
            self.repair_brush_preview_point = source_point
            self._paint_repair_brush(source_point, source_point)
        self.redraw()

    def drag_repair_mark(self, event: tk.Event) -> None:
        source_point = self._canvas_to_source_point(event.x, event.y)
        if source_point is None:
            return
        self.last_mouse = (event.x, event.y)
        if self.drag_mode == "repair_rect" and self.repair_rect_start is not None:
            x1, y1 = self.repair_rect_start
            x2, y2 = source_point
            self.repair_rect_preview = (x1, y1, x2, y2)
        elif self.drag_mode == "repair_brush":
            self._paint_repair_brush(
                self.repair_last_source_point or source_point,
                source_point,
            )
            self.repair_last_source_point = source_point
            self.repair_brush_preview_point = source_point
        self.redraw()

    def finish_repair_rect(self) -> None:
        if (
            self.repair_mask is None
            or self.repair_rect_preview is None
            or ImageDraw is None
        ):
            return
        x1, y1, x2, y2 = self.repair_rect_preview
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if right - left < 2 or bottom - top < 2:
            self.repair_rect_preview = None
            return
        draw = ImageDraw.Draw(self.repair_mask)
        draw.rectangle((left, top, right, bottom), fill=255)
        self.repair_rect_preview = None

    def _paint_repair_brush(
        self,
        start_point: tuple[int, int],
        end_point: tuple[int, int],
    ) -> None:
        if self.repair_mask is None or ImageDraw is None:
            return
        radius = self._repair_brush_radius()
        width = radius * 2
        draw = ImageDraw.Draw(self.repair_mask)
        draw.line((start_point, end_point), fill=255, width=width)
        for x, y in (start_point, end_point):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)

    def _repair_brush_radius(self) -> int:
        try:
            size = int(self.brush_size.get())
        except (tk.TclError, ValueError):
            size = 36
        return max(2, size // 2)

    def update_cursor(self, event: tk.Event) -> None:
        if self.repair_mode.get() and self.source_image is not None:
            source_point = self._canvas_to_source_point(event.x, event.y)
            if source_point != self.repair_brush_preview_point:
                self.repair_brush_preview_point = source_point
                self.redraw()
            self._set_canvas_cursor("crosshair")
            return
        if self.canvas_resize_mode.get() and self.source_image is not None:
            hit_region = self._output_hit_region(event.x, event.y)
            self._set_canvas_cursor(self._resize_cursor(hit_region))
            return
        if self.source_image is None:
            self.canvas.configure(cursor="hand2")
            return
        hit_region = self._image_hit_region(event.x, event.y)
        if hit_region in {"top_left", "bottom_right"}:
            cursor = "size_nw_se"
        elif hit_region in {"top_right", "bottom_left"}:
            cursor = "size_ne_sw"
        elif hit_region in {"left", "right"}:
            cursor = "size_we"
        elif hit_region in {"top", "bottom"}:
            cursor = "size_ns"
        elif hit_region == "inside":
            cursor = "fleur"
        else:
            cursor = ""
        self._set_canvas_cursor(cursor)

    def _resize_cursor(self, hit_region: str | None) -> str:
        if hit_region in {"top_left", "bottom_right"}:
            return "size_nw_se"
        if hit_region in {"top_right", "bottom_left"}:
            return "size_ne_sw"
        if hit_region in {"left", "right"}:
            return "size_we"
        if hit_region in {"top", "bottom"}:
            return "size_ns"
        return ""

    def _set_canvas_cursor(self, cursor: str) -> None:
        try:
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            self.canvas.configure(cursor="")

    def zoom_with_wheel(self, event: tk.Event) -> None:
        direction = 1
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            direction = -1
        factor = 1.08 if direction > 0 else 1 / 1.08
        if self.source_image is not None and self._point_in_output_rect(event.x, event.y):
            self.image_scale = self._clamp_scale(self.image_scale * factor)
        else:
            self.view_zoom = self._clamp_view_zoom(self.view_zoom * factor)
        self._update_status()
        self.redraw()

    def export_image(self) -> None:
        if self.source_image is None:
            messagebox.showwarning("未导入图片", "请先导入一张图片。")
            return
        if not self._valid_target_size():
            return

        fmt = self.output_format.get()
        extension = ".jpg" if fmt == "JPG" else f".{fmt.lower()}"
        default_name = "cropped-image" + extension
        if self.source_path is not None:
            default_name = self.source_path.stem + "-crop" + extension
        path = filedialog.asksaveasfilename(
            defaultextension=extension,
            initialfile=default_name,
            filetypes=SUPPORTED_SAVE_TYPES,
        )
        if not path:
            return

        try:
            output = self.render_output()
            save_format = "JPEG" if fmt == "JPG" else fmt
            save_kwargs = {}
            if save_format in {"JPEG", "WEBP"}:
                save_kwargs["quality"] = max(1, min(100, self.quality.get()))
            if save_format == "JPEG":
                output = output.convert("RGB")
            output.save(path, save_format, **save_kwargs)
        except Exception as exc:
            messagebox.showerror("导出失败", f"无法导出图片：\n{exc}")
            return
        self.status.set(f"已导出：{path}")

    def render_output(self) -> Image.Image:
        if self.source_image is None:
            raise RuntimeError("No source image loaded.")

        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        canvas = Image.new("RGBA", (dst_w, dst_h), "white")

        self._paste_scaled_source(canvas, self.source_image)
        return canvas

    def render_repair_overlay(self) -> Image.Image:
        if self.source_image is None:
            raise RuntimeError("No source image loaded.")
        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        overlay = Image.new("RGBA", (dst_w, dst_h), (0, 0, 0, 0))
        if self.repair_mask is None:
            return overlay
        mask_color = Image.new("RGBA", self.repair_mask.size, (255, 92, 106, 95))
        mask_color.putalpha(self.repair_mask.point(lambda value: min(110, value)))
        self._paste_scaled_source(overlay, mask_color)
        return overlay

    def render_preview(self, width: int, height: int) -> Image.Image:
        canvas = Image.new("RGBA", (width, height), "white")
        if self.source_image is None:
            return canvas
        src_w, src_h = self.source_image.size
        scaled_w = max(1, round(src_w * self.image_scale * self.view_scale))
        scaled_h = max(1, round(src_h * self.image_scale * self.view_scale))
        resized = self.source_image.resize((scaled_w, scaled_h), Image.Resampling.BICUBIC)
        left = round((width - scaled_w) / 2 + self.offset_x * self.view_scale)
        top = round((height - scaled_h) / 2 + self.offset_y * self.view_scale)
        canvas.alpha_composite(resized, (left, top))
        return canvas

    def render_repair_preview_overlay(self, width: int, height: int) -> Image.Image:
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        if self.source_image is None or self.repair_mask is None:
            return overlay
        mask_color = Image.new("RGBA", self.repair_mask.size, (255, 92, 106, 95))
        mask_color.putalpha(self.repair_mask.point(lambda value: min(110, value)))
        src_w, src_h = self.source_image.size
        scaled_w = max(1, round(src_w * self.image_scale * self.view_scale))
        scaled_h = max(1, round(src_h * self.image_scale * self.view_scale))
        resized = mask_color.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)
        left = round((width - scaled_w) / 2 + self.offset_x * self.view_scale)
        top = round((height - scaled_h) / 2 + self.offset_y * self.view_scale)
        overlay.alpha_composite(resized, (left, top))
        return overlay

    def _paste_scaled_source(self, canvas: Image.Image, source: Image.Image) -> None:
        if self.source_image is None:
            return
        src_w, src_h = self.source_image.size
        scaled_w = max(1, round(src_w * self.image_scale))
        scaled_h = max(1, round(src_h * self.image_scale))
        resample = Image.Resampling.LANCZOS if source.mode != "L" else Image.Resampling.NEAREST
        resized = source.resize((scaled_w, scaled_h), resample)

        left = round((canvas.width - scaled_w) / 2 + self.offset_x)
        top = round((canvas.height - scaled_h) / 2 + self.offset_y)
        canvas.alpha_composite(resized, (left, top))

    def redraw(self) -> None:
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self._draw_workspace_background(width, height)
        if not self._valid_target_size(show_error=False):
            self._draw_centered_text(width, height, "请输入有效的目标尺寸")
            return

        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        self.view_scale = self._base_view_scale(width, height, dst_w, dst_h)
        self.view_scale *= self.view_zoom
        self.view_scale = max(0.01, self.view_scale)
        view_w = dst_w * self.view_scale
        view_h = dst_h * self.view_scale
        self.view_left = (width - view_w) / 2 + self.view_pan_x
        self.view_top = (height - view_h) / 2 + self.view_pan_y

        self._draw_output_shadow(view_w, view_h)
        self.canvas.create_rectangle(
            self.view_left,
            self.view_top,
            self.view_left + view_w,
            self.view_top + view_h,
            fill="white",
            outline="#263958",
            width=2,
        )

        if self.source_image is None:
            self._draw_drop_card(width, height)
            return

        preview_w = max(1, round(view_w))
        preview_h = max(1, round(view_h))
        preview = self.render_preview(preview_w, preview_h)
        self.preview_image_ref = ImageTk.PhotoImage(preview)
        self.canvas.create_image(
            self.view_left,
            self.view_top,
            image=self.preview_image_ref,
            anchor=tk.NW,
        )
        self._draw_repair_mask_overlay(preview_w, preview_h)
        self.canvas.create_rectangle(
            self.view_left,
            self.view_top,
            self.view_left + view_w,
            self.view_top + view_h,
            outline=ACCENT,
            width=2,
        )
        if self.canvas_resize_mode.get():
            self._draw_canvas_resize_handles(view_w, view_h)
        else:
            self._draw_image_handles()

    def _base_view_scale(self, width: int, height: int, dst_w: int, dst_h: int) -> float:
        margin = max(36, round(min(width, height) * 0.07))
        available_w = max(1, width - margin * 2)
        available_h = max(1, height - margin * 2)
        return max(0.01, min(available_w / dst_w, available_h / dst_h))

    def _preserve_view_scale(self, dst_w: int, dst_h: int, scale: float) -> None:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        base_scale = self._base_view_scale(width, height, dst_w, dst_h)
        self.view_zoom = max(0.01, scale / base_scale)

    def _set_view_origin(self, left: float, top: float, dst_w: int, dst_h: int) -> None:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        view_w = dst_w * self.view_scale
        view_h = dst_h * self.view_scale
        self.view_pan_x = left - (width - view_w) / 2
        self.view_pan_y = top - (height - view_h) / 2

    def _draw_repair_mask_overlay(self, preview_w: int, preview_h: int) -> None:
        if (
            not self.repair_mode.get()
            or self.repair_mask is None
            or self.source_image is None
            or ImageTk is None
        ):
            return
        overlay = self.render_repair_preview_overlay(preview_w, preview_h)
        if self.repair_rect_preview is not None and ImageDraw is not None:
            draw = ImageDraw.Draw(overlay)
            x1, y1, x2, y2 = self._source_rect_to_preview_rect(
                self.repair_rect_preview,
                preview_w,
                preview_h,
            )
            draw.rectangle((x1, y1, x2, y2), outline=(255, 92, 106, 230), width=3)
            draw.rectangle((x1, y1, x2, y2), fill=(255, 92, 106, 60))
        self.mask_preview_ref = ImageTk.PhotoImage(overlay)
        self.canvas.create_image(
            self.view_left,
            self.view_top,
            image=self.mask_preview_ref,
            anchor=tk.NW,
        )
        self._draw_brush_preview()

    def _draw_brush_preview(self) -> None:
        if (
            not self.repair_mode.get()
            or self.source_image is None
            or self.repair_tool.get() != "画笔"
            or self.repair_brush_preview_point is None
        ):
            return
        x, y = self._source_point_to_canvas(self.repair_brush_preview_point)
        radius = self._repair_brush_radius() * self.image_scale * self.view_scale
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            outline="#ff8a94",
            width=2,
        )
        self.canvas.create_oval(
            x - 2,
            y - 2,
            x + 2,
            y + 2,
            fill="#ff8a94",
            outline="",
        )

    def _draw_canvas_resize_handles(self, view_w: float, view_h: float) -> None:
        left = self.view_left
        top = self.view_top
        right = left + view_w
        bottom = top + view_h
        self.canvas.create_rectangle(left, top, right, bottom, outline=WARNING, width=2)
        for x, y in (
            (left, top),
            ((left + right) / 2, top),
            (right, top),
            (left, (top + bottom) / 2),
            (right, (top + bottom) / 2),
            (left, bottom),
            ((left + right) / 2, bottom),
            (right, bottom),
        ):
            self.canvas.create_rectangle(
                x - HANDLE_SIZE / 2,
                y - HANDLE_SIZE / 2,
                x + HANDLE_SIZE / 2,
                y + HANDLE_SIZE / 2,
                fill=WARNING,
                outline="#ffd3d8",
            )

    def _draw_workspace_background(self, width: int, height: int) -> None:
        self.canvas.create_rectangle(0, 0, width, height, fill=WORK_BG, outline="")

    def _draw_output_shadow(self, view_w: float, view_h: float) -> None:
        left = self.view_left
        top = self.view_top
        right = left + view_w
        bottom = top + view_h
        self.canvas.create_rectangle(left - 9, top - 9, right + 9, bottom + 9, fill="#0d1628", outline="")
        self.canvas.create_rectangle(left - 4, top - 4, right + 4, bottom + 4, outline="#22344f", width=2)

    def _draw_drop_card(self, width: int, height: int) -> None:
        card_w = min(430, max(320, width - 120))
        card_h = 164
        x1 = (width - card_w) / 2
        y1 = (height - card_h) / 2
        x2 = x1 + card_w
        y2 = y1 + card_h
        self._round_rect(x1, y1, x2, y2, 30, fill=SURFACE_BG, outline="")
        self.canvas.create_text(
            width / 2,
            y1 + 48,
            text="选择要裁剪的图片",
            fill=TEXT_MAIN,
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        self.canvas.create_text(
            width / 2,
            y1 + 88,
            text="点击导入，或直接把图片拖到这里",
            fill=TEXT_MUTED,
            font=("Microsoft YaHei UI", 11),
        )
        self.canvas.create_text(
            width / 2,
            y1 + 124,
            text="PNG  JPG  WEBP  BMP  GIF  TIFF",
            fill="#b7c8df",
            font=("Microsoft YaHei UI", 10, "bold"),
        )

    def _round_rect(self, x1: float, y1: float, x2: float, y2: float, radius: int, **kwargs) -> int:
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _draw_centered_text(self, width: int, height: int, text: str) -> None:
        self.canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            fill=TEXT_MAIN,
            font=("Microsoft YaHei UI", 15, "bold"),
        )

    def _draw_image_handles(self) -> None:
        rect = self._image_rect_on_canvas()
        if rect is None:
            return
        left, top, right, bottom = rect
        self.canvas.create_rectangle(left, top, right, bottom, outline=WARNING, width=2)
        for x, y in (
            (left, top),
            ((left + right) / 2, top),
            (right, top),
            (left, (top + bottom) / 2),
            (right, (top + bottom) / 2),
            (left, bottom),
            ((left + right) / 2, bottom),
            (right, bottom),
        ):
            self.canvas.create_oval(
                x - HANDLE_SIZE,
                y - HANDLE_SIZE,
                x + HANDLE_SIZE,
                y + HANDLE_SIZE,
                outline="",
                fill="#2d1720",
            )
            self.canvas.create_rectangle(
                x - HANDLE_SIZE / 2,
                y - HANDLE_SIZE / 2,
                x + HANDLE_SIZE / 2,
                y + HANDLE_SIZE / 2,
                fill=WARNING,
                outline="#ffd3d8",
            )

    def _image_rect_on_canvas(self) -> tuple[float, float, float, float] | None:
        if self.source_image is None:
            return None
        src_w, src_h = self.source_image.size
        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        scaled_w = src_w * self.image_scale
        scaled_h = src_h * self.image_scale
        left_output = (dst_w - scaled_w) / 2 + self.offset_x
        top_output = (dst_h - scaled_h) / 2 + self.offset_y
        left = self.view_left + left_output * self.view_scale
        top = self.view_top + top_output * self.view_scale
        return (
            left,
            top,
            left + scaled_w * self.view_scale,
            top + scaled_h * self.view_scale,
        )

    def _canvas_to_source_point(self, x: int, y: int) -> tuple[int, int] | None:
        rect = self._image_rect_on_canvas()
        if rect is None or self.source_image is None:
            return None
        left, top, right, bottom = rect
        if not (left <= x <= right and top <= y <= bottom):
            return None
        scale = self.image_scale * self.view_scale
        if scale <= 0:
            return None
        src_x = int(round((x - left) / scale))
        src_y = int(round((y - top) / scale))
        src_w, src_h = self.source_image.size
        if src_x < 0 or src_y < 0 or src_x >= src_w or src_y >= src_h:
            return None
        return src_x, src_y

    def _source_point_to_canvas(self, point: tuple[int, int]) -> tuple[float, float]:
        rect = self._image_rect_on_canvas()
        if rect is None:
            return 0.0, 0.0
        left, top, _right, _bottom = rect
        x, y = point
        scale = self.image_scale * self.view_scale
        return left + x * scale, top + y * scale

    def _source_rect_to_output_rect(
        self,
        rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        if self.source_image is None:
            return 0, 0, 0, 0
        src_w, src_h = self.source_image.size
        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        scaled_w = src_w * self.image_scale
        scaled_h = src_h * self.image_scale
        left_output = (dst_w - scaled_w) / 2 + self.offset_x
        top_output = (dst_h - scaled_h) / 2 + self.offset_y
        x1, y1, x2, y2 = rect
        return (
            round(left_output + x1 * self.image_scale),
            round(top_output + y1 * self.image_scale),
            round(left_output + x2 * self.image_scale),
            round(top_output + y2 * self.image_scale),
        )

    def _source_rect_to_preview_rect(
        self,
        rect: tuple[int, int, int, int],
        preview_w: int,
        preview_h: int,
    ) -> tuple[int, int, int, int]:
        if self.source_image is None:
            return 0, 0, 0, 0
        src_w, src_h = self.source_image.size
        scaled_w = src_w * self.image_scale * self.view_scale
        scaled_h = src_h * self.image_scale * self.view_scale
        left = (preview_w - scaled_w) / 2 + self.offset_x * self.view_scale
        top = (preview_h - scaled_h) / 2 + self.offset_y * self.view_scale
        x1, y1, x2, y2 = rect
        scale = self.image_scale * self.view_scale
        return (
            round(left + x1 * scale),
            round(top + y1 * scale),
            round(left + x2 * scale),
            round(top + y2 * scale),
        )

    def _point_in_output_rect(self, x: int, y: int) -> bool:
        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        right = self.view_left + dst_w * self.view_scale
        bottom = self.view_top + dst_h * self.view_scale
        return self.view_left <= x <= right and self.view_top <= y <= bottom

    def _output_hit_region(self, x: int, y: int) -> str | None:
        dst_w, dst_h = self.target_width.get(), self.target_height.get()
        left = self.view_left
        top = self.view_top
        right = left + dst_w * self.view_scale
        bottom = top + dst_h * self.view_scale
        edge = HANDLE_SIZE * 1.9
        near_left = abs(x - left) <= edge and top - edge <= y <= bottom + edge
        near_right = abs(x - right) <= edge and top - edge <= y <= bottom + edge
        near_top = abs(y - top) <= edge and left - edge <= x <= right + edge
        near_bottom = abs(y - bottom) <= edge and left - edge <= x <= right + edge
        if near_left and near_top:
            return "top_left"
        if near_right and near_top:
            return "top_right"
        if near_left and near_bottom:
            return "bottom_left"
        if near_right and near_bottom:
            return "bottom_right"
        if near_left:
            return "left"
        if near_right:
            return "right"
        if near_top:
            return "top"
        if near_bottom:
            return "bottom"
        return None

    def _image_hit_region(self, x: int, y: int) -> str | None:
        rect = self._image_rect_on_canvas()
        if rect is None:
            return None
        left, top, right, bottom = rect
        edge = HANDLE_SIZE * 1.8
        near_left = abs(x - left) <= edge and top - edge <= y <= bottom + edge
        near_right = abs(x - right) <= edge and top - edge <= y <= bottom + edge
        near_top = abs(y - top) <= edge and left - edge <= x <= right + edge
        near_bottom = abs(y - bottom) <= edge and left - edge <= x <= right + edge

        if near_left and near_top:
            return "top_left"
        if near_right and near_top:
            return "top_right"
        if near_left and near_bottom:
            return "bottom_left"
        if near_right and near_bottom:
            return "bottom_right"
        if near_left:
            return "left"
        if near_right:
            return "right"
        if near_top:
            return "top"
        if near_bottom:
            return "bottom"
        if left <= x <= right and top <= y <= bottom:
            return "inside"
        return None

    def _near_image_corner(self, x: int, y: int) -> bool:
        rect = self._image_rect_on_canvas()
        if rect is None:
            return False
        left, top, right, bottom = rect
        radius = HANDLE_SIZE * 1.7
        for cx, cy in ((left, top), (right, top), (left, bottom), (right, bottom)):
            if math.hypot(x - cx, y - cy) <= radius:
                return True
        return False

    def _scale_from_center(self, dx: int, dy: int, x: int, y: int) -> None:
        rect = self._image_rect_on_canvas()
        if rect is None:
            return
        left, top, right, bottom = rect
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        before = max(1.0, math.hypot(x - dx - center_x, y - dy - center_y))
        after = max(1.0, math.hypot(x - center_x, y - center_y))
        self.image_scale = self._clamp_scale(self.image_scale * (after / before))

    def _clamp_scale(self, scale: float) -> float:
        return max(MIN_SCALE, min(MAX_SCALE, scale))

    def _clamp_view_zoom(self, scale: float) -> float:
        return max(MIN_VIEW_ZOOM, min(MAX_VIEW_ZOOM, scale))

    def _valid_target_size(self, show_error: bool = True) -> bool:
        try:
            width = int(self.target_width.get())
            height = int(self.target_height.get())
        except (tk.TclError, ValueError):
            if show_error:
                messagebox.showerror("尺寸无效", "宽度和高度必须是数字。")
            return False
        if width < 1 or height < 1 or width > 20000 or height > 20000:
            if show_error:
                messagebox.showerror("尺寸无效", "宽度和高度必须在 1 到 20000 之间。")
            return False
        return True

    def _update_status(self) -> None:
        mode = "填充裁剪" if self.fit_mode.get() == "cover" else "白底留边"
        self.target_info.set(f"目标 {self.target_width.get()} x {self.target_height.get()}")
        self.mode_info.set(mode)
        if self.source_image is None:
            self.status.set("选择或拖拽图片开始裁剪。")
            self.source_info.set("未导入图片")
            self.zoom_info.set("缩放 100%")
            return
        src_w, src_h = self.source_image.size
        scaled_w = round(src_w * self.image_scale)
        scaled_h = round(src_h * self.image_scale)
        self.source_info.set(f"源图 {src_w} x {src_h}")
        self.zoom_info.set(f"缩放 {self.image_scale * 100:.1f}%")
        self.status.set(
            f"当前图片显示尺寸 {scaled_w} x {scaled_h}，可拖拽移动、滚轮缩放、拖动角点缩放。"
        )


def main() -> None:
    enable_high_dpi()
    app = ImageCropperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
