import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser, simpledialog
import json
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import webbrowser
from PIL import Image, ImageTk
import os

# Constants
APP_NAME = "LUL Layout Manager"
VERSION = "0.0.1"
DEFAULT_THEME = {
    'bg': '#2d2d2d',
    'fg': '#ffffff',
    'toolbar_bg': '#1e1e1e',
    'canvas_bg': '#252526',
    'highlight': '#007acc',
    'widget_outline': '#3e3e42'
}
SUPPORTED_WIDGETS = [
    'Button', 'Label', 'Entry', 'Text', 'Checkbutton',
    'Radiobutton', 'Scale', 'Listbox', 'Scrollbar',
    'Frame', 'LabelFrame', 'Combobox', 'Progressbar'
]
GRID_SIZE = 20  # Snap-to-grid size

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='layout_manager.log'
)

@dataclass
class WidgetData:
    type: str
    x: int
    y: int
    properties: dict
    id: Optional[int] = None

class DraggableWidget:
    def __init__(self, builder, canvas, widget, widget_type, x, y, properties=None):
        self.builder = builder  # Reference to the GUIBuilder for undo callbacks
        self.canvas = canvas
        self.widget = widget
        self.widget_type = widget_type
        self.x = x
        self.y = y
        self.properties = properties or {}
        self.selected = False
        
        # Record original position for undo support
        self.original_x = x
        self.original_y = y

        # Create the window on canvas. Note: canvas windows don’t directly support outlines,
        # so we manage it via our update_appearance method.
        self.id = canvas.create_window(
            x, y,
            window=widget,
            tags=("widget", f"widget_{id(widget)}"),
            anchor="nw"
        )
        
        self._add_dragging_support()
        self._add_context_menu()
        self.update_appearance()
    
    def _add_dragging_support(self):
        self.widget.bind("<ButtonPress-1>", self.on_start)
        self.widget.bind("<B1-Motion>", self.on_drag)
        self.widget.bind("<ButtonRelease-1>", self.on_release)
        self.widget.bind("<Enter>", self.on_hover)
        self.widget.bind("<Leave>", self.on_leave)
    
    def _add_context_menu(self):
        self.menu = tk.Menu(self.canvas, tearoff=0)
        self.menu.add_command(label="Properties", command=self.edit_properties)
        self.menu.add_command(label="Delete", command=self.delete)
        self.menu.add_separator()
        self.menu.add_command(label="Bring to Front", command=self.bring_to_front)
        self.menu.add_command(label="Send to Back", command=self.send_to_back)
        
        if self.widget_type in ['Frame', 'LabelFrame']:
            self.menu.add_separator()
            self.menu.add_command(label="Add Widget Inside", command=self.add_widget_inside)
        
        self.widget.bind("<Button-3>", self.show_context_menu)
    
    def update_appearance(self):
        # Note: canvas windows don’t inherently have an outline.
        # In a more robust solution, you might wrap the widget in a Frame with a border.
        if self.selected:
            self.canvas.itemconfig(self.id, width=2)
        else:
            self.canvas.itemconfig(self.id, width=1)
    
    def on_start(self, event):
        self.start_x = event.x
        self.start_y = event.y
        # Record the starting position
        self.original_x = self.x
        self.original_y = self.y
        self.select()
    
    def on_drag(self, event):
        dx = event.x - self.start_x
        dy = event.y - self.start_y
        
        # Calculate new position with snap-to-grid
        new_x = self.x + dx
        new_y = self.y + dy
        new_x = round(new_x / GRID_SIZE) * GRID_SIZE
        new_y = round(new_y / GRID_SIZE) * GRID_SIZE
        
        dx = new_x - self.x
        dy = new_y - self.y
        
        if dx != 0 or dy != 0:
            self.canvas.move(self.id, dx, dy)
            self.x = new_x
            self.y = new_y
    
    def on_release(self, event):
        self.update_appearance()
        # Push undo action if widget has moved
        if (self.x, self.y) != (self.original_x, self.original_y):
            self.builder.push_undo(('move', self, self.original_x, self.original_y))
    
    def on_hover(self, event):
        self.widget.config(cursor="hand2")
    
    def on_leave(self, event):
        self.widget.config(cursor="")
    
    def show_context_menu(self, event):
        try:
            self.select()
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
    
    def select(self):
        # Deselect all other widgets first
        for item in self.canvas.find_withtag("widget"):
            self.canvas.itemconfig(item, width=1)
        self.selected = True
        self.update_appearance()
        self.canvas.tag_raise(self.id)
    
    def deselect(self):
        self.selected = False
        self.update_appearance()
    
    def edit_properties(self):
        PropertyEditor(self.builder.root, self)
    
    def delete(self):
        self.canvas.delete(self.id)
        self.widget.destroy()
    
    def bring_to_front(self):
        self.canvas.tag_raise(self.id)
    
    def send_to_back(self):
        self.canvas.tag_lower(self.id)
    
    def add_widget_inside(self):
        if self.widget_type in ['Frame', 'LabelFrame']:
            # This method assumes the builder has a method to add widgets to a container
            self.builder.add_widget_to_container(self.widget)

