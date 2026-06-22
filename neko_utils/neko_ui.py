import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import os
import threading
import pygame
import time
import math
import speech_recognition as sr
from neko_core import NekoAssistant

class NekoUI:
    def __init__(self, assistant):
        self.assistant = assistant
        self.root = tk.Tk()
        self.root.title("Neko")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "magenta")
        
        self.follow_mouse = False
        self.listening = False
        
        # Load icon
        icon_path = os.path.join(self.assistant.data_dir, "icon.ico")
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(img)
        else:
            self.photo = None

        self.label = tk.Label(self.root, image=self.photo, bg="magenta")
        self.label.pack()

        # Audio
        pygame.mixer.init()
        self.sounds = {
            "meow": os.path.join(self.assistant.data_dir, "meow.mp3"),
            "purr": os.path.join(self.assistant.data_dir, "purr.mp3"),
            "high": os.path.join(self.assistant.data_dir, "meow_high.wav"),
            "low": os.path.join(self.assistant.data_dir, "meow_low.wav"),
        }

        # Bindings
        self.label.bind("<Button-1>", self.on_left_click)
        self.label.bind("<Button-3>", self.on_right_click)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<Double-Button-1>", self.on_double_click)

        # Center on screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"64x64+{sw-100}+{sh-150}")

        self.play_sound("purr")
        
        # Start update loop for following mouse
        self.update_loop()
        
        # Start background listener
        threading.Thread(target=self.voice_listener_bg, daemon=True).start()

    def play_sound(self, name):
        if name in self.sounds and os.path.exists(self.sounds[name]):
            try:
                pygame.mixer.music.load(self.sounds[name])
                pygame.mixer.music.play()
            except:
                pass

    def update_loop(self):
        if self.follow_mouse:
            mx = self.root.winfo_pointerx()
            my = self.root.winfo_pointery()
            nx = self.root.winfo_x() + 32
            ny = self.root.winfo_y() + 32
            
            # Move towards mouse
            dx = mx - nx
            dy = my - ny
            dist = math.sqrt(dx*dx + dy*dy)
            
            if dist > 40:
                speed = 5
                new_x = int(nx + (dx/dist) * speed) - 32
                new_y = int(ny + (dy/dist) * speed) - 32
                self.root.geometry(f"+{new_x}+{new_y}")
        
        self.root.after(20, self.update_loop)

    def on_drag(self, event):
        self.follow_mouse = False # Stop following when dragged
        x = self.root.winfo_pointerx() - 32
        y = self.root.winfo_pointery() - 32
        self.root.geometry(f"+{x}+{y}")

    def on_left_click(self, event):
        self.play_sound("meow")

    def on_right_click(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="🐾 Follow Mouse: " + ("ON" if self.follow_mouse else "OFF"), command=self.toggle_follow)
        menu.add_separator()
        
        for auto in self.assistant.automations:
            menu.add_command(label=f"🚀 {auto['name']}", command=lambda n=auto['name']: self.assistant.run_automation(n, "neko_right_click"))
        
        menu.add_separator()
        menu.add_command(label="🧮 Calculator", command=self.open_calculator)
        menu.add_command(label="🎤 Voice: " + ("Listening" if self.listening else "Idle"), command=self.voice_command_ui)
        menu.add_separator()
        menu.add_command(label="❌ Exit", command=self.root.destroy)
        
        menu.post(event.x_root, event.y_root)

    def toggle_follow(self):
        self.follow_mouse = not self.follow_mouse
        if self.follow_mouse: self.play_sound("high")

    def on_double_click(self, event):
        self.play_sound("high")
        self.open_calculator()

    def open_calculator(self):
        expr = simpledialog.askstring("Neko Calculator", "Meow? (e.g. 5*5 or 100 cm to in):")
        if expr:
            result = self.assistant.calculate(expr)
            messagebox.showinfo("Neko Result", result)
            self.play_sound("meow")

    def voice_command_ui(self):
        messagebox.showinfo("Neko Voice", "I am always listening for 'Neko' followed by a command!\nTry saying: 'Neko, work time' or 'Neko, calculate 5 plus 5'")

    def voice_listener_bg(self):
        r = sr.Recognizer()
        mic = sr.Microphone()
        
        while True:
            try:
                with mic as source:
                    r.adjust_for_ambient_noise(source)
                    self.listening = True
                    audio = r.listen(source, timeout=5, phrase_time_limit=5)
                    self.listening = False
                    
                text = r.recognize_google(audio).lower()
                print(f"Heard: {text}")
                
                if "neko" in text:
                    self.play_sound("meow")
                    if "work time" in text:
                        self.assistant.run_automation("work time", "voice")
                    elif "calculate" in text or "calc" in text:
                        # Simple extraction
                        expr = text.split("calculate")[-1].split("calc")[-1].strip()
                        # Convert spoken words to symbols
                        expr = expr.replace("plus", "+").replace("minus", "-").replace("times", "*").replace("divided by", "/")
                        res = self.assistant.calculate(expr)
                        print(f"Result: {res}")
                        self.play_sound("high")
                    elif "follow" in text:
                        self.toggle_follow()
                    elif "stop" in text:
                        self.follow_mouse = False
            except Exception as e:
                # print(f"Voice error: {e}")
                pass
            time.sleep(0.5)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    assistant = NekoAssistant()
    ui = NekoUI(assistant)
    ui.run()
