# app.py

import customtkinter
from src.gui import AppGUI

if __name__ == "__main__":
    """
    Initializes and runs the application.
    Using customtkinter.CTk() ensures the dark theme is applied correctly from the start.
    """
    root = customtkinter.CTk()
    app = AppGUI(root)
    root.mainloop()