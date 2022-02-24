import tkinter as tk
from tkhtmlview import HTMLLabel

root = tk.Tk()
root.title('gui-test-title')

#label1 = tk.Label(root, text="Hello World")
#label1.pack()
label2 = HTMLLabel(root, html="""
<h1>TEST123</h1>
	""")
label2.pack()

root.mainloop()