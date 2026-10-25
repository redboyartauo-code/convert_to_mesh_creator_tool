import json
import math
import os
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

try:
    import trimesh
except ImportError:
    trimesh = None


APP_TITLE = "Convert to Mesh – Creator Tool"
CREATOR = "redboyartauo-code"
VORTEX_URL = "https://playvortex.io/"
DEFAULT_MAX_FACES = 4000
TARGET_SIZE = 8.0
WARNING_TEXT = (
    "Note: Vortex has no documented native mesh API, so this output approximates "
    "triangles with Parts. Dense meshes create many objects and can hurt performance. "
    "Start with a low triangle count."
)

DARK_THEME = {
    "bg": "#0F1117",
    "panel": "#171A23",
    "panel_alt": "#1E2230",
    "border": "#2A2F3F",
    "text": "#E6E8EF",
    "muted": "#8A90A2",
    "accent": "#7C5CFF",
    "accent_hover": "#9478FF",
    "link": "#9478FF",
    "warning": "#F5A524",
    "warning_bg": "#2A2110",
    "success": "#3DDC97",
    "sun": "#FFC53D",
    "moon": "#C9CFEA",
}

LIGHT_THEME = {
    "bg": "#F4F5F9",
    "panel": "#FFFFFF",
    "panel_alt": "#EEF0F6",
    "border": "#D9DCE6",
    "text": "#1B1E28",
    "muted": "#6B7185",
    "accent": "#6A4DF0",
    "accent_hover": "#5B3DE0",
    "link": "#5B3DE0",
    "warning": "#9A5B00",
    "warning_bg": "#FFF4DC",
    "success": "#14865A",
    "sun": "#F5B700",
    "moon": "#8C93B5",
}

FONT_BODY = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_LINK = ("Segoe UI", 10, "underline")
FONT_TITLE = ("Segoe UI Semibold", 20)
FONT_STAT = ("Segoe UI Semibold", 18)


def load_glb(path):
    loaded = trimesh.load(path, force="scene", process=False)
    meshes = []
    if isinstance(loaded, trimesh.Scene):
        for node_name in loaded.graph.nodes_geometry:
            transform, geometry_name = loaded.graph[node_name]
            geom = loaded.geometry.get(geometry_name)
            if geom is None or not isinstance(geom, trimesh.Trimesh):
                continue
            geom = geom.copy()
            geom.apply_transform(transform)
            if len(geom.vertices) and len(geom.faces):
                meshes.append(geom)
    elif isinstance(loaded, trimesh.Trimesh):
        meshes = [loaded]
    if not meshes:
        raise ValueError("No triangle mesh was found in this GLB.")
    return meshes


def simplify_mesh(meshes, max_faces):
    combined = trimesh.util.concatenate(meshes)
    if len(combined.faces) > max_faces:
        try:
            combined = combined.simplify_quadric_decimation(face_count=max_faces)
        except Exception:
            count = len(combined.faces)
            indices = (
                [round(i * (count - 1) / (max_faces - 1)) for i in range(max_faces)]
                if max_faces > 1
                else [0]
            )
            combined = combined.submesh([indices], append=True, repair=False)
    combined.remove_unreferenced_vertices()
    return combined


def lua_number(value):
    if abs(float(value)) < 1e-9:
        value = 0
    return f"{float(value):.5f}".rstrip("0").rstrip(".") or "0"