class PropertyEditor(tk.Toplevel):
    def __init__(self, parent, draggable_widget):
        super().__init__(parent)
        self.title(f"Properties - {draggable_widget.widget_type}")
        self.draggable_widget = draggable_widget
        self.widget = draggable_widget.widget
        self.widget_type = draggable_widget.widget_type
        
        self.geometry("400x600")
        self.resizable(True, True)
        
        self.create_widgets()
        self.load_properties()
    
    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Property list
        self.tree = ttk.Treeview(main_frame, columns=('value',), selectmode='browse')
        self.tree.heading('#0', text='Property')
        self.tree.heading('value', text='Value')
        self.tree.column('#0', width=150)
        self.tree.column('value', width=200)
        
        vsb = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(main_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Edit area
        edit_frame = ttk.Frame(main_frame)
        edit_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        
        ttk.Label(edit_frame, text="Edit Value:").pack(side=tk.LEFT)
        self.value_entry = ttk.Entry(edit_frame)
        self.value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.update_btn = ttk.Button(edit_frame, text="Update", command=self.update_property)
        self.update_btn.pack(side=tk.LEFT)
        
        # Special buttons for colors and fonts
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        
        ttk.Button(btn_frame, text="Choose Color...", command=self.choose_color).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Choose Font...", command=self.choose_font).pack(side=tk.LEFT, padx=2)
        
        # Bind selection change
        self.tree.bind('<<TreeviewSelect>>', self.on_property_select)
    
    def load_properties(self):
        # Common properties
        properties = {
            'text': getattr(self.widget, 'cget')('text') if hasattr(self.widget, 'cget') else '',
            'background': getattr(self.widget, 'cget')('bg') if hasattr(self.widget, 'cget') else '',
            'foreground': getattr(self.widget, 'cget')('fg') if hasattr(self.widget, 'cget') else '',
            'width': getattr(self.widget, 'cget')('width') if hasattr(self.widget, 'cget') else '',
            'height': getattr(self.widget, 'cget')('height') if hasattr(self.widget, 'cget') else '',
            'x': self.draggable_widget.x,
            'y': self.draggable_widget.y
        }
        
        # Widget-specific properties
        if self.widget_type == 'Button':
            properties['command'] = ''
        elif self.widget_type == 'Entry':
            properties['show'] = getattr(self.widget, 'cget')('show') if hasattr(self.widget, 'cget') else ''
        elif self.widget_type == 'Text':
            properties['wrap'] = getattr(self.widget, 'cget')('wrap') if hasattr(self.widget, 'cget') else ''
        
        for prop, value in properties.items():
            self.tree.insert('', 'end', text=prop, values=(value,))
    
    def on_property_select(self, event):
        selected = self.tree.selection()
        if selected:
            prop = self.tree.item(selected[0], 'text')
            value = self.tree.item(selected[0], 'values')[0]
            self.value_entry.delete(0, tk.END)
            self.value_entry.insert(0, value)
    
    def update_property(self):
        selected = self.tree.selection()
        if not selected:
            return
            
        prop = self.tree.item(selected[0], 'text')
        new_value = self.value_entry.get()
        
        try:
            # Handle position separately using the draggable widget's canvas
            if prop == 'x':
                dx = int(new_value) - self.draggable_widget.x
                self.draggable_widget.canvas.move(self.draggable_widget.id, dx, 0)
                self.draggable_widget.x = int(new_value)
            elif prop == 'y':
                dy = int(new_value) - self.draggable_widget.y
                self.draggable_widget.canvas.move(self.draggable_widget.id, 0, dy)
                self.draggable_widget.y = int(new_value)
            else:
                # Update widget property if it exists (uses config method)
                self.widget.config({prop: new_value})
            
            # Update tree view with new value
            self.tree.item(selected[0], values=(new_value,))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update property: {str(e)}")
    
    def choose_color(self):
        selected = self.tree.selection()
        if not selected:
            return
            
        prop = self.tree.item(selected[0], 'text')
        if prop not in ['background', 'foreground']:
            messagebox.showwarning("Warning", "Please select a color property first")
            return
            
        color = colorchooser.askcolor(title=f"Choose {prop} color")
        if color[1]:
            self.value_entry.delete(0, tk.END)
            self.value_entry.insert(0, color[1])
            self.update_property()
    
    def choose_font(self):
        selected = self.tree.selection()
        if not selected:
            return
            
        prop = self.tree.item(selected[0], 'text')
        if prop != 'font':
            messagebox.showwarning("Warning", "Please select the font property first")
            return
            
        font = simpledialog.askstring("Font", "Enter font (e.g., Arial 12 bold):")
        if font:
            self.value_entry.delete(0, tk.END)
            self.value_entry.insert(0, font)
            self.update_property()

class GUIBuilder:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)
        
        # Application state
        self.active_widget = None
        self.widgets = []
        self.current_file = None
        self.undo_stack = []
        self.redo_stack = []
        
        # Configure styles
        self.setup_styles()
        
        # Build UI
        self.create_ui()
        
        # Bind keyboard shortcuts
        self.setup_shortcuts()
        
        # Create grid
        self.show_grid()
        
        # Status bar
        self.setup_statusbar()
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure('.', background=DEFAULT_THEME['bg'], foreground=DEFAULT_THEME['fg'])
        style.configure('TFrame', background=DEFAULT_THEME['bg'])
        style.configure('TButton', background=DEFAULT_THEME['toolbar_bg'])
        style.configure('TLabel', background=DEFAULT_THEME['bg'])
        style.configure('TEntry', fieldbackground='#333333')
        style.configure('Treeview', background='#333333', fieldbackground='#333333', foreground='white')
        
        # Custom styles
        style.configure('Toolbutton.TButton', padding=5)
        style.configure('Status.TLabel', background=DEFAULT_THEME['toolbar_bg'], relief=tk.SUNKEN)
    
    def create_ui(self):
        # Main layout
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
        
        # Left sidebar - Toolbox
        self.create_toolbox()
        
        # Right pane - Canvas and properties
        self.create_canvas_area()
        
        # Menu bar
        self.create_menubar()
    
    def create_menubar(self):
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self.open_project, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_project, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_project_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Export Python...", command=self.export_python)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", command=self.cut, accelerator="Ctrl+X")
        edit_menu.add_command(label="Copy", command=self.copy, accelerator="Ctrl+C")
        edit_menu.add_command(label="Paste", command=self.paste, accelerator="Ctrl+V")
        edit_menu.add_command(label="Delete", command=self.delete_selected, accelerator="Del")
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu (fixed syntax)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Show Grid", command=self.toggle_grid)
        view_menu.add_separator()
        view_menu.add_command(label="Zoom In", command=lambda: self.zoom(1.1))
        view_menu.add_command(label="Zoom Out", command=lambda: self.zoom(0.9))
        view_menu.add_command(label="Reset Zoom", command=lambda: self.zoom(1.0))
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Documentation", command=self.show_docs)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def create_toolbox(self):
        self.toolbox = ttk.Frame(self.main_paned, width=200, style='TFrame')
        self.main_paned.add(self.toolbox, weight=0)
        
        # Toolbox header
        header = ttk.Label(self.toolbox, text="Widgets", style='Heading.TLabel')
        header.pack(pady=(10, 5), padx=5, fill=tk.X)
        
        # Search box
        search_frame = ttk.Frame(self.toolbox)
        search_frame.pack(padx=5, pady=5, fill=tk.X)
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind('<KeyRelease>', self.filter_widgets)
        
        # Widget buttons container
        self.widget_buttons_frame = ttk.Frame(self.toolbox)
        self.widget_buttons_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add widget buttons
        self.create_widget_buttons()
        
        # Properties panel at the bottom
        self.create_properties_panel()
    
    def create_widget_buttons(self):
        for widget_type in SUPPORTED_WIDGETS:
            btn = ttk.Button(
                self.widget_buttons_frame,
                text=widget_type,
                command=lambda wt=widget_type: self.select_widget(wt),
                style='Toolbutton.TButton'
            )
            btn.pack(fill=tk.X, pady=2)
    
    def filter_widgets(self, event=None):
        search_term = self.search_var.get().lower()
        
        for child in self.widget_buttons_frame.winfo_children():
            widget_text = child['text'].lower()
            if search_term in widget_text:
                child.pack(fill=tk.X, pady=2)
            else:
                child.pack_forget()
    
    def create_properties_panel(self):
        properties_frame = ttk.LabelFrame(self.toolbox, text="Properties", padding=5)
        properties_frame.pack(fill=tk.X, padx=5, pady=5)
        # Placeholder – properties will populate when a widget is selected
    
    def create_canvas_area(self):
        canvas_container = ttk.Frame(self.main_paned)
        self.main_paned.add(canvas_container, weight=1)
        
        # Canvas with scrollbars
        self.canvas = tk.Canvas(
            canvas_container,
            bg=DEFAULT_THEME['canvas_bg'],
            highlightthickness=0
        )
        
        self.h_scroll = ttk.Scrollbar(canvas_container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        # Grid layout
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.v_scroll.grid(row=0, column=1, sticky='ns')
        self.h_scroll.grid(row=1, column=0, sticky='ew')
        
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)
        
        # Bind canvas events for panning when no widget is actively placed
        self.canvas.bind("<Button-1>", self.canvas_click)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        
        # Initialize zoom
        self.zoom_level = 1.0
    
    def show_grid(self):
        self.grid_visible = True
        self.draw_grid()
    
    def hide_grid(self):
        self.grid_visible = False
        self.canvas.delete("grid_line")
    
    def toggle_grid(self):
        if self.grid_visible:
            self.hide_grid()
        else:
            self.show_grid()
    
    def draw_grid(self):
        if not self.grid_visible:
            return
            
        self.canvas.delete("grid_line")
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        for x in range(0, width, GRID_SIZE):
            self.canvas.create_line(
                x, 0, x, height,
                tags=("grid_line",),
                fill="#3e3e42",
                dash=(1, 2)
            )
        
        for y in range(0, height, GRID_SIZE):
            self.canvas.create_line(
                0, y, width, y,
                tags=("grid_line",),
                fill="#3e3e42",
                dash=(1, 2)
            )
    
    def on_canvas_resize(self, event):
        if self.grid_visible:
            self.draw_grid()
    
    def setup_statusbar(self):
        self.statusbar = ttk.Frame(self.root, height=20, style='TFrame')
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(
            self.statusbar,
            text="Ready",
            style='Status.TLabel'
        )
        self.status_label.pack(fill=tk.X, padx=1, pady=1)
    
    def setup_shortcuts(self):
        self.root.bind("<Control-n>", lambda e: self.new_project())
        self.root.bind("<Control-o>", lambda e: self.open_project())
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-Shift-S>", lambda e: self.save_project_as())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Delete>", lambda e: self.delete_selected())
    
    def select_widget(self, widget_type):
        self.active_widget = widget_type
        self.status_label.config(text=f"Selected: {widget_type} - Click on canvas to place")
    
    def canvas_click(self, event):
        if self.active_widget:
            self.place_widget(event.x, event.y)
        else:
            # Check if a widget was clicked to select it
            clicked = self.canvas.find_withtag("current")
            if clicked and "widget" in self.canvas.gettags(clicked[0]):
                for dw in self.widgets:
                    if dw.id == clicked[0]:
                        dw.select()
                        break
    
    def place_widget(self, x, y):
        if not self.active_widget:
            return
            
        # Snap to grid
        x = round(x / GRID_SIZE) * GRID_SIZE
        y = round(y / GRID_SIZE) * GRID_SIZE
        
        widget = None
        widget_type = self.active_widget
        
        try:
            if widget_type == "Button":
                widget = ttk.Button(self.canvas, text="Button")
            elif widget_type == "Label":
                widget = ttk.Label(self.canvas, text="Label")
            elif widget_type == "Entry":
                widget = ttk.Entry(self.canvas)
            elif widget_type == "Text":
                widget = tk.Text(self.canvas, width=30, height=5)
            elif widget_type == "Checkbutton":
                widget = ttk.Checkbutton(self.canvas, text="Checkbutton")
            elif widget_type == "Radiobutton":
                widget = ttk.Radiobutton(self.canvas, text="Radiobutton")
            elif widget_type == "Scale":
                widget = ttk.Scale(self.canvas, from_=0, to=100)
            elif widget_type == "Listbox":
                widget = tk.Listbox(self.canvas, height=4)
                for item in ["Item 1", "Item 2", "Item 3"]:
                    widget.insert(tk.END, item)
            elif widget_type == "Scrollbar":
                widget = ttk.Scrollbar(self.canvas)
            elif widget_type == "Frame":
                widget = ttk.Frame(self.canvas, width=200, height=200, relief=tk.RIDGE)
            elif widget_type == "LabelFrame":
                widget = ttk.LabelFrame(self.canvas, text="LabelFrame", width=200, height=200)
            elif widget_type == "Combobox":
                widget = ttk.Combobox(self.canvas, values=["Option 1", "Option 2", "Option 3"])
            elif widget_type == "Progressbar":
                widget = ttk.Progressbar(self.canvas, length=200, mode='determinate')
                widget.step(50)
            
            if widget:
                # Pass self (the builder) into DraggableWidget for undo support
                dw = DraggableWidget(self, self.canvas, widget, widget_type, x, y)
                self.widgets.append(dw)
                
                # Push creation action to undo stack
                self.push_undo(('create', dw))
                
                # Reset selection
                self.active_widget = None
                self.status_label.config(text="Ready")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create widget: {str(e)}")
            logging.error(f"Widget creation error: {str(e)}")
    
    def canvas_drag(self, event):
        # Handle canvas panning when no widget is being placed
        if not self.active_widget:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
    
    def zoom(self, factor):
        self.zoom_level *= factor
        self.canvas.scale("all", 0, 0, factor, factor)
        self.status_label.config(text=f"Zoom: {int(self.zoom_level * 100)}%")
    
    def new_project(self):
        if self.widgets and not messagebox.askyesno("New Project", "Current project will be lost. Continue?"):
            return
        
        self.clear_canvas()
        self.current_file = None
        self.status_label.config(text="New project created")
    
    def clear_canvas(self):
        for dw in self.widgets:
            self.canvas.delete(dw.id)
            dw.widget.destroy()
        self.widgets = []
        self.undo_stack = []
        self.redo_stack = []
    
    def open_project(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Layout Files", "*.json"), ("All Files", "*.*")],
            title="Open Layout File"
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                self.clear_canvas()
                self.current_file = file_path
                
                for widget_data in data['widgets']:
                    self.load_widget(widget_data)
                
                self.status_label.config(text=f"Opened: {file_path}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {str(e)}")
                logging.error(f"File open error: {str(e)}")
    
    def load_widget(self, widget_data):
        widget_type = widget_data['type']
        x = widget_data['x']
        y = widget_data['y']
        properties = widget_data.get('properties', {})
        
        self.active_widget = widget_type
        self.place_widget(x, y)
        
        # Apply properties to the last created widget
        if self.widgets:
            dw = self.widgets[-1]
            for prop, value in properties.items():
                try:
                    dw.widget.config({prop: value})
                except Exception:
                    pass  # Skip properties that don't apply
    
    def save_project(self):
        if self.current_file:
            self._save_to_file(self.current_file)
        else:
            self.save_project_as()
    
    def save_project_as(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Layout Files", "*.json"), ("All Files", "*.*")],
            title="Save Layout As"
        )
        
        if file_path:
            self._save_to_file(file_path)
            self.current_file = file_path
    
    def _save_to_file(self, file_path):
        try:
            data = {
                'version': VERSION,
                'widgets': []
            }
            
            for dw in self.widgets:
                widget_data = {
                    'type': dw.widget_type,
                    'x': dw.x,
                    'y': dw.y,
                    'properties': {
                        'text': dw.widget.cget('text') if 'text' in dw.widget.keys() else '',
                        'width': dw.widget.cget('width') if 'width' in dw.widget.keys() else '',
                        'height': dw.widget.cget('height') if 'height' in dw.widget.keys() else '',
                        'background': dw.widget.cget('bg') if 'bg' in dw.widget.keys() else '',
                        'foreground': dw.widget.cget('fg') if 'fg' in dw.widget.keys() else ''
                    }
                }
                data['widgets'].append(widget_data)
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.status_label.config(text=f"Saved: {file_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {str(e)}")
            logging.error(f"File save error: {str(e)}")
    
    def export_python(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python Files", "*.py"), ("All Files", "*.*")],
            title="Export Python Code"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(self.generate_python_code())
                
                self.status_label.config(text=f"Exported: {file_path}")
                messagebox.showinfo("Export Successful", "Python code exported successfully!")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export code: {str(e)}")
                logging.error(f"Export error: {str(e)}")
    
    def generate_python_code(self):
        code = [
            "import tkinter as tk",
            "from tkinter import ttk",
            "",
            "def create_gui():",
            "    root = tk.Tk()",
            "    root.title('Generated GUI')",
            ""
        ]
        
        # Create widgets
        for i, dw in enumerate(self.widgets):
            var_name = f"widget_{i}"
            
            if dw.widget_type == "Button":
                text = dw.widget.cget('text') if 'text' in dw.widget.keys() else 'Button'
                code.append(f"    {var_name} = ttk.Button(root, text='{text}')")
            elif dw.widget_type == "Label":
                text = dw.widget.cget('text') if 'text' in dw.widget.keys() else 'Label'
                code.append(f"    {var_name} = ttk.Label(root, text='{text}')")
            elif dw.widget_type == "Entry":
                code.append(f"    {var_name} = ttk.Entry(root)")
            # Add other widget types as needed...
            
            code.append(f"    {var_name}.place(x={dw.x}, y={dw.y})")
            code.append("")
        
        code.append("    root.mainloop()")
        code.append("")
        code.append("if __name__ == '__main__':")
        code.append("    create_gui()")
        
        return "\n".join(code)
    
    def delete_selected(self):
        selected = [dw for dw in self.widgets if dw.selected]
        if not selected:
            return
            
        for dw in selected:
            self.push_undo(('delete', dw))
            self.canvas.delete(dw.id)
            dw.widget.destroy()
            self.widgets.remove(dw)
    
    def push_undo(self, action):
        self.undo_stack.append(action)
        self.redo_stack = []  # Clear redo stack when a new action is performed
    
    def undo(self):
        if not self.undo_stack:
            return
            
        action = self.undo_stack.pop()
        self.redo_stack.append(action)
        
        if action[0] == 'create':
            _, dw = action
            self.canvas.delete(dw.id)
            dw.widget.destroy()
            self.widgets.remove(dw)
        elif action[0] == 'delete':
            _, dw = action
            self.widgets.append(dw)
            dw.id = self.canvas.create_window(dw.x, dw.y, window=dw.widget)
        elif action[0] == 'move':
            _, dw, old_x, old_y = action
            dx = old_x - dw.x
            dy = old_y - dw.y
            self.canvas.move(dw.id, dx, dy)
            dw.x, dw.y = old_x, old_y
    
    def redo(self):
        if not self.redo_stack:
            return
            
        action = self.redo_stack.pop()
        self.undo_stack.append(action)
        
        if action[0] == 'create':
            _, dw = action
            self.widgets.append(dw)
            dw.id = self.canvas.create_window(dw.x, dw.y, window=dw.widget)
        elif action[0] == 'delete':
            _, dw = action
            self.canvas.delete(dw.id)
            dw.widget.destroy()
            self.widgets.remove(dw)
        elif action[0] == 'move':
            _, dw, old_x, old_y = action
            dx = dw.x - old_x
            dy = dw.y - old_y
            self.canvas.move(dw.id, dx, dy)
            dw.x, dw.y = old_x, old_y
    
    def cut(self):
        self.copy()
        self.delete_selected()
    
    def copy(self):
        selected = [dw for dw in self.widgets if dw.selected]
        if not selected:
            return
            
        # TODO: Implement copy-to-clipboard functionality
        messagebox.showinfo("Info", "Copy functionality will be implemented")
    
    def paste(self):
        # TODO: Implement paste-from-clipboard functionality
        messagebox.showinfo("Info", "Paste functionality will be implemented")
    
    def show_docs(self):
        webbrowser.open("LinkToGitHub")
    
    def show_about(self):
        about_window = tk.Toplevel(self.root)
        about_window.title("About")
        about_window.geometry("400x300")
        about_window.resizable(False, False)
        
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            img = img.resize((100, 100), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            logo_label = tk.Label(about_window, image=photo)
            logo_label.image = photo
            logo_label.pack(pady=10)
        
        tk.Label(about_window, text=f"{APP_NAME} v{VERSION}").pack()
        tk.Label(about_window, text="\nA professional GUI layout manager\nfor Tkinter applications\nBy:Auxk0rd").pack()
        #tk.Label(about_window, text="\n© 2025  CompanyName").pack() TODO:Use this in future
        
        close_btn = ttk.Button(about_window, text="Close", command=about_window.destroy)
        close_btn.pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = GUIBuilder(root)
    root.mainloop()
