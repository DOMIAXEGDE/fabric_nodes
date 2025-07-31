import pygame
import json
import os
import importlib
import importlib.util
import sys
import subprocess
import base64
import io
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, colorchooser
from PIL import Image
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any, Union

pygame.init()

# Constants
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SIDEBAR_WIDTH = 280
MAIN_WIDTH = SCREEN_WIDTH - SIDEBAR_WIDTH

# Colors
PRIMARY = (75, 83, 32)  # Army Green
SECONDARY = (189, 183, 107)  # Dark Khaki
ACCENT = (108, 117, 125)  # Slate Gray
BG = (245, 245, 220)  # Beige
SURFACE = (255, 255, 255)  # White
TEXT = (51, 51, 51)  # Dark Gray
CODE_BG = (247, 247, 240)  # Light Code Background
CODE_NUM = (144, 144, 144)  # Line Number Gray
GRID_COLOR = (204, 204, 204)  # Grid lines
BUTTON_HOVER = (219, 213, 137)  # Lighter version of SECONDARY

# Fonts
pygame.font.init()
FONT_BASE = pygame.font.SysFont("Arial", 14)
FONT_HEADER = pygame.font.SysFont("Arial", 20, bold=True)
FONT_MONO = pygame.font.SysFont("Courier New", 12)
FONT_MONO_BOLD = pygame.font.SysFont("Courier New", 14, bold=True)

def wrap_text(text: str, font: pygame.font.Font, max_px: int) -> list[str]:
    """Return a list of substrings that each fit inside max_px."""
    words = text.expandtabs(4).split(" ")
    lines, buf = [], ""
    for w in words:
        test = f"{buf} {w}".strip()
        if font.size(test)[0] <= max_px:
            buf = test
        else:
            if buf:
                lines.append(buf)
            buf = w
    if buf:
        lines.append(buf)
    return lines


@dataclass
class Layer:
    size: int
    nodes: List[int] = field(default_factory=list)


@dataclass
class Matrix:
    quadtree_size: int
    max_depth: int
    layers: List[Layer] = field(default_factory=list)
    payload_pool: Dict[str, Any] = field(default_factory=dict)
    version: int = 1


class Button:
    def __init__(self, x, y, width, height, text, action=None, font=FONT_BASE):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.action = action
        self.font = font
        self.hovered = False
        self.pressed = False

    def draw(self, surface):
        if self.pressed:
            color = SECONDARY
        else:
            color = BUTTON_HOVER if self.hovered else PRIMARY

        pygame.draw.rect(surface, color, self.rect, border_radius=4)

        text_surf = self.font.render(self.text, True, SURFACE)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def check_hover(self, pos):
        self.hovered = self.rect.collidepoint(pos)
        return self.hovered

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return False

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.pressed and self.rect.collidepoint(event.pos):
                self.pressed = False
                if self.action:
                    return self.action()
                return True
            self.pressed = False

        return False