def generate_lua(mesh, object_name, anchor_name, scale):
    vertices = mesh.vertices.astype(float)
    faces = mesh.faces.astype(int)

    bounds = mesh.bounds
    center = (bounds[0] + bounds[1]) / 2.0
    largest = max(float(max(bounds[1] - bounds[0])), 1e-6)
    factor = (TARGET_SIZE / largest) * scale
    centered = (vertices - center) * factor

    lines = [
        f"-- Created by {CREATOR}",
        "local Workspace = game:GetService('Workspace')",
        f"local anchorName = {json.dumps(anchor_name)}",
        f"local objectName = {json.dumps(object_name)}",
        "local anchor = Workspace:WaitForChild(anchorName)",
        "local previous = Workspace:FindFirstChild(objectName .. '_Generated')",
        "if previous then previous:Destroy() end",
        "local model = Instance.new('Model')",
        "model.Name = objectName .. '_Generated'",
        "model.Parent = Workspace",
        "local anchorCF = anchor.CFrame",
        "local vertices = {",
    ]
    lines += [
        f"    Vector3.new({lua_number(x)}, {lua_number(y)}, {lua_number(z)}),"
        for x, y, z in centered
    ]
    lines.append("}")
    lines.append("local triangles = {")
    lines += [f"    {{{int(a) + 1}, {int(b) + 1}, {int(c) + 1}}}," for a, b, c in faces]
    lines += [
        "}",
        "local color = anchor.Color",
        "local material = anchor.Material",
        "local thickness = 0.035",
        "local function renderTriangle(va, vb, vc)",
        "    local a = anchorCF:PointToWorldSpace(va)",
        "    local b = anchorCF:PointToWorldSpace(vb)",
        "    local c = anchorCF:PointToWorldSpace(vc)",
        "    local ab = b - a",
        "    local ac = c - a",
        "    local normal = ab:Cross(ac)",
        "    if normal.Magnitude < 0.0001 then return end",
        "    local edge = c - b",
        "    local edgeLength = edge.Magnitude",
        "    if edgeLength < 0.0001 then return end",
        "    local height = normal.Magnitude / edgeLength",
        "    local zAxis = edge.Unit",
        "    local yAxis = normal.Unit",
        "    local xAxis = yAxis:Cross(zAxis)",
        "    if xAxis.Magnitude < 0.0001 then return end",
        "    xAxis = xAxis.Unit",
        "    local p = Instance.new('Part')",
        "    p.Name = 'TriangleSurface'",
        "    p.Anchored = true",
        "    p.CanCollide = false",
        "    p.CastShadow = true",
        "    p.Material = material",
        "    p.Color = color",
        "    p.Size = Vector3.new(math.max(height, 0.025), thickness, edgeLength)",
        "    p.CFrame = CFrame.fromMatrix((b + c) / 2, xAxis, yAxis, zAxis)",
        "    p.Parent = model",
        "end",
        "for _, tri in ipairs(triangles) do",
        "    renderTriangle(vertices[tri[1]], vertices[tri[2]], vertices[tri[3]])",
        "end",
        "anchor.Transparency = 1",
        "anchor.CanCollide = false",
        "print('Generated mesh:', #vertices, 'vertices,', #triangles, 'triangles')",
    ]
    return "\n".join(lines) + "\n"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("840x680")
        self.minsize(780, 640)
        self.file_path = None
        self.meshes = None
        self.dark = True
        self.palette = DARK_THEME

        self.configure(bg=self.palette["bg"])
        self._setup_style(self.palette)
        self._build_ui()
        self._set_export_state(False)

    def _setup_style(self, c):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=c["bg"], foreground=c["text"], font=FONT_BODY)
        style.configure("TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["panel"])
        style.configure("Stat.TFrame", background=c["panel_alt"])

        style.configure("TLabel", background=c["bg"], foreground=c["text"], font=FONT_BODY)
        style.configure("Title.TLabel", background=c["bg"], foreground=c["text"], font=FONT_TITLE)
        style.configure("Subtitle.TLabel", background=c["bg"], foreground=c["muted"])
        style.configure("Creator.TLabel", background=c["bg"], foreground=c["accent"], font=FONT_SMALL)
        style.configure("Link.TLabel", background=c["bg"], foreground=c["link"], font=FONT_LINK)
        style.configure("CardTitle.TLabel", background=c["panel"], foreground=c["text"], font=FONT_BOLD)
        style.configure("Card.TLabel", background=c["panel"], foreground=c["text"])
        style.configure("Muted.TLabel", background=c["panel"], foreground=c["muted"], font=FONT_SMALL)
        style.configure("StatValue.TLabel", background=c["panel_alt"], foreground=c["text"], font=FONT_STAT)
        style.configure("StatCaption.TLabel", background=c["panel_alt"], foreground=c["muted"], font=FONT_SMALL)
        style.configure("Warning.TLabel", background=c["warning_bg"], foreground=c["warning"], padding=12)
        style.configure("Status.TLabel", background=c["bg"], foreground=c["success"])

        style.configure(
            "TButton",
            background=c["panel_alt"],
            foreground=c["text"],
            borderwidth=0,
            focusthickness=0,
            padding=(14, 8),
        )
        style.map(
            "TButton",
            background=[("active", c["border"]), ("disabled", c["panel"])],
            foreground=[("disabled", c["muted"])],
        )
        style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground="#FFFFFF",
            font=FONT_BOLD,
            padding=(18, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", c["accent_hover"]), ("disabled", c["panel_alt"])],
            foreground=[("disabled", c["muted"])],
        )

        field_style = {
            "fieldbackground": c["panel_alt"],
            "foreground": c["text"],
            "insertcolor": c["text"],
            "bordercolor": c["border"],
            "lightcolor": c["border"],
            "darkcolor": c["border"],
            "padding": 6,
        }
        style.configure("TEntry", **field_style)
        style.configure("TSpinbox", arrowcolor=c["text"], **field_style)

    def _build_ui(self):
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")

        top_row = ttk.Frame(header)
        top_row.pack(fill="x")
        ttk.Label(top_row, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        self.toggle_canvas = tk.Canvas(
            top_row, width=36, height=36, highlightthickness=0, bd=0, cursor="hand2"
        )
        self.toggle_canvas.pack(side="right")
        self.toggle_canvas.bind("<Button-1>", lambda e: self.toggle_theme())
        self._draw_toggle()

        ttk.Label(
            header,
            text="Convert a .glb model into a Luau script built from Parts.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(header, text=f"Created by {CREATOR}", style="Creator.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Label(
            header,
            text="This tool was designed to be used in Vortex Studio (0.8.1):",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        link = ttk.Label(header, text=VORTEX_URL, style="Link.TLabel", cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(VORTEX_URL))

        source = self._card(root, "Source model")
        top = ttk.Frame(source, style="Card.TFrame")
        top.pack(fill="x")
        self.file_label = ttk.Label(top, text="No file selected", style="Muted.TLabel")
        self.file_label.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Import GLB...", command=self.choose_file).pack(side="right")

        stats = ttk.Frame(source, style="Card.TFrame")
        stats.pack(fill="x", pady=(16, 0))
        self.stat_vars = {}
        for index, (key, caption) in enumerate(
            (("meshes", "Meshes"), ("vertices", "Vertices"), ("triangles", "Triangles"))
        ):
            box = ttk.Frame(stats, style="Stat.TFrame", padding=(16, 12))
            box.pack(side="left", fill="x", expand=True, padx=(0 if index == 0 else 10, 0))
            var = tk.StringVar(value="—")
            self.stat_vars[key] = var
            ttk.Label(box, textvariable=var, style="StatValue.TLabel").pack(anchor="w")
            ttk.Label(box, text=caption, style="StatCaption.TLabel").pack(anchor="w")

        settings = self._card(root, "Export settings")
        grid = ttk.Frame(settings, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.name_var = tk.StringVar(value="ImportedMesh")
        self.anchor_var = tk.StringVar(value="MeshAnchor")
        self.faces_var = tk.IntVar(value=DEFAULT_MAX_FACES)
        self.scale_var = tk.DoubleVar(value=1.0)

        self._field(grid, 0, 0, "Model name",
                    lambda p: ttk.Entry(p, textvariable=self.name_var))
        self._field(grid, 0, 1, "Anchor part name",
                    lambda p: ttk.Entry(p, textvariable=self.anchor_var))
        self._field(grid, 1, 0, "Max triangles",
                    lambda p: ttk.Spinbox(p, from_=100, to=15000, increment=100,
                                          textvariable=self.faces_var))
        self._field(grid, 1, 1, "Scale",
                    lambda p: ttk.Spinbox(p, from_=0.05, to=20.0, increment=0.25,
                                          textvariable=self.scale_var))

        ttk.Label(
            settings,
            text="The largest axis is normalized to 8 studs before the scale is applied.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(12, 0))

        ttk.Label(root, text=WARNING_TEXT, style="Warning.TLabel", wraplength=740).pack(
            fill="x", pady=(18, 0)
        )

        footer = ttk.Frame(root)
        footer.pack(fill="x", side="bottom", pady=(18, 0))
        self.status = tk.StringVar(value="Ready. Import a .glb file to begin.")
        ttk.Label(footer, textvariable=self.status, style="Status.TLabel", wraplength=520).pack(side="left")
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self.export_button = ttk.Button(
            footer,
            text="Generate Luau script...",
            style="Accent.TButton",
            command=self.export_lua,
        )
        self.export_button.pack(side="right", padx=(0, 10))

    def _draw_toggle(self):
        c = self.toggle_canvas
        p = self.palette
        c.delete("all")
        c.configure(bg=p["bg"])
        if self.dark:
            c.create_oval(10, 10, 26, 26, fill=p["sun"], outline="")
            for i in range(8):
                angle = math.radians(i * 45)
                x1 = 18 + 11 * math.cos(angle)
                y1 = 18 + 11 * math.sin(angle)
                x2 = 18 + 15 * math.cos(angle)
                y2 = 18 + 15 * math.sin(angle)
                c.create_line(x1, y1, x2, y2, fill=p["sun"], width=2, capstyle="round")
        else:
            c.create_oval(8, 8, 28, 28, fill=p["moon"], outline="")
            c.create_oval(15, 4, 35, 24, fill=p["bg"], outline="")

    def toggle_theme(self):
        self.dark = not self.dark
        self.palette = DARK_THEME if self.dark else LIGHT_THEME
        self.configure(bg=self.palette["bg"])
        self._setup_style(self.palette)
        self._draw_toggle()

    def _card(self, parent, title):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="x", pady=(18, 0))
        card = ttk.Frame(wrapper, style="Card.TFrame", padding=18)
        card.pack(fill="x")
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        return card

    def _field(self, parent, row, col, text, make_widget):
        cell = ttk.Frame(parent, style="Card.TFrame")
        cell.grid(row=row, column=col, sticky="ew", padx=(0, 18), pady=6)
        ttk.Label(cell, text=text, style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        make_widget(cell).pack(fill="x")

    def _set_export_state(self, enabled):
        self.export_button.state(["!disabled"] if enabled else ["disabled"])

    def choose_file(self):
        if trimesh is None:
            messagebox.showerror(
                "Missing dependency",
                "Install the dependencies first:\n\npython -m pip install trimesh pyglet",
            )
            return
        path = filedialog.askopenfilename(
            title="Select GLB model",
            filetypes=[("GLB model", "*.glb"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            meshes = load_glb(path)
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            return

        self.meshes = meshes
        self.file_path = path
        vertex_count = sum(len(m.vertices) for m in meshes)
        triangle_count = sum(len(m.faces) for m in meshes)
        self.file_label.config(text=os.path.basename(path), style="Card.TLabel")
        self.stat_vars["meshes"].set(f"{len(meshes):,}")
        self.stat_vars["vertices"].set(f"{vertex_count:,}")
        self.stat_vars["triangles"].set(f"{triangle_count:,}")
        self.status.set(f"Loaded {os.path.basename(path)}.")
        self._set_export_state(True)

    def export_lua(self):
        if not self.meshes or not self.file_path:
            messagebox.showwarning("No model", "Import a .glb file before exporting.")
            return
        try:
            max_faces = int(self.faces_var.get())
            scale = float(self.scale_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid settings", "Max triangles must be an integer and scale must be a number.")
            return
        if max_faces < 1 or scale <= 0:
            messagebox.showerror("Invalid settings", "Max triangles and scale must be greater than zero.")
            return

        object_name = self.name_var.get().strip() or "ImportedMesh"
        anchor_name = self.anchor_var.get().strip() or "MeshAnchor"

        try:
            mesh = simplify_mesh(self.meshes, max_faces)
            lua = generate_lua(mesh, object_name, anchor_name, scale)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))
            return

        default_name = os.path.splitext(os.path.basename(self.file_path))[0] + "_mesh.lua"
        path = filedialog.asksaveasfilename(
            title="Save Luau script",
            defaultextension=".lua",
            initialfile=default_name,
            filetypes=[("Luau script", "*.lua"), ("Text file", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(lua)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return

        self.status.set(
            f"Saved {os.path.basename(path)} | {len(mesh.vertices):,} vertices, "
            f"{len(mesh.faces):,} triangles."
        )
        messagebox.showinfo(
            "Export complete",
            "Script saved.\n\n"
            f"In Vortex, create a Part named '{anchor_name}' in Workspace, "
            "place the script in ServerScriptService, and run a playtest.",
        )


if __name__ == "__main__":
    if trimesh is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Install dependencies",
            "Open a terminal and run:\n\npython -m pip install trimesh pyglet",
        )
        root.destroy()
    else:
        App().mainloop()