class DropDown:
    def __init__(self, x, y, width, height, options=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.options = options or []
        self.selected = ""
        self.open = False
        self.hovered_index = -1
        self.hovered = False
        
    def draw(self, surface):
        box_color = BUTTON_HOVER if self.hovered else SURFACE
        pygame.draw.rect(surface, box_color, self.rect, border_radius=4)
        pygame.draw.rect(surface, ACCENT, self.rect, width=1, border_radius=4)
        
        # Draw selected option
        text_surf = FONT_BASE.render(self.selected or "Select...", True, TEXT)
        text_rect = text_surf.get_rect(midleft=(self.rect.x + 10, self.rect.centery))
        surface.blit(text_surf, text_rect)
        
        # Draw dropdown arrow
        arrow_points = [
            (self.rect.right - 15, self.rect.centery - 3),
            (self.rect.right - 10, self.rect.centery + 3),
            (self.rect.right - 5, self.rect.centery - 3)
        ]
        pygame.draw.polygon(surface, ACCENT, arrow_points)
        
        # Draw dropdown options if open
        if self.open:
            option_height = 25
            dropdown_rect = pygame.Rect(
                self.rect.x,
                self.rect.bottom,
                self.rect.width,
                option_height * len(self.options)
            )
            pygame.draw.rect(surface, SURFACE, dropdown_rect)
            pygame.draw.rect(surface, ACCENT, dropdown_rect, width=1)
            
            for i, option in enumerate(self.options):
                option_rect = pygame.Rect(
                    self.rect.x,
                    self.rect.bottom + i * option_height,
                    self.rect.width,
                    option_height
                )
                
                # Highlight hovered option
                if i == self.hovered_index:
                    pygame.draw.rect(surface, BG, option_rect)
                
                # Draw option text
                text_surf = FONT_BASE.render(option, True, TEXT)
                text_rect = text_surf.get_rect(midleft=(option_rect.x + 10, option_rect.centery))
                surface.blit(text_surf, text_rect)
    
    def check_hover(self, pos):
        if self.rect.collidepoint(pos):
            self.hovered = True
            return True
        else:
            self.hovered = False

        if self.open:
            option_height = 25
            for i, _ in enumerate(self.options):
                option_rect = pygame.Rect(
                    self.rect.x,
                    self.rect.bottom + i * option_height,
                    self.rect.width,
                    option_height
                )
                if option_rect.collidepoint(pos):
                    # Skip separators
                    if self.options[i].startswith("---"):
                        self.hovered_index = -1
                        return True
                    self.hovered_index = i
                    return True

            self.hovered_index = -1

        return False
    
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return True
            
            if self.open:
                option_height = 25
                for i, option in enumerate(self.options):
                    option_rect = pygame.Rect(
                        self.rect.x,
                        self.rect.bottom + i * option_height,
                        self.rect.width,
                        option_height
                    )
                    if option_rect.collidepoint(event.pos):
                        if option.startswith("---"):
                            self.open = False
                            return False
                        self.selected = option
                        self.open = False
                        return option
                
                # Click outside the dropdown closes it
                self.open = False
        
        return False


class Slider:
    def __init__(self, x, y, width, height, min_val, max_val, value, label=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.handle_radius = 8
        self.min = min_val
        self.max = max_val
        self.value = value
        self.dragging = False
        self.hovered = False
        self.label = label
        
    def draw(self, surface):
        # Draw track
        track_rect = pygame.Rect(
            self.rect.x,
            self.rect.centery - 2,
            self.rect.width,
            4
        )
        pygame.draw.rect(surface, ACCENT, track_rect, border_radius=2)
        
        # Calculate handle position
        handle_x = self.rect.x + int((self.value - self.min) / (self.max - self.min) * self.rect.width)
        handle_pos = (handle_x, self.rect.centery)

        radius = self.handle_radius + 2 if (self.hovered or self.dragging) else self.handle_radius
        color = SECONDARY if (self.hovered or self.dragging) else PRIMARY
        pygame.draw.circle(surface, color, handle_pos, radius)
        
        # Draw label and value
        if self.label:
            label_text = f"{self.label}: {self.value}"
            text_surf = FONT_BASE.render(label_text, True, TEXT)
            text_rect = text_surf.get_rect(bottomleft=(self.rect.x, self.rect.y - 5))
            surface.blit(text_surf, text_rect)
    
    def check_hover(self, pos):
        # Check if mouse is over handle
        handle_x = self.rect.x + int((self.value - self.min) / (self.max - self.min) * self.rect.width)
        handle_rect = pygame.Rect(
            handle_x - self.handle_radius,
            self.rect.centery - self.handle_radius,
            self.handle_radius * 2,
            self.handle_radius * 2
        )
        self.hovered = handle_rect.collidepoint(pos)
        return self.hovered
    
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.check_hover(event.pos):
                self.dragging = True
                return False

        elif event.type == pygame.MOUSEBUTTONUP:
            if self.dragging:
                self.dragging = False
                return False

        elif event.type == pygame.MOUSEMOTION:
            self.check_hover(event.pos)
            if self.dragging:
                # Update value based on mouse position
                relative_x = max(0, min(event.pos[0] - self.rect.x, self.rect.width))
                self.value = self.min + int((relative_x / self.rect.width) * (self.max - self.min))
                return self.value
        
        return False


class TextInput:
    def __init__(self, x, y, width, height, default_text="", label=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = default_text
        self.active = False
        self.cursor_pos = len(default_text)
        self.cursor_visible = True
        self.label = label
        
    def draw(self, surface):
        # Draw box
        color = PRIMARY if self.active else ACCENT
        pygame.draw.rect(surface, SURFACE, self.rect, border_radius=4)
        pygame.draw.rect(surface, color, self.rect, width=1, border_radius=4)
        
        # Draw text
        text_surf = FONT_BASE.render(self.text, True, TEXT)
        text_rect = text_surf.get_rect(midleft=(self.rect.x + 10, self.rect.centery))
        surface.blit(text_surf, text_rect)

        if self.active:
            # Simple blinking cursor based on time
            self.cursor_visible = (pygame.time.get_ticks() // 500) % 2 == 0
            if self.cursor_visible:
                cursor_x = text_rect.right + 1
                top = self.rect.y + 5
                bottom = self.rect.bottom - 5
                pygame.draw.line(surface, TEXT, (cursor_x, top), (cursor_x, bottom))
        
        # Draw label
        if self.label:
            label_surf = FONT_BASE.render(self.label, True, TEXT)
            label_rect = label_surf.get_rect(bottomleft=(self.rect.x, self.rect.y - 5))
            surface.blit(label_surf, label_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
                self.cursor_pos = len(self.text)
            else:
                self.active = False
            return self.active

        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                self.active = False
                return self.text
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                self.cursor_pos = max(0, self.cursor_pos - 1)
            else:
                self.text += event.unicode
                self.cursor_pos += len(event.unicode)
            return False

        return False


class ContextMenu:
    def __init__(self, x, y, width, height, options=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.options = options or []
        self.visible = True
        self.hovered_index = -1
        
    def draw(self, surface):
        if not self.visible:
            return
        
        # Draw background
        pygame.draw.rect(surface, SURFACE, self.rect, border_radius=4)
        pygame.draw.rect(surface, ACCENT, self.rect, width=1, border_radius=4)
        
        # Draw options
        option_height = 30
        for i, (text, _) in enumerate(self.options):
            option_rect = pygame.Rect(
                self.rect.x,
                self.rect.y + i * option_height,
                self.rect.width,
                option_height
            )
            
            # Highlight hovered option
            if i == self.hovered_index:
                pygame.draw.rect(surface, BG, option_rect)
            
            # Draw separator line for certain options
            if text.startswith("---"):
                pygame.draw.line(
                    surface,
                    ACCENT,
                    (self.rect.x + 5, option_rect.centery),
                    (self.rect.right - 5, option_rect.centery),
                    1
                )
                continue
            
            # Draw option text
            text_surf = FONT_BASE.render(text, True, TEXT)
            text_rect = text_surf.get_rect(midleft=(option_rect.x + 10, option_rect.centery))
            surface.blit(text_surf, text_rect)
    
    def check_hover(self, pos):
        if not self.visible or not self.rect.collidepoint(pos):
            self.hovered_index = -1
            return False
        
        # Find hovered option
        option_height = 30
        for i, _ in enumerate(self.options):
            option_rect = pygame.Rect(
                self.rect.x,
                self.rect.y + i * option_height,
                self.rect.width,
                option_height
            )
            if option_rect.collidepoint(pos):
                if self.options[i][0:3] == "---":
                    self.hovered_index = -1
                    return True
                self.hovered_index = i
                return True
        
        self.hovered_index = -1
        return True
    
    def handle_event(self, event):
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            option_height = 30
            for i, (text, action) in enumerate(self.options):
                option_rect = pygame.Rect(
                    self.rect.x,
                    self.rect.y + i * option_height,
                    self.rect.width,
                    option_height
                )
                if option_rect.collidepoint(event.pos):
                    if text.startswith("---"):
                        return False
                    return action
        
        return False


class Modal:
    def __init__(self, width, height, title):
        self.rect = pygame.Rect(
            (SCREEN_WIDTH - width) // 2,
            (SCREEN_HEIGHT - height) // 2,
            width,
            height
        )
        self.title = title
        self.visible = False
        self.elements = []
        self.result = None
        
    def add_element(self, element):
        self.elements.append(element)
    
    def draw(self, surface):
        if not self.visible:
            return
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        surface.blit(overlay, (0, 0))
        
        # Draw modal background
        pygame.draw.rect(surface, SURFACE, self.rect, border_radius=4)
        pygame.draw.rect(surface, ACCENT, self.rect, width=1, border_radius=4)
        
        # Draw title
        title_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, 40)
        pygame.draw.rect(surface, PRIMARY, title_rect, border_top_left_radius=4, border_top_right_radius=4)
        
        title_surf = FONT_HEADER.render(self.title, True, SURFACE)
        title_rect = title_surf.get_rect(center=(self.rect.centerx, self.rect.y + 20))
        surface.blit(title_surf, title_rect)
        
        # Draw elements
        for element in self.elements:
            element.draw(surface)
    
    def handle_event(self, event):
        if not self.visible:
            return False
        
        # Close modal if clicking outside
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                self.visible = False
                return True
        
        # Handle events for elements
        for element in self.elements:
            result = element.handle_event(event)
            if result:
                self.result = result
                return True
        
        return False


class CodeExecutor:
    """Handles execution of code in different languages"""
    
    def __init__(self):
        self.extension_map = {
            "python": ".py",
            "javascript": ".js",
            "c": ".c",
            "cpp": ".cpp",
            "java": ".java",
            "html": ".html",
        }
        
        self.executor_map = {
            "python": self.execute_python,
        }
        
        # Ensure tmp directory exists
        self.tmp_dir = os.path.join(tempfile.gettempdir(), "quadtree_code")
        os.makedirs(self.tmp_dir, exist_ok=True)
    
    def execute(self, code: str, language: str) -> Tuple[bool, str]:
        """Execute code in the given language"""
        executor = self.executor_map.get(language.lower())
        if executor:
            return executor(code)
        else:
            return False, f"No executor available for {language}. Would you like to create one?"
    
    def execute_python(self, code: str) -> Tuple[bool, str]:
        """Execute Python code"""
        # Save code to temporary file
        temp_file = os.path.join(self.tmp_dir, f"temp_{hash(code)}.py")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(code)
        
        try:
            # Execute in subprocess to capture output and isolate errors
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout
            )
            
            # Clean up temp file
            try:
                os.remove(temp_file)
            except:
                pass
                
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, f"Error:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "Execution timed out (5s limit)"
        except Exception as e:
            return False, f"Execution error: {str(e)}"


class QuadtreeMatrix:
    """Main class for quadtree matrix operations"""
    
    def __init__(self):
        self.contexts = {}
        self.current_ctx = ""
        self.active_cell = None
        self.code_executor = CodeExecutor()
        
    def create_empty_matrix(self, size: int, max_depth: int) -> Matrix:
        """Create a new empty matrix with the given size and depth"""
        layers = []
        for d in range(max_depth + 1):
            layer_size = 1 << d
            nodes = [0] * (layer_size ** 2)
            layers.append(Layer(size=layer_size, nodes=nodes))
        
        return Matrix(
            quadtree_size=size,
            max_depth=max_depth,
            layers=layers,
            payload_pool={}
        )
    
    def create_new_context(self, id: str, size: int, max_depth: int) -> Matrix:
        """Create a new named context"""
        self.contexts[id] = self.create_empty_matrix(size, max_depth)
        return self.contexts[id]
    
    def get_context_list(self) -> List[str]:
        """Get list of all context IDs"""
        return list(self.contexts.keys())
    
    def load_json(self, filepath: str) -> Optional[str]:
        """Load matrix from JSON file and return the assigned context ID"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Basic validation
            if not all(key in data for key in ['quadtree_size', 'max_depth', 'layers']):
                raise ValueError("Invalid matrix format")
            
            # Convert to our data structures
            matrix = Matrix(
                quadtree_size=data['quadtree_size'],
                max_depth=data['max_depth'],
                version=data.get('version', 1),
                layers=[],
                payload_pool=data.get('payload_pool', {})
            )
            
            # Process layers
            for layer_data in data['layers']:
                layer = Layer(
                    size=layer_data['size'],
                    nodes=layer_data['nodes']
                )
                matrix.layers.append(layer)
            
            # Create context ID from filename
            ctx_id = os.path.basename(filepath).replace('.json', '')
            if ctx_id in self.contexts:
                base_id = ctx_id
                counter = 1
                while ctx_id in self.contexts:
                    ctx_id = f"{base_id}_{counter}"
                    counter += 1
            
            self.contexts[ctx_id] = matrix
            return ctx_id
            
        except Exception as e:
            print(f"Error loading JSON: {e}")
            return None
    
    def save_json(self, ctx_id: str, filepath: str) -> bool:
        """Save matrix to JSON file"""
        if ctx_id not in self.contexts:
            return False
        
        matrix = self.contexts[ctx_id]
        data = {
            'version': matrix.version,
            'quadtree_size': matrix.quadtree_size,
            'max_depth': matrix.max_depth,
            'layers': [],
            'payload_pool': matrix.payload_pool
        }
        
        # Convert layers to serializable format
        for layer in matrix.layers:
            data['layers'].append({
                'size': layer.size,
                'nodes': layer.nodes
            })
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving JSON: {e}")
            return False


class CodeEditorModal:
    def __init__(self, screen_width, screen_height):
        self.width = int(screen_width * 0.7)
        self.height = int(screen_height * 0.7)
        self.rect = pygame.Rect(
            (screen_width - self.width) // 2,
            (screen_height - self.height) // 2,
            self.width,
            self.height
        )
        
        self.visible = False
        self.code = ""
        self.language = "python"
        self.cell = None
        self.cursor_pos = 0
        self.scroll_y = 0

        # --- HORIZONTAL SCROLLING ---
        self.scroll_x = 0

        # --- TEXT SELECTION ---
        self.selection_start = 0
        self.selecting = False

        # --- CURSOR BLINKING ---
        self.cursor_timer = 0
        self.cursor_visible = True
        self.clock = None # Will be passed in handle_event
        
        # Create buttons
        button_width = 100
        button_height = 30
        margin = 10
        
        self.save_button = Button(
            self.rect.right - button_width - margin,
            self.rect.bottom - button_height - margin,
            button_width,
            button_height,
            "Save"
        )
        
        self.execute_button = Button(
            self.rect.right - button_width * 2 - margin * 2,
            self.rect.bottom - button_height - margin,
            button_width,
            button_height,
            "Execute"
        )
        
        self.cancel_button = Button(
            self.rect.right - button_width * 3 - margin * 3,
            self.rect.bottom - button_height - margin,
            button_width,
            button_height,
            "Cancel"
        )
        
        # Language input
        self.language_label = "Language:"
        self.language_input = TextInput(
            self.rect.x + 100,
            self.rect.bottom - button_height - margin,
            150,
            button_height,
            "python"
        )
    
    def show(self, code="", language="python", cell=None):
        self.visible = True
        self.code = code
        self.language = language
        self.language_input.text = language
        self.cell = cell
        self.cursor_pos = len(code)
        self.scroll_y = 0
        self.scroll_x = 0
        self.selection_start = len(code)
    
    def hide(self):
        self.visible = False
        return None, None
    
    def get_lines(self):
        return self.code.split('\n')

    def get_selection(self):
        start = min(self.selection_start, self.cursor_pos)
        end = max(self.selection_start, self.cursor_pos)
        return start, end

    def delete_selection(self):
        if self.selection_start == self.cursor_pos:
            return
        
        start, end = self.get_selection()
        self.code = self.code[:start] + self.code[end:]
        self.cursor_pos = start
        self.selection_start = start

    def get_cursor_row_col(self):
        lines = self.get_lines()
        pos = 0
        for i, line in enumerate(lines):
            if pos + len(line) + 1 > self.cursor_pos:
                return i, self.cursor_pos - pos
            pos += len(line) + 1
        return len(lines) - 1, len(lines[-1])

    def draw(self, surface):
        if not self.visible:
            return
        
        if self.clock:
            self.cursor_timer += self.clock.get_time()
            if self.cursor_timer > 500:
                self.cursor_timer = 0
                self.cursor_visible = not self.cursor_visible

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        surface.blit(overlay, (0, 0))
        
        pygame.draw.rect(surface, SURFACE, self.rect, border_radius=4)
        pygame.draw.rect(surface, ACCENT, self.rect, width=1, border_radius=4)
        
        title_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, 40)
        pygame.draw.rect(surface, PRIMARY, title_rect, border_top_left_radius=4, border_top_right_radius=4)
        
        title_surf = FONT_HEADER.render("Code Editor", True, SURFACE)
        title_rect_surf = title_surf.get_rect(center=(self.rect.centerx, self.rect.y + 20))
        surface.blit(title_surf, title_rect_surf)
        
        editor_rect = pygame.Rect(
            self.rect.x + 10, self.rect.y + 50, self.rect.width - 20, self.rect.height - 120
        )
        
        line_number_width = 40
        text_area_rect = pygame.Rect(
            editor_rect.x + line_number_width, editor_rect.y,
            editor_rect.width - line_number_width, editor_rect.height
        )

        lines = self.get_lines()
        font_height = FONT_MONO.get_height()
        max_visible_lines = editor_rect.height // font_height
        
        text_area_surface = surface.subsurface(text_area_rect)
        text_area_surface.fill(CODE_BG)
        
        selection_start_pos, selection_end_pos = self.get_selection()
        char_w, _ = FONT_MONO.size(' ')

        for i, line in enumerate(lines[self.scroll_y:self.scroll_y + max_visible_lines]):
            y_pos = i * font_height
            line_start_index = sum(len(l) + 1 for l in lines[:self.scroll_y + i])
            line_end_index = line_start_index + len(line)

            if selection_start_pos < line_end_index and selection_end_pos > line_start_index:
                start = max(line_start_index, selection_start_pos)
                end = min(line_end_index, selection_end_pos)
                start_x = (start - line_start_index) * char_w - self.scroll_x
                width = (end - start) * char_w
                selection_rect = pygame.Rect(start_x, y_pos, width, font_height)
                pygame.draw.rect(text_area_surface, (200, 200, 255), selection_rect)

            line_surf = FONT_MONO.render(line, True, TEXT)
            text_area_surface.blit(line_surf, (-self.scroll_x, y_pos))

        if self.cursor_visible:
            row, col = self.get_cursor_row_col()
            if self.scroll_y <= row < self.scroll_y + max_visible_lines:
                cursor_x = col * char_w - self.scroll_x
                cursor_y = (row - self.scroll_y) * font_height
                cursor_rect = pygame.Rect(cursor_x, cursor_y, 1, font_height)
                pygame.draw.rect(text_area_surface, TEXT, cursor_rect)

        line_number_bg = pygame.Rect(editor_rect.x, editor_rect.y, line_number_width, editor_rect.height)
        pygame.draw.rect(surface, (234, 234, 234), line_number_bg)
        for i in range(max_visible_lines):
            line_num_str = str(self.scroll_y + i + 1)
            line_num_surf = FONT_MONO.render(line_num_str, True, CODE_NUM)
            surface.blit(line_num_surf, (editor_rect.x + 5, editor_rect.y + i * font_height))
        
        lang_label_surf = FONT_BASE.render(self.language_label, True, TEXT)
        surface.blit(lang_label_surf, (self.rect.x + 10, self.rect.bottom - 30 - lang_label_surf.get_height() // 2))
        self.language_input.draw(surface)
        self.save_button.draw(surface)
        self.execute_button.draw(surface)
        self.cancel_button.draw(surface)
    
    def handle_event(self, event, clock):
        self.clock = clock
        if not self.visible:
            return False

        # Handle modal buttons
        for button in [self.save_button, self.execute_button, self.cancel_button]:
            if event.type == pygame.MOUSEMOTION:
                button.check_hover(event.pos)
            result = button.handle_event(event)
            if result:
                if button == self.save_button: return ('save', (self.code, self.language_input.text, self.cell))
                elif button == self.execute_button: return ('execute', (self.code, self.language_input.text))
                elif button == self.cancel_button:
                    self.hide()
                    return ('cancel', None)

        self.language_input.handle_event(event)

        # Define editor geometry, which is needed for event handling
        editor_rect = pygame.Rect(self.rect.x + 10, self.rect.y + 50, self.rect.width - 20, self.rect.height - 120)
        line_number_width = 40
        text_area_rect = pygame.Rect(
            editor_rect.x + line_number_width, editor_rect.y,
            editor_rect.width - line_number_width, editor_rect.height
        )

        mouse_pos = pygame.mouse.get_pos()
        if editor_rect.collidepoint(mouse_pos):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.selecting = True
                mx, my = event.pos
                row = self.scroll_y + (my - text_area_rect.y) // FONT_MONO.get_height()
                char_w, _ = FONT_MONO.size(' ')
                col = round((mx - text_area_rect.x + self.scroll_x) / char_w)
                lines = self.get_lines()
                row = min(row, len(lines) - 1)
                col = min(col, len(lines[row]))
                self.cursor_pos = sum(len(l) + 1 for l in lines[:row]) + col
                if not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    self.selection_start = self.cursor_pos
                self.cursor_timer = 0
                self.cursor_visible = True

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.selecting = False

            elif event.type == pygame.MOUSEMOTION and self.selecting:
                mx, my = event.pos
                row = self.scroll_y + (my - text_area_rect.y) // FONT_MONO.get_height()
                char_w, _ = FONT_MONO.size(' ')
                col = round((mx - text_area_rect.x + self.scroll_x) / char_w)
                lines = self.get_lines()
                row = min(row, len(lines) - 1)
                col = min(col, len(lines[row]))
                self.cursor_pos = sum(len(l) + 1 for l in lines[:row]) + col
                self.cursor_timer = 0
                self.cursor_visible = True

        if event.type == pygame.KEYDOWN:
            self.cursor_timer = 0
            self.cursor_visible = True
            shift_pressed = pygame.key.get_mods() & pygame.KMOD_SHIFT

            if not shift_pressed and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_HOME, pygame.K_END):
                self.selection_start = self.cursor_pos

            if event.key == pygame.K_a and pygame.key.get_mods() & pygame.KMOD_CTRL:
                self.selection_start = 0
                self.cursor_pos = len(self.code)
            elif event.key == pygame.K_LEFT:
                if self.cursor_pos > 0:
                    self.cursor_pos -= 1
            elif event.key == pygame.K_RIGHT:
                if self.cursor_pos < len(self.code):
                    self.cursor_pos += 1
            elif event.key == pygame.K_HOME:
                row, col = self.get_cursor_row_col()
                self.cursor_pos -= col
            elif event.key == pygame.K_END:
                row, col = self.get_cursor_row_col()
                line_len = len(self.get_lines()[row])
                self.cursor_pos += line_len - col
            elif event.key == pygame.K_UP:
                row, col = self.get_cursor_row_col()
                if row > 0:
                    prev_len = len(self.get_lines()[row-1])
                    prev_start = sum(len(l) + 1 for l in self.get_lines()[:row-1])
                    self.cursor_pos = prev_start + min(prev_len, col)
            elif event.key == pygame.K_DOWN:
                row, col = self.get_cursor_row_col()
                lines = self.get_lines()
                if row < len(lines) - 1:
                    next_len = len(lines[row+1])
                    next_start = sum(len(l) + 1 for l in lines[:row+1])
                    self.cursor_pos = next_start + min(next_len, col)
            elif event.key == pygame.K_BACKSPACE:
                if self.selection_start != self.cursor_pos: self.delete_selection()
                elif self.cursor_pos > 0:
                    self.code = self.code[:self.cursor_pos-1] + self.code[self.cursor_pos:]
                    self.cursor_pos -= 1
                    self.selection_start = self.cursor_pos
            elif event.key == pygame.K_DELETE:
                if self.selection_start != self.cursor_pos: self.delete_selection()
                elif self.cursor_pos < len(self.code):
                    self.code = self.code[:self.cursor_pos] + self.code[self.cursor_pos+1:]
            elif event.key == pygame.K_RETURN:
                self.delete_selection()
                self.code = self.code[:self.cursor_pos] + '\n' + self.code[self.cursor_pos:]
                self.cursor_pos += 1
                self.selection_start = self.cursor_pos
            elif event.key == pygame.K_TAB:
                self.delete_selection()
                self.code = self.code[:self.cursor_pos] + '    ' + self.code[self.cursor_pos:]
                self.cursor_pos += 4
                self.selection_start = self.cursor_pos
            elif event.unicode:
                self.delete_selection()
                self.code = self.code[:self.cursor_pos] + event.unicode + self.code[self.cursor_pos:]
                self.cursor_pos += len(event.unicode)
                self.selection_start = self.cursor_pos
        
        row, col = self.get_cursor_row_col()
        max_visible_lines = editor_rect.height // FONT_MONO.get_height()
        char_w, _ = FONT_MONO.size(' ')
        if char_w > 0:
            max_visible_cols = text_area_rect.width // char_w
            if col < self.scroll_x: self.scroll_x = col
            if col >= self.scroll_x + max_visible_cols: self.scroll_x = col - max_visible_cols + 1

        if row < self.scroll_y: self.scroll_y = row
        if row >= self.scroll_y + max_visible_lines: self.scroll_y = row - max_visible_lines + 1

        return False


class OutputModal:
    def __init__(self, screen_width, screen_height):
        self.width = int(screen_width * 0.6)
        self.height = int(screen_height * 0.5)
        self.rect = pygame.Rect(
            (screen_width - self.width) // 2,
            (screen_height - self.height) // 2,
            self.width,
            self.height
        )
        
        self.visible = False
        self.output = ""
        self.success = True
        self.scroll_y = 0
        
        # Create close button
        button_width = 100
        button_height = 30
        margin = 10
        
        self.close_button = Button(
            self.rect.right - button_width - margin,
            self.rect.bottom - button_height - margin,
            button_width,
            button_height,
            "Close"
        )
    
    def show(self, output, success=True):
        self.visible = True
        self.output = output
        self.success = success
        self.scroll_y = 0
    
    def hide(self):
        self.visible = False
    
    def draw(self, surface):
        if not self.visible:
            return
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        surface.blit(overlay, (0, 0))
        
        # Draw modal background
        pygame.draw.rect(surface, SURFACE, self.rect, border_radius=4)
        pygame.draw.rect(surface, ACCENT, self.rect, width=1, border_radius=4)
        
        # Draw title
        title_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, 40)
        title_color = (0, 128, 0) if self.success else (200, 0, 0)
        pygame.draw.rect(surface, title_color, title_rect, border_top_left_radius=4, border_top_right_radius=4)
        
        title = "Execution Output" if self.success else "Execution Error"
        title_surf = FONT_HEADER.render(title, True, SURFACE)
        title_rect = title_surf.get_rect(center=(self.rect.centerx, self.rect.y + 20))
        surface.blit(title_surf, title_rect)
        
        # Draw output area
        output_rect = pygame.Rect(
            self.rect.x + 10,
            self.rect.y + 50,
            self.rect.width - 20,
            self.rect.height - 100
        )
        pygame.draw.rect(surface, CODE_BG, output_rect)
        pygame.draw.rect(surface, ACCENT, output_rect, width=1)
        
        # Draw output text
        font = FONT_MONO
        font_height = font.get_height()
        lines = self.output.split('\n')
        
        # Calculate max visible lines
        max_visible_lines = output_rect.height // font_height
        
        # Draw visible lines
        for i, line in enumerate(lines[self.scroll_y:self.scroll_y + max_visible_lines]):
            line_color = TEXT
            line_surf = font.render(line, True, line_color)
            surface.blit(
                line_surf,
                (output_rect.x + 5, output_rect.y + i * font_height)
            )
        
        # Draw close button
        self.close_button.draw(surface)
    
    def handle_event(self, event):
        if not self.visible:
            return False
        
        # Handle button events
        if event.type == pygame.MOUSEMOTION:
            self.close_button.check_hover(event.pos)
        
        result = self.close_button.handle_event(event)
        if result:
            self.hide()
            return True
        
        # Handle mouse wheel for scrolling
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y = max(0, self.scroll_y - event.y)
            
            lines = self.output.split('\n')
            font_height = FONT_MONO.get_height()
            output_height = self.rect.height - 100
            max_visible_lines = output_height // font_height
            
            max_scroll = max(0, len(lines) - max_visible_lines)
            self.scroll_y = min(max_scroll, self.scroll_y)
        
        return False

class QuadtreeApp:
    """Main application class"""
    
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Quadtree Matrix Editor")
        
        self.clock = pygame.time.Clock()
        self.matrix = QuadtreeMatrix()
        self.current_depth = 0
        self.quadtree_size = 400
        self.max_depth = 4
        
        # Initialize with default context
        self.matrix.create_new_context("default", self.quadtree_size, self.max_depth)
        self.matrix.current_ctx = "default"
        
        # Initialize UI elements
        self.setup_ui()
        
        # Canvas for drawing
        self.canvas = pygame.Surface((MAIN_WIDTH, SCREEN_HEIGHT))
        self.canvas.fill(BG)
        
        # Initialize modals
        self.code_editor = CodeEditorModal(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.output_modal = OutputModal(SCREEN_WIDTH, SCREEN_HEIGHT)
        
        # State
        self.dragging = False
        self.hover_pos = None
    
    def setup_ui(self):
        # Context section
        self.ctx_label = "Context:"
        self.context_dropdown = DropDown(
            10, 40, SIDEBAR_WIDTH - 20, 30,
            self.matrix.get_context_list()
        )
        self.context_dropdown.selected = self.matrix.current_ctx
        
        # Context buttons
        button_width = 80
        button_height = 30
        margin = 10
        
        self.new_ctx_btn = Button(
            10, 80, button_width, button_height,
            "+ New", 
            self.new_context_action
        )
        
        self.import_ctx_btn = Button(
            10 + button_width + margin, 80, button_width, button_height,
            "Import", 
            self.import_context_action
        )
        
        self.export_ctx_btn = Button(
            10 + button_width*2 + margin*2, 80, button_width, button_height,
            "Export", 
            self.export_context_action
        )
        
        # Size input
        self.size_label = "Quadtree Size (px):"
        self.size_input = TextInput(
            10, 150, SIDEBAR_WIDTH - 20, 30,
            str(self.quadtree_size),
            self.size_label
        )
        
        # Depth slider
        self.depth_slider = Slider(
            10, 220, SIDEBAR_WIDTH - 20, 30,
            0, self.max_depth, self.current_depth,
            "Depth"
        )
        
        # Export PNG button
        self.export_png_btn = Button(
            10, 260, SIDEBAR_WIDTH - 20, 30,
            "Export PNG", 
            self.export_png_action
        )
        
        # All UI elements
        self.ui_elements = [
            self.context_dropdown,
            self.new_ctx_btn,
            self.import_ctx_btn,
            self.export_ctx_btn,
            self.size_input,
            self.depth_slider,
            self.export_png_btn
        ]
        
        # Context menu (will be populated when right-clicking)
        self.context_menu = None
    
    def new_context_action(self):
        # Create a popup to ask for context ID
        root = tk.Tk()
        root.withdraw()
        ctx_id = simpledialog.askstring("New Context", "Enter context ID:")
        root.destroy()
        
        if ctx_id:
            self.matrix.create_new_context(ctx_id, self.quadtree_size, self.max_depth)
            self.matrix.current_ctx = ctx_id
            
            # Update dropdown
            self.context_dropdown.options = self.matrix.get_context_list()
            self.context_dropdown.selected = ctx_id
        
        return True
    
    def import_context_action(self):
        root = tk.Tk()
        root.withdraw()
        filepath = filedialog.askopenfilename(
            title="Import Matrix",
            filetypes=[("JSON files", "*.json")]
        )
        root.destroy()
        
        if filepath:
            ctx_id = self.matrix.load_json(filepath)
            if ctx_id:
                self.matrix.current_ctx = ctx_id
                
                # Update UI to match imported matrix
                matrix = self.matrix.contexts[ctx_id]
                self.quadtree_size = matrix.quadtree_size
                self.size_input.text = str(self.quadtree_size)
                
                # Update depth slider
                self.max_depth = matrix.max_depth
                self.depth_slider.max = self.max_depth
                
                # Update dropdown
                self.context_dropdown.options = self.matrix.get_context_list()
                self.context_dropdown.selected = ctx_id
        
        return True
    
    def export_context_action(self):
        if not self.matrix.current_ctx:
            return False
            
        root = tk.Tk()
        root.withdraw()
        filepath = filedialog.asksaveasfilename(
            title="Export Matrix",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        root.destroy()
        
        if filepath:
            self.matrix.save_json(self.matrix.current_ctx, filepath)
        
        return True
    
    def export_png_action(self):
        if not self.matrix.current_ctx:
            return False
            
        # Render current view to surface
        self.render_quadtree()
        
        root = tk.Tk()
        root.withdraw()
        filepath = filedialog.asksaveasfilename(
            title="Export PNG",
            defaultextension=".png",
            filetypes=[("PNG files", "*.png")]
        )
        root.destroy()
        
        if filepath:
            pygame.image.save(self.canvas, filepath)
        
        return True
    
    def show_context_menu(self, position, cell):
        # Create menu options
        options = [
            ("🎨 Change Color", lambda: self.handle_context_action("change_color", cell)),
            ("T Add Text", lambda: self.handle_context_action("add_text", cell)),
            ("📝 Add Code", lambda: self.handle_context_action("add_code", cell)),
            ("🖼️ Add Image", lambda: self.handle_context_action("add_image", cell)),
            ("↪ Subdivide", lambda: self.handle_context_action("subdivide", cell)),
            ("---", None),
            ("↩ Reset Cell", lambda: self.handle_context_action("reset_cell", cell))
        ]
        
        # Check if cell has code to add Edit Code option
        if self.matrix.current_ctx:
            matrix = self.matrix.contexts[self.matrix.current_ctx]
            d, idx = cell
            key = f"{d}:{idx}"
            
            if key in matrix.payload_pool and matrix.payload_pool[key].get('type') == 'code':
                # Insert edit code option after add code
                options.insert(3, ("✏️ Edit Code", lambda: self.handle_context_action("edit_code", cell)))
                # Insert execute code option
                options.insert(4, ("▶️ Execute Code", lambda: self.handle_context_action("execute_code", cell)))
        
        # Create and position context menu
        menu_width = 180
        menu_height = len(options) * 30
        
        pos_x = min(position[0], SCREEN_WIDTH - menu_width - 10)
        pos_y = min(position[1], SCREEN_HEIGHT - menu_height - 10)
        
        self.context_menu = ContextMenu(pos_x, pos_y, menu_width, menu_height, options)
    
    def handle_context_action(self, action, cell):
        if not self.matrix.current_ctx or not cell:
            return False
        
        matrix = self.matrix.contexts[self.matrix.current_ctx]
        d, idx = cell
        
        if action == "change_color":
            root = tk.Tk()
            root.withdraw()
            color = colorchooser.askcolor(title="Choose Color")[0]
            root.destroy()
            
            if color:
                # Convert RGB to int color
                r, g, b = [int(c) for c in color]
                color_int = (r << 16) | (g << 8) | b
                matrix.layers[d].nodes[idx] = color_int
        
        elif action == "add_text":
            root = tk.Tk()
            root.withdraw()
            text = simpledialog.askstring("Add Text", "Enter text:")
            
            if text:
                # Ask for color
                color = colorchooser.askcolor(title="Text Color")[0]
                root.destroy()
                
                if color:
                    r, g, b = [int(c) for c in color]
                    matrix.payload_pool[f"{d}:{idx}"] = {
                        'type': 'text',
                        'text': text,
                        'color': [r, g, b]
                    }
            else:
                root.destroy()
        
        elif action == "add_code" or action == "edit_code":
            # Show code editor
            code = ""
            language = "python"
            
            # Load existing code if editing
            if action == "edit_code":
                key = f"{d}:{idx}"
                if key in matrix.payload_pool and matrix.payload_pool[key].get('type') == 'code':
                    code = matrix.payload_pool[key].get('code', '')
                    language = matrix.payload_pool[key].get('language', 'python')
            
            self.code_editor.show(code, language, cell)
        
        elif action == "execute_code":
            key = f"{d}:{idx}"
            if key in matrix.payload_pool and matrix.payload_pool[key].get('type') == 'code':
                code = matrix.payload_pool[key].get('code', '')
                language = matrix.payload_pool[key].get('language', 'python')
                
                # Execute the code
                success, output = self.matrix.code_executor.execute(code, language)
                
                # Show output window
                self.output_modal.show(output, success)
        
        elif action == "add_image":
            root = tk.Tk()
            root.withdraw()
            filepath = filedialog.askopenfilename(
                title="Select Image",
                filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp")]
            )
            root.destroy()
            
            if filepath:
                try:
                    with open(filepath, "rb") as f:
                        img_data = f.read()
                    
                    # Convert to base64 for storage
                    b64_data = base64.b64encode(img_data).decode('utf-8')
                    
                    matrix.payload_pool[f"{d}:{idx}"] = {
                        'type': 'image',
                        'data': b64_data
                    }
                except Exception as e:
                    print(f"Error loading image: {e}")
        
        elif action == "subdivide":
            if d < matrix.max_depth:
                parent_key = f"{d}:{idx}"
                color = matrix.layers[d].nodes[idx]
                payload = matrix.payload_pool.get(parent_key)
                
                d1 = d + 1
                layer1 = matrix.layers[d1]
                
                cx = idx % matrix.layers[d].size
                cy = idx // matrix.layers[d].size
                
                base_x = cx * 2
                base_y = cy * 2
                
                for dy in range(2):
                    for dx in range(2):
                        cx1 = base_x + dx
                        cy1 = base_y + dy
                        idx1 = cy1 * layer1.size + cx1
                        
                        layer1.nodes[idx1] = color
                        
                        if payload:
                            matrix.payload_pool[f"{d1}:{idx1}"] = payload.copy()
        
        elif action == "reset_cell":
            matrix.layers[d].nodes[idx] = 0
            key = f"{d}:{idx}"
            if key in matrix.payload_pool:
                del matrix.payload_pool[key]
        
        # Return True to indicate action was handled
        return True
    
    def render_quadtree(self):
        """Render the current quadtree to the canvas"""
        if not self.matrix.current_ctx:
            return
        
        matrix = self.matrix.contexts[self.matrix.current_ctx]
        d = self.current_depth
        
        S = matrix.quadtree_size
        layer = matrix.layers[d]
        cell_size = S / layer.size
        
        # Calculate position to center the quadtree
        offset_x = (MAIN_WIDTH - S) // 2
        offset_y = (SCREEN_HEIGHT - S) // 2
        
        # Clear canvas
        self.canvas.fill(BG)
        
        # Draw cells
        for i, color in enumerate(layer.nodes):
            if color:
                cx = i % layer.size
                cy = i // layer.size
                x = int(cx * cell_size) + offset_x
                y = int(cy * cell_size) + offset_y
                
                # Extract RGB components
                r = (color >> 16) & 0xFF
                g = (color >> 8) & 0xFF
                b = color & 0xFF
                
                pygame.draw.rect(
                    self.canvas,
                    (r, g, b),
                    (x, y, int(cell_size), int(cell_size))
                )
            
            # Draw payloads
            key = f"{d}:{i}"
            payload = matrix.payload_pool.get(key)
            
            if payload:
                cx = i % layer.size
                cy = i // layer.size
                x = int(cx * cell_size) + offset_x
                y = int(cy * cell_size) + offset_y
                
                if payload.get('type') == 'text':
                    text = payload.get('text', '')
                    color = payload.get('color', [0, 0, 0])
                    
                    # Render text
                    font_size = int(cell_size * 0.3)
                    font = pygame.font.SysFont("Arial", max(12, min(font_size, 36)))
                    text_surf = font.render(text, True, color)
                    
                    # Center text
                    text_rect = text_surf.get_rect(center=(
                        x + cell_size/2,
                        y + cell_size/2
                    ))
                    
                    self.canvas.blit(text_surf, text_rect)
                
                elif payload.get('type') == 'code':
                    code = payload.get('code', '')
                    
                    if cell_size < 100:
                        # Small cell, just show code symbol
                        font_size = int(cell_size * 0.5)
                        font = pygame.font.SysFont("Courier New", max(12, min(font_size, 36)), bold=True)
                        text_surf = font.render("{ }", True, (51, 51, 51))
                        
                        # Center text
                        text_rect = text_surf.get_rect(center=(
                            x + cell_size/2,
                            y + cell_size/2
                        ))
                        
                        self.canvas.blit(text_surf, text_rect)

                        if self.hover_pos:
                            hx, hy = self.hover_pos
                            if SIDEBAR_WIDTH + x <= hx <= SIDEBAR_WIDTH + x + cell_size and y <= hy <= y + cell_size:
                                preview = code.split('\n', 1)[0][:30]
                                tip_font = FONT_MONO
                                tip_surf = tip_font.render(preview, True, TEXT)
                                bg_rect = tip_surf.get_rect()
                                bg_rect.topleft = (x, y - bg_rect.height - 2)
                                pygame.draw.rect(self.canvas, SURFACE, bg_rect)
                                pygame.draw.rect(self.canvas, ACCENT, bg_rect, 1)
                                self.canvas.blit(tip_surf, bg_rect)
                    else:
                        # --- clipping region (unchanged) ---
                        cell_rect = pygame.Rect(x + 2, y + 2, cell_size - 4, cell_size - 4)
                        old_clip  = self.canvas.get_clip()
                        # ---------------- sizing constants (restore these!) ----------------
                        code_lines     = code.split("\n")
                        line_height    = min(cell_size * 0.09, 16)      # px per rendered row
                        padding        = 8                               # top/left inset
                        line_num_width = 20                              # gutter for numbers
                        max_lines      = int((cell_size - 2*padding) / line_height)
                        # -------------------------------------------------------------------

                        self.canvas.set_clip(cell_rect)

                        # --- background rectangles (unchanged) ---
                        pygame.draw.rect(self.canvas, CODE_BG, (x + 2, y + 2, cell_size - 4, cell_size - 4))
                        pygame.draw.rect(self.canvas, (234, 234, 234), (x + 2, y + 2, line_num_width, cell_size - 4))

                        # --- wrapped code rendering ---
                        font          = pygame.font.SysFont("Courier New", int(line_height * 0.75))
                        line_idx      = 0
                        y_pos         = y + padding
                        for raw_line in code_lines:
                            wrapped_segments = wrap_text(raw_line, font, cell_size - line_num_width - 10)
                            for seg in wrapped_segments:
                                if line_idx >= max_lines:          # vertical clip
                                    break

                                # line number
                                ln_surf = font.render(str(line_idx + 1), True, CODE_NUM)
                                self.canvas.blit(
                                    ln_surf,
                                    (x + line_num_width - 2 - ln_surf.get_width(), y_pos)
                                )

                                # code text
                                code_surf = font.render(seg, True, (51, 51, 51))
                                self.canvas.blit(
                                    code_surf,
                                    (x + line_num_width + 5, y_pos)
                                )

                                y_pos    += line_height
                                line_idx += 1
                            if line_idx >= max_lines:
                                break

                        # --- overflow ellipsis ---
                        if line_idx < len(code_lines):
                            dots = font.render("⋯", True, (102, 102, 102))
                            self.canvas.blit(
                                dots,
                                (x + cell_size / 2 - dots.get_width() / 2, y + cell_size - padding - line_height)
                            )

                        # --- restore previous clip ---
                        self.canvas.set_clip(old_clip)



                
                elif payload.get('type') == 'image':
                    try:
                        # Decode base64 image data
                        img_data = base64.b64decode(payload.get('data', ''))
                        img = Image.open(io.BytesIO(img_data))
                        
                        # Convert PIL Image to Pygame surface
                        mode = img.mode
                        size = img.size
                        data = img.tobytes()
                        
                        img_surface = pygame.image.fromstring(data, size, mode)
                        
                        # Scale to fit cell
                        img_surface = pygame.transform.scale(
                            img_surface,
                            (int(cell_size), int(cell_size))
                        )
                        
                        # Draw image
                        self.canvas.blit(img_surface, (x, y))
                    except Exception as e:
                        print(f"Error rendering image: {e}")
        
        # Draw grid lines
        for i in range(layer.size + 1):
            pos = int(i * cell_size) + offset_x
            pygame.draw.line(
                self.canvas,
                GRID_COLOR,
                (pos, offset_y),
                (pos, offset_y + S)
            )
            
            pos = int(i * cell_size) + offset_y
            pygame.draw.line(
                self.canvas,
                GRID_COLOR,
                (offset_x, pos),
                (offset_x + S, pos)
            )
    
    def get_cell_at_position(self, pos):
        """Get cell coordinates at mouse position"""
        if not self.matrix.current_ctx:
            return None
        
        matrix = self.matrix.contexts[self.matrix.current_ctx]
        S = matrix.quadtree_size
        layer = matrix.layers[self.current_depth]
        cell_size = S / layer.size
        
        # Calculate offset to center quadtree
        offset_x = (MAIN_WIDTH - S) // 2 + SIDEBAR_WIDTH
        offset_y = (SCREEN_HEIGHT - S) // 2
        
        # Calculate relative position in quadtree
        rel_x = pos[0] - offset_x
        rel_y = pos[1] - offset_y
        
        # Check if position is within quadtree
        if 0 <= rel_x < S and 0 <= rel_y < S:
            cx = int(rel_x // cell_size)
            cy = int(rel_y // cell_size)
            idx = cy * layer.size + cx
            
            return (self.current_depth, idx)
        
        return None

    def handle_code_editor_result(self, result):
        if not result:
            return
        
        action, data = result
        
        if action == 'save':
            code, language, cell = data
            if cell and self.matrix.current_ctx:
                d, idx = cell
                self.matrix.contexts[self.matrix.current_ctx].payload_pool[f"{d}:{idx}"] = {
                    'type': 'code',
                    'code': code,
                    'language': language
                }
        
        elif action == 'execute':
            code, language = data
            success, output = self.matrix.code_executor.execute(code, language)
            self.output_modal.show(output, success)
    
    def handle_events(self):
        """Handle pygame events"""
        mouse_pos = pygame.mouse.get_pos()
        self.hover_pos = mouse_pos

        # Update hover state for UI elements before processing events
        for element in self.ui_elements:
            if hasattr(element, 'check_hover'):
                element.check_hover(mouse_pos)

        # Handle context menu hover if active
        if self.context_menu:
            self.context_menu.check_hover(mouse_pos)

        # Process the event queue
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            # --- MODAL AND CONTEXT MENU HANDLING (Corrected Logic) ---

            # Handle modals first, as they are on top and should consume events
            code_editor_result = self.code_editor.handle_event(event, self.clock)
            if code_editor_result:
                self.handle_code_editor_result(code_editor_result)
                continue # Event handled, move to next event

            if self.output_modal.handle_event(event):
                continue # Event handled, move to next event

            # Handle context menu if it's active
            if self.context_menu:
                action = self.context_menu.handle_event(event)
                if action:
                    action()
                    self.context_menu = None
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if (not self.context_menu.rect.collidepoint(event.pos) or
                        self.context_menu.hovered_index == -1):
                        self.context_menu = None
                
                continue # Event was related to the context menu, so we skip the rest

            # --- MAIN UI AND CANVAS EVENT HANDLING ---

            # Handle main UI element events
            handled = False
            for element in self.ui_elements:
                result = element.handle_event(event)
                if result:
                    handled = True
                    
                    if element == self.context_dropdown:
                        if isinstance(result, str):
                            self.matrix.current_ctx = result
                            
                            matrix = self.matrix.contexts[self.matrix.current_ctx]
                            self.quadtree_size = matrix.quadtree_size
                            self.size_input.text = str(self.quadtree_size)
                            self.max_depth = matrix.max_depth
                            self.depth_slider.max = self.max_depth

                    elif element == self.depth_slider:
                        self.current_depth = result

                    elif element == self.size_input:
                        try:
                            new_size = int(result)
                            if 100 <= new_size <= SCREEN_HEIGHT:
                                self.quadtree_size = new_size
                                if self.matrix.current_ctx:
                                    self.matrix.contexts[self.matrix.current_ctx].quadtree_size = new_size
                        except ValueError:
                            self.size_input.text = str(self.quadtree_size)
                    
                    break

            if handled:
                continue

            # Handle right-click for context menu in the main canvas area
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if event.pos[0] > SIDEBAR_WIDTH:
                    cell = self.get_cell_at_position(event.pos)
                    if cell:
                        self.show_context_menu(event.pos, cell)

        return True
    
    def update(self, dt):
        """Update game state"""
        pass
    
    def draw(self):
        """Draw the application"""
        # Clear screen
        self.screen.fill(SURFACE)
        
        # Draw sidebar background
        pygame.draw.rect(
            self.screen,
            SURFACE,
            (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT)
        )
        
        # Draw sidebar title
        title_surf = FONT_HEADER.render("Quadtree Controls", True, PRIMARY)
        self.screen.blit(title_surf, (SIDEBAR_WIDTH // 2 - title_surf.get_width() // 2, 10))
        
        # Draw context label
        ctx_label_surf = FONT_BASE.render(self.ctx_label, True, TEXT)
        self.screen.blit(ctx_label_surf, (10, 40 - ctx_label_surf.get_height() - 2))
        
        # Draw UI elements
        for element in self.ui_elements:
            if element is not self.context_dropdown:
                element.draw(self.screen)

        # Draw the dropdown last so options appear on top
        self.context_dropdown.draw(self.screen)
        
        # Draw main area background
        pygame.draw.rect(
            self.screen,
            BG,
            (SIDEBAR_WIDTH, 0, MAIN_WIDTH, SCREEN_HEIGHT)
        )
        
        # Render quadtree
        self.render_quadtree()
        
        # Draw canvas to screen
        self.screen.blit(self.canvas, (SIDEBAR_WIDTH, 0))
        
        # Draw context menu if active
        if self.context_menu:
            self.context_menu.draw(self.screen)
        
        # Draw modals on top if visible
        self.code_editor.draw(self.screen)
        self.output_modal.draw(self.screen)
        
        # Update display
        pygame.display.flip()
    
    def run(self):
        """Main game loop"""
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            
            running = self.handle_events()
            self.update(dt)
            self.draw()

if __name__ == "__main__":
    app = QuadtreeApp()
    app.run()